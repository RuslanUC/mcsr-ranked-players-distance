import sqlite3
import time
from collections import deque
from datetime import datetime
from enum import IntEnum
from uuid import UUID

import niquests
from loguru import logger
from pydantic import BaseModel, RootModel


# RANKED_HOST = "https://api.mcsrranked.com"  # 5 seconds cache
RANKED_HOST = "https://mcsrranked.com/api"  # 30 seconds cache
SKIP_FETCHING_EXISTING = False
RUN_BFS_FROM_PLAYER: str | None = None
OFFSET_PLAYER = None
FROM_SEASON = 1
TO_SEASON = 11
LAST_SEASON = 12
# season 1 min id - 100876, fetched max id - 338903
# season 2 min id - 338910, fetched max id - 519261
# season 3 min id - 519262, fetched max id - 674675
# season 4 min id - 674680, fetched max id - 727169
# season 5 min id - 909754, fetched max id - 1168207
# season 6 min id - 1168210, fetched max id - 1499236
# season 7 min id - 1499237, fetched max id - 1842958
# season 8 min id - 1970850, fetched max id - 2110220
# season 9 min id - 2803592, fetched max id - 4547052
# season 10 min id - 4547099, fetched max id - 9676810
# season 11 min id - 9676905, fetched max id - 12897285
# season 12 min id - 12897439, fetched max id - ...
FETCH_MATCHES_FROM_ID = 0
FETCH_MATCHES_SEASON = 12

REQ_SINCE_LAST_RATE_LIMIT = 0


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


class SeasonResult(BaseModel):
    ...


class SeasonsResponse(BaseModel):
    seasonResults: dict[int, SeasonResult]


class Break(Exception):
    ...


class Continue(Exception):
    ...


def _process_response(player: str | None, resp: niquests.Response) -> dict:
    global REQ_SINCE_LAST_RATE_LIMIT

    if resp.status_code == 404:
        logger.warning(f"Player {player} does not exist, what?")
        raise Break
    if resp.status_code == 429:
        logger.info(f"Requests since last rate limit: {REQ_SINCE_LAST_RATE_LIMIT - 1}")
        REQ_SINCE_LAST_RATE_LIMIT = 0

        wait_seconds = 60
        if "Ratelimit" in resp.headers:
            ratelimit = resp.headers["Ratelimit"]
            for part in ratelimit.split(";"):
                part = part.strip()
                if part.startswith("t="):
                    _, _, seconds = part.partition("=")
                    seconds = seconds.strip()
                    if seconds.isdigit():
                        wait_seconds = int(seconds)
        wait_seconds = max(wait_seconds, 5)
        logger.warning(f"Got error 429, re-trying in {wait_seconds} seconds...")
        time.sleep(wait_seconds)
        raise Continue

    try:
        resp_j = resp.json()
    except niquests.JSONDecodeError:
        wait_seconds = 5
        logger.warning(f"Got JSONDecodeError, re-trying in {wait_seconds} seconds...")
        time.sleep(wait_seconds)
        raise Continue
    if resp_j["status"] != "success":
        logger.warning(f"Failed to fetch data for player {player!r}: {resp_j['data']['error']}")
        raise Break

    return resp_j


def fetch_matches_for_player(
        db: sqlite3.Connection, player: str, season: int, after_id: int | None, before_id: int | None,
) -> None:
    global REQ_SINCE_LAST_RATE_LIMIT

    insert_matches = []
    insert_matches_players = []
    min_id = None
    max_id = None

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

        REQ_SINCE_LAST_RATE_LIMIT += 1
        resp = niquests.get(f"{RANKED_HOST}/users/{player}/matches", params=params)
        try:
            resp_j = _process_response(player, resp)
        except Break:
            break
        except Continue:
            continue

        matches = Matches(root=resp_j["data"])
        if not matches.root:
            break

        before_id = matches.root[-1].id
        min_id = matches.root[-1].id
        max_id = matches.root[0].id

        for match in matches.root:
            insert_matches.append((match.id, match.season, match.date))
            for match_player in match.players:
                insert_matches_players.append((match.id, match_player.nickname.lower()))

        if len(matches.root) != 100:
            logger.debug("Number of matches is not 100, probably no matches left?")
            break

    cur = db.executemany(
        "INSERT OR IGNORE INTO `match` (`id`, `season`, `date`) VALUES (?, ?, ?);",
        insert_matches,
    )
    matches_cnt = cur.rowcount
    cur = db.executemany(
        "INSERT OR IGNORE INTO `match_player` (`match_id`, `player_nickname`) VALUES (?, ?);",
        insert_matches_players,
    )
    logger.debug(f"Inserted {matches_cnt} matches and {cur.rowcount} matches-players")

    if min_id is not None and max_id is not None:
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


def fetch_matches_between_ids(db: sqlite3.Connection, season: int, after_id: int, before_id: int) -> int:
    global REQ_SINCE_LAST_RATE_LIMIT

    insert_matches = []
    insert_matches_players = []
    max_id = after_id

    while True:
        params = {
            "count": "100",
            "type": str(MatchType.RANKED.value),
            "season": str(season),
            "after": str(after_id),
            "before": str(before_id),
        }

        REQ_SINCE_LAST_RATE_LIMIT += 1
        resp = niquests.get(f"{RANKED_HOST}/matches", params=params)
        try:
            resp_j = _process_response(None, resp)
        except Break:
            break
        except Continue:
            continue

        matches = Matches(root=resp_j["data"])

        min_id = before_id

        for match in matches.root:
            min_id = min(min_id, match.id)
            max_id = max(max_id, match.id)
            insert_matches.append((match.id, match.season, match.date))
            for match_player in match.players:
                insert_matches_players.append((match.id, match_player.nickname.lower()))

        if before_id - after_id > 100 and len(matches.root) == 100 and min_id > after_id:
            logger.warning(
                "Api returned number of matches that equals to the limit, but before-after has more than 100 matches. "
                f"Will fetch matches {after_id}-{min_id}."
            )
            fetch_matches_between_ids(db, season, after_id, min_id)

        break

    cur = db.executemany(
        "INSERT OR IGNORE INTO `match` (`id`, `season`, `date`) VALUES (?, ?, ?);",
        insert_matches,
    )
    matches_cnt = cur.rowcount
    cur = db.executemany(
        "INSERT OR IGNORE INTO `match_player` (`match_id`, `player_nickname`) VALUES (?, ?);",
        insert_matches_players,
    )
    logger.debug(f"Inserted {matches_cnt} matches and {cur.rowcount} matches-players")

    db.commit()

    return max_id


def fetch_seasons_with_matches(player: str) -> set[int]:
    global REQ_SINCE_LAST_RATE_LIMIT

    while True:
        REQ_SINCE_LAST_RATE_LIMIT += 1
        resp = niquests.get(f"{RANKED_HOST}/users/{player}/seasons")
        try:
            resp_j = _process_response(player, resp)
        except Break:
            break
        except Continue:
            continue

        seasons_resp = SeasonsResponse(**resp_j["data"])
        return set(seasons_resp.seasonResults.keys())

    return set()


def fetch_for_player(db: sqlite3.Connection, player: str) -> None:
    cur = db.execute(
        """
        SELECT `season`, `min_match_id`, `max_match_id`, `season_fetched`
        FROM `player`
        WHERE `nickname` = ? AND `season` >= ? AND `season` <= ?;
        """,
        [player, FROM_SEASON, TO_SEASON],
    )

    need_fetch_seasons: dict[int, tuple[int, int] | None] = {
        season: None
        for season in range(FROM_SEASON, TO_SEASON + 1)
    }
    skipped = []

    for season, min_match_id, max_match_id, season_fetched in cur:
        if SKIP_FETCHING_EXISTING or season_fetched:
            skipped.append(season)
            del need_fetch_seasons[season]
        else:
            need_fetch_seasons[season] = (min_match_id, max_match_id)

    if skipped:
        logger.debug(f"Skipping fetching seasons {', '.join(map(str, sorted(skipped)))} for player {player}")

    if len(need_fetch_seasons.keys() - {LAST_SEASON}) > 2:
        to_fetch = {}
        seasons_with_matches = fetch_seasons_with_matches(player)
        for season in seasons_with_matches:
            if season in need_fetch_seasons:
                to_fetch[season] = need_fetch_seasons.pop(season)
        to_insert = [
            [player, season]
            for season, ids in need_fetch_seasons.items()
            if ids is None and season != LAST_SEASON
        ]
        to_skip = [
            [player, season]
            for season, ids in need_fetch_seasons.items()
            if ids is not None and season != LAST_SEASON
        ]

        skipped = 0
        if to_insert:
            cur = db.executemany(
                "INSERT INTO `player`(`nickname`, `season`, `season_fetched`) VALUES (?, ?, 1);", to_insert,
            )
            skipped += cur.rowcount
        if to_skip:
            cur = db.executemany(
                "UPDATE `player` SET `season_fetched` = 1 WHERE `nickname` = ? AND `season` = ?;", to_skip,
            )
            skipped += cur.rowcount

        if skipped:
            db.commit()
            logger.debug(f"Skipped {skipped} seasons for player {player}")

        need_fetch_seasons = to_fetch

    for season, ids in need_fetch_seasons.items():
        if ids is None:
            db.execute("INSERT INTO `player` (`nickname`, `season`) VALUES (?, ?);", [player, season])
            fetch_matches_for_player(db, player, season, None, None)
        else:
            min_match_id, max_match_id = ids
            fetch_matches_for_player(db, player, season, max_match_id, None)
            fetch_matches_for_player(db, player, season, None, min_match_id)

        if season < LAST_SEASON:
            db.execute(
                "UPDATE `player` SET `season_fetched` = 1 WHERE `nickname` = ? AND `season` = ?;",
                [player, season]
            )


def get_vs_nicknames(db: sqlite3.Connection, player: str) -> set[str]:
    cur = db.execute(
        """
        SELECT mp2.player_nickname
        FROM match_player mp1
            LEFT OUTER JOIN match_player mp2 ON mp2.match_id = mp1.match_id
            INNER JOIN `match` m ON m.id = mp1.match_id
        WHERE mp1.player_nickname = ? AND mp2.player_nickname != ?
        ;
        """,
        [player, player],
    )

    return {row[0] for row in cur}


def run_bfs_from_player(db: sqlite3.Connection, player: str) -> None:
    queue: deque[tuple[str, int]] = deque([(player, 0)])
    seen = {player}
    skip = OFFSET_PLAYER is not None

    while queue:
        nickname, depth = queue.popleft()
        logger.info(
            f"Fetching player {nickname}, "
            f"processed: {len(seen) - len(queue)}, "
            f"queued: {len(queue)}, "
            f"depth: {depth}"
        )

        if not skip:
            fetch_for_player(db, nickname)

        if nickname == OFFSET_PLAYER:
            skip = False

        for other in sorted(get_vs_nicknames(db, nickname)):
            if other in seen:
                continue
            seen.add(other)
            queue.append((other, depth + 1))


def fetch_matches_from_id(db: sqlite3.Connection, from_id: int, season: int) -> None:
    if from_id == 0:
        cur = db.execute("SELECT MAX(`id`) FROM `match` WHERE season = ?;", [season])
        max_id, = cur.fetchone()
        if max_id is None:
            raise ValueError(f"No matches for season {season} found, \"from_id\" must be set")
        from_id = max_id
        logger.info(f"Last known match id for season {season} is {from_id}")

    while True:
        new_from_id = fetch_matches_between_ids(db, season, from_id, from_id + 170)
        if from_id == new_from_id:
            logger.info(f"{from_id} == {new_from_id}, probably no new matches?")
            break

        logger.info(f"New from_id: {new_from_id}")
        from_id = new_from_id


def main() -> None:
    db = sqlite3.connect("matches_mcsr-ranked.db")
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
        `season` INT NOT NULL,
        `date` DATETIME NOT NULL
    );
    CREATE TABLE IF NOT EXISTS `match_player` (
        `match_id` BIGINT NOT NULL,
        `player_nickname` VARCHAR(32) NOT NULL,
        PRIMARY KEY (`match_id`, `player_nickname`),
        FOREIGN KEY (`match_id`) REFERENCES `match`(`id`)
    );
    CREATE INDEX IF NOT EXISTS `idx_match_player_nickname` ON `match_player`(`player_nickname`);
    DROP INDEX IF EXISTS `idx_match_players`;
    DROP TABLE IF EXISTS `match_fts`;
    CREATE INDEX IF NOT EXISTS `idx_match_season_id` ON `match`(`season`, `id`);
    COMMIT;
    """)

    if RUN_BFS_FROM_PLAYER is not None:
        run_bfs_from_player(db, RUN_BFS_FROM_PLAYER)
    elif FETCH_MATCHES_FROM_ID is not None:
        fetch_matches_from_id(db, FETCH_MATCHES_FROM_ID, FETCH_MATCHES_SEASON)

    db.close()


if __name__ == "__main__":
    main()
