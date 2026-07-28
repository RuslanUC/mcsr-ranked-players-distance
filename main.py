import itertools
import sqlite3
import time
from collections import deque
from datetime import datetime
from enum import IntEnum
from uuid import UUID

import niquests
from pydantic import BaseModel, RootModel


# RANKED_HOST = "https://api.mcsrranked.com"  # 5 seconds cache
RANKED_HOST = "https://mcsrranked.com/api"  # 30 seconds cache
PLAYER1 = "feinberg"
PLAYER2 = "fatchudlolcow"
JUST_CHECK = False
SKIP_FETCHING_EXISTING = True
RUN_BFS_FROM_PLAYER = "feinberg"
FROM_SEASON = 9
TO_SEASON = 11
LAST_SEASON = 11


class MatchType(IntEnum):
    CASUAL = 1
    RANKED = 2
    PRIVATE = 3
    EVENT = 4


class UserProfile(BaseModel):
    uuid: UUID
    nickname: str


class MatchResult(BaseModel):
    uuid: UUID | None
    time: int


class MatchInfo(BaseModel):
    id: int
    type: MatchType
    season: int
    date: datetime
    players: list[UserProfile]
    result: MatchResult
    forfeited: bool
    decayed: bool
    tag: str | None
    beginner: bool


class Matches(RootModel):
    root: list[MatchInfo]


def fetch_matches(
        db: sqlite3.Connection, player: str, season: int, after_id: int | None, before_id: int | None,
) -> None:
    if JUST_CHECK:
        return

    while True:
        params = {
            "type": str(MatchType.RANKED.value),
            "season": str(season),
            "sort": "newest",
            "count": "100",
            "excludedecay": "true",
        }
        if after_id:
            params["after"] = str(after_id)
        if before_id:
            params["before"] = str(before_id)

        resp = niquests.get(f"{RANKED_HOST}/users/{player}/matches", params=params)
        if resp.status_code == 404:
            print(f"Player {player} does not exist, what?")
            break
        if resp.status_code == 429:
            print("Got error 429, re-trying in 60 seconds...")
            time.sleep(60)
            continue

        resp_j = resp.json()
        if resp_j["status"] != "success":
            print(f"Failed to fetch data for player {player!r}: {resp_j['data']['error']}")
            break

        matches = Matches(root=resp_j["data"])
        if not matches.root:
            break

        before_id = matches.root[-1].id

        insert_matches = []
        for match in matches.root:
            players = [player.nickname.lower() for player in match.players]
            players.insert(0, "")
            players.append("")
            insert_matches.append((match.id, "|".join(players), match.season, match.date))

        cur = db.executemany(
            "INSERT OR IGNORE INTO `match` (`id`, `players`, `season`, `date`) VALUES (?, ?, ?, ?);",
            insert_matches,
        )
        print(f"Inserted {cur.rowcount} matches")

        min_id = matches.root[-1].id
        max_id = matches.root[0].id
        db.execute(
            """
            UPDATE `player` 
            SET 
                `min_match_id`=MIN(COALESCE(`min_match_id`, ?), ?),
                `max_match_id`=MAX(COALESCE(`max_match_id`, 0), ?)
            WHERE 
                `nickname` = ? AND `season` =?;
            """,
            [min_id, min_id, max_id, player, season],
        )
        db.commit()


def fetch_for_player(db: sqlite3.Connection, player: str, season: int) -> None:
    cur = db.cursor()
    cur.execute(
        """
        SELECT `min_match_id`, `max_match_id`, `season_fetched`
        FROM `player`
        WHERE `nickname` = ? AND `season` = ?;
        """,
        [player, season],
    )
    row = cur.fetchone()
    if row is None:
        db.execute("INSERT INTO `player` (`nickname`, `season`) VALUES (?, ?);", [player, season])
        fetch_matches(db, player, season, None, None)
    else:
        min_match_id, max_match_id, season_fetched = row
        if SKIP_FETCHING_EXISTING or season_fetched:
            print(f"Skipping fetching season {season} for player {player}")
            return
        fetch_matches(db, player, season, max_match_id, None)
        fetch_matches(db, player, season, None, min_match_id)

    if season < LAST_SEASON:
        db.execute(
            "UPDATE `player` SET `season_fetched` = 1 WHERE `nickname` = ? AND `season` = ?;",
            [player, season]
        )


def get_vs_nicknames(db: sqlite3.Connection, player: str) -> set[str]:
    result = set()
    if JUST_CHECK and False:
        sep = " "
        cur = db.execute("SELECT `players` FROM `match_fts` WHERE `players` MATCH ?;", [f"\"{player}\""])
    else:
        sep = "|"
        cur = db.execute("SELECT `players` FROM `match` WHERE `players` LIKE ?;", [f"%|{player}|%"])

    for players_separated, in cur:
        for nickname in players_separated.split(sep):
            if not nickname:
                continue
            result.add(nickname)

    return result

def try_players(db: sqlite3.Connection, player1: str, player2: str) -> tuple[str, ...] | None:
    vs2 = get_vs_nicknames(db, player2)

    queue: deque[tuple[str, tuple[str, ...]]] = deque([(player1, (player1,))])
    seen = {player1}

    while queue:
        nickname, path = queue.popleft()
        print(f"Trying {'-'.join(path)}")

        for season in range(FROM_SEASON, TO_SEASON + 1):
            fetch_for_player(db, nickname, season)

        vs = get_vs_nicknames(db, nickname)
        if player2 in vs:
            return *path, player2

        for other in vs:
            if other in seen:
                continue
            if other in vs2:
                return *path, other, player2
            seen.add(other)
            queue.append((other, (*path, other)))

    return None


def run_bfs_from_player(db: sqlite3.Connection, player: str) -> None:
    queue: deque[str] = deque([player])
    seen = {player}

    while queue:
        nickname = queue.popleft()
        print(f"Fetching player {nickname}")

        for season in range(FROM_SEASON, TO_SEASON + 1):
            fetch_for_player(db, nickname, season)

        for other in get_vs_nicknames(db, nickname):
            if other in seen:
                continue
            seen.add(other)
            queue.append(other)


def main() -> None:
    db = sqlite3.connect("matches.db")
    db.executescript("""
    BEGIN;
    CREATE TABLE IF NOT EXISTS `player` (
        `nickname` VARCHAR(32) NOT NULL,
        `season` INT NOT NULL,
        `min_match_id` BIGINT DEFAULT NULL,
        `max_match_id` BIGINT DEFAULT NULL,
        `season_fetched` BOOL NOT NULL DEFAULT FALSE,
        PRIMARY KEY (`nickname`, `season`)
    );
    CREATE TABLE IF NOT EXISTS `match` (
        `id` BIGINT PRIMARY KEY NOT NULL,
        `players` VARCHAR(256) NOT NULL,
        `season` INT NOT NULL,
        `date` DATETIME NOT NULL
    );
    CREATE INDEX IF NOT EXISTS `idx_match_players` ON `match`(`players`);
    DROP TABLE IF EXISTS `match_fts`;
    COMMIT;
    """)

    if JUST_CHECK and False:
        db.execute("CREATE VIRTUAL TABLE `match_fts` USING fts5(`players`);")
        db.execute("INSERT INTO `match_fts` (`players`) SELECT REPLACE(`players`, '|', ' ') FROM `match`;")

    if RUN_BFS_FROM_PLAYER is not None:
        run_bfs_from_player(db, RUN_BFS_FROM_PLAYER)
        db.close()
        return

    result = try_players(db, PLAYER1, PLAYER2)
    if result is None:
        print("Didn't find the result :(")
    else:
        print("=" * 32)
        print(f"FOUND: {'-'.join(result)}")
        print("Matches:")
        for num, (p1, p2) in enumerate(itertools.pairwise(result), start=1):
            cur = db.execute(
                """
                SELECT `id`, `season`, `date` 
                FROM `match` 
                WHERE `players` LIKE ? AND `players` LIKE ? 
                ORDER BY `id` DESC 
                LIMIT 1;
                """,
                [f"%|{p1}|%", f"%|{p2}|%"],
            )
            match_id, match_season, match_date = cur.fetchone()
            print(
                f" {num}. {p1} vs {p2} in season {match_season}, on {match_date} "
                f"(match url: https://mcsrranked.com/stats/{p1}/vs/{p2}/{match_id}?season={match_season})"
            )

    db.close()


if __name__ == "__main__":
    main()
