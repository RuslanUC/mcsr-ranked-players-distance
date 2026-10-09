import sqlite3
import time
import uuid
from datetime import datetime
from enum import IntEnum
from uuid import UUID

import niquests
from loguru import logger
from pydantic import BaseModel, RootModel


# RANKED_HOST = "https://api.mcsrranked.com"  # 5 seconds cache
RANKED_HOST = "https://mcsrranked.com/api"  # 30 seconds cache
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
FETCH_MATCHES_FROM_ID = 100876
FETCH_MATCHES_SEASON = 1
FETCH_MATCHES_WAIT_FOR_NEW = False

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


def fetch_matches_between_ids(db: sqlite3.Connection, season: int, after_id: int, before_id: int) -> int:
    global REQ_SINCE_LAST_RATE_LIMIT

    insert_matches: list[tuple[int, int, datetime, UUID | None]] = []
    insert_matches_players: list[tuple[UUID, int]] = []
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
            insert_matches.append((match.id, match.season, match.date, match.result.uuid))
            for match_player in match.players:
                insert_matches_players.append((match_player.uuid, match.id))

        if before_id - after_id > 100 and len(matches.root) == 100 and min_id > after_id:
            logger.warning(
                "Api returned number of matches that equals to the limit, but before-after has more than 100 matches. "
                f"Will fetch matches {after_id}-{min_id}."
            )
            fetch_matches_between_ids(db, season, after_id, min_id)

        break

    cur = db.executemany(
        "INSERT OR IGNORE INTO `match` (`id`, `season`, `date`, `winner`) VALUES (?, ?, ?, ?);",
        insert_matches,
    )
    matches_cnt = cur.rowcount
    cur = db.executemany(
        "INSERT OR IGNORE INTO `match_player` (`player_id`, `match_id`) VALUES (?, ?);",
        insert_matches_players,
    )
    logger.debug(f"Inserted {matches_cnt} matches and {cur.rowcount} matches-players")

    db.commit()

    return max_id


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
            if FETCH_MATCHES_WAIT_FOR_NEW:
                time.sleep(60 * 5)
                continue
            else:
                break

        logger.info(f"New from_id: {new_from_id}")
        from_id = new_from_id


def refetch_from_file(db: sqlite3.Connection, season: int, filename: str) -> None:
    batch_size = 99

    with open(filename, encoding="utf-8") as f:
        ids = list(set(map(int, map(str.strip, f))))

    if not ids:
        return

    ids.sort()
    fetched = 0

    for offset in range(0, len(ids), batch_size):
        batch = ids[offset: offset + batch_size]
        fetch_matches_between_ids(db, season, batch[0] - 1, batch[-1] + 1)
        fetched += len(batch)
        logger.info(
            f"Processed batch of {len(batch)} IDs ({batch[-1] - batch[0] + 1}), "
            f"from {batch[0]} to {batch[-1]}: {fetched}/{len(ids)}, {fetched / len(ids) * 100:.2f}%"
        )


def main() -> None:
    sqlite3.register_adapter(uuid.UUID, str)
    db = sqlite3.connect("matches_mcsr-ranked-new.db")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS `player` (
        `id` UUID NOT NULL PRIMARY KEY ,
        `nickname` VARCHAR(32) NOT NULL
    );
    CREATE TABLE IF NOT EXISTS `match` (
        `id` BIGINT PRIMARY KEY NOT NULL,
        `season` INT NOT NULL,
        `date` DATETIME NOT NULL,
        `winner` UUID DEFAULT NULL,
        FOREIGN KEY (`winner`) REFERENCES `player`(`id`)
    );
    CREATE TABLE IF NOT EXISTS `match_player` (
        `player_id` UUID NOT NULL,
        `match_id` BIGINT NOT NULL,
        PRIMARY KEY (`player_id`, `match_id`),
        FOREIGN KEY (`player_id`) REFERENCES `player`(`id`),
        FOREIGN KEY (`match_id`) REFERENCES `match`(`id`)
    );
    CREATE INDEX IF NOT EXISTS `idx_player_nickname` ON `player`(`nickname`);
    CREATE INDEX IF NOT EXISTS `idx_match_season_id` ON `match`(`season`, `id`);
    """)

    # fetch_matches_from_id(db, FETCH_MATCHES_FROM_ID, FETCH_MATCHES_SEASON)
    refetch_from_file(db, 1, "match_ids_1.txt")

    db.close()


if __name__ == "__main__":
    main()
