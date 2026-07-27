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
FROM_SEASON = 9
TO_SEASON = 11


class MatchType(IntEnum):
    CASUAL = 1
    RANKED = 2
    PRIVATE = 3
    EVENT = 4


class UserProfile(BaseModel):
    uuid: UUID
    nickname: str
    roleType: int
    eloRate: int | None
    eloRank: int | None
    country: str | None


class MatchSeed(BaseModel):
    id: str | None
    overworld: str | None
    nether: str | None
    endTowers: list[int]
    variations: list[str]


class MatchResult(BaseModel):
    uuid: UUID | None
    time: int


class MatchRank(BaseModel):
    season: int | None
    allTime: int | None


class MatchChange(BaseModel):
    uuid: UUID
    change: int | None
    eloRate: int | None


class MatchVod(BaseModel):
    uuid: UUID
    url: str
    startsAt: int


class MatchCompletion(BaseModel):
    uuid: UUID
    time: int


class MatchTimeline(BaseModel):
    uuid: UUID
    time: int
    type: str


class MatchInfo(BaseModel):
    id: int
    type: MatchType
    season: int
    category: str | None
    date: datetime
    players: list[UserProfile]
    spectators: list[UserProfile]
    seed: MatchSeed | None
    result: MatchResult
    forfeited: bool
    decayed: bool
    rank: MatchRank
    changes: list[MatchChange]
    tag: str | None
    beginner: bool
    vod: list[MatchVod]


class Matches(RootModel):
    root: list[MatchInfo]


def fetch_matches(db: sqlite3.Connection, player: str, season: int, after_id: int | None, before_id: int | None) -> None:
    if JUST_CHECK:
        return

    while True:
        params = {
            "type": str(MatchType.RANKED.value),
            "season": str(season),
            "sort": "newest",
            "count": "100",
        }
        if after_id:
            params["after"] = str(after_id)
        if before_id:
            params["before"] = str(before_id)

        resp = niquests.get(f"{RANKED_HOST}/users/{player}/matches", params=params)
        if resp.status_code == 429:
            print("Got error 429, re-trying in 60 seconds...")
            time.sleep(60)
            continue

        matches = Matches(root=resp.json()["data"])
        if not matches.root:
            break

        before_id = matches.root[-1].id

        insert_matches = []
        for match in matches.root:
            players = [player.nickname.lower() for player in match.players]
            players.insert(0, "")
            players.append("")
            insert_matches.append((match.id, "|".join(players), match.season, match.date))

        cur = db.executemany("INSERT INTO `match` (`id`, `players`, `season`, `date`) VALUES (?, ?, ?, ?);", insert_matches)
        db.commit()
        print(f"Inserted {cur.rowcount} matches")


def fetch_for_player(db: sqlite3.Connection, player: str, season: int) -> None:
    cur = db.cursor()
    cur.execute("SELECT MIN(`id`) min_match_id, MAX(`id`) max_match_id FROM `match` WHERE `players` LIKE ? AND `season` = ?;",[f"%|{player}|%", season])
    min_match_id, max_match_id = cur.fetchone()

    if min_match_id and max_match_id:
        fetch_matches(db, player, season, max_match_id, None)
        fetch_matches(db, player, season, None, min_match_id)
    else:
        fetch_matches(db, player, season, None, None)


def get_vs_nicknames(db: sqlite3.Connection, player: str) -> set[str]:
    cur = db.execute("""
    WITH RECURSIVE Splitter AS (
        SELECT
            SUBSTR(players, 1, INSTR(players, '|') - 1) AS nickname,
            SUBSTR(players, INSTR(players, '|') + 1) AS remainder
        FROM
            match
        WHERE 
            players like ?
        UNION ALL
        SELECT
            SUBSTR(remainder, 1, INSTR(remainder, '|') - 1) AS nickname,
            SUBSTR(remainder, INSTR(remainder, '|') + 1) AS remainder
        FROM
            Splitter
        WHERE
            remainder != ''
    )
    SELECT
        DISTINCT(nickname)
    FROM
        Splitter
    WHERE nickname != '';
    """, [f"%|{player}|%"])

    return {row[0] for row in cur.fetchall()}


def try_players(db: sqlite3.Connection, player1: str, player2: str) -> tuple[str, ...] | None:
    for season in range(FROM_SEASON, TO_SEASON + 1):
        fetch_for_player(db, player2, season)

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


def main() -> None:
    db = sqlite3.connect("matches.db")
    db.executescript("""
    BEGIN;
    CREATE TABLE IF NOT EXISTS `match` (
        `id` BIGINT PRIMARY KEY NOT NULL,
        `players` VARCHAR(256) NOT NULL,
        `season` INT NOT NULL,
        `date` DATETIME NOT NULL
    );
    CREATE INDEX IF NOT EXISTS `idx_match_players` ON `match`(`players`);
    COMMIT;
    """)

    result = try_players(db, PLAYER1, PLAYER2)
    if result is None:
        print("Didn't find the result :(")
    else:
        print("=" * 32)
        print(f"FOUND: {'-'.join(result)}")
        print("Matches:")
        for num, (p1, p2) in enumerate(itertools.pairwise(result), start=1):
            cur = db.execute("SELECT `id`, `season`, `date` FROM `match` WHERE `players` LIKE ? AND `players` LIKE ? ORDER BY `id` DESC LIMIT 1;", [f"%|{p1}|%", f"%|{p2}|%"])
            match_id, match_season, match_date = cur.fetchone()
            print(
                f" {num}. {p1} vs {p2} in season {match_season}, on {match_date} "
                f"(match url: https://mcsrranked.com/stats/{p1}/vs/{p2}/{match_id}?season={match_season})"
            )

    db.close()


if __name__ == "__main__":
    main()
