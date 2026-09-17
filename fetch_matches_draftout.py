import sqlite3
import time
from collections import deque
from datetime import datetime, UTC

import niquests
from loguru import logger
from pydantic import BaseModel, Field

RANKED_HOST = "https://draftoutmc.com"
RUN_BFS_FROM_PLAYER = "feinberg"


class MatchInfo(BaseModel):
    id: int = Field(alias="matchId")
    opponent_name: str = Field(alias="opponentName")
    completed_at: int = Field(alias="completedAt")


class MatchesSeries(BaseModel):
    points: list[MatchInfo]


def fetch_matches(db: sqlite3.Connection, player: str, season: int) -> None:
    insert_matches = []
    insert_matches_players = []
    min_id = None
    max_id = None
    retry = 0

    while True:
        try:
            resp = niquests.get(f"{RANKED_HOST}/api/stats/{player}/elo-series")
        except IOError:
            wait_seconds = min(30, 2 ** retry)
            logger.warning(f"Got connection error, re-trying in {wait_seconds} seconds")
            time.sleep(wait_seconds)
            retry += 1
            continue

        if resp.status_code == 429:
            wait_seconds = 60
            logger.warning(f"Got error 429, re-trying in {wait_seconds} seconds...")
            time.sleep(wait_seconds)
            continue

        resp_j = resp.json()
        matches = MatchesSeries(**resp_j)
        if not matches.points:
            break

        min_id = matches.points[-1].id
        max_id = matches.points[0].id

        for match in matches.points:
            min_id = min(min_id, match.id)
            max_id = max(max_id, match.id)
            # TODO: i forgot what this timestamp is
            insert_matches.append((match.id, season, datetime.fromtimestamp(1779583272101 / 1000, UTC)))
            insert_matches_players.append((match.id, player))
            insert_matches_players.append((match.id, match.opponent_name.lower()))

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


def fetch_for_player(db: sqlite3.Connection, player: str, season: int) -> None:
    db.execute("INSERT OR IGNORE INTO `player` (`nickname`, `season`) VALUES (?, ?);", [player, season])
    fetch_matches(db, player, season)


def get_vs_nicknames(db: sqlite3.Connection, player: str) -> set[str]:
    cur = db.execute(
        """
        SELECT mp2.player_nickname
        FROM match_player mp1
            LEFT OUTER JOIN match_player mp2 ON mp2.match_id = mp1.match_id
            INNER JOIN match m ON m.id = mp1.match_id
        WHERE mp1.player_nickname = ? AND mp2.player_nickname != ?
        ;
        """,
        [player, player],
    )

    return {row[0] for row in cur}


def run_bfs_from_player(db: sqlite3.Connection, player: str) -> None:
    queue: deque[tuple[str, int]] = deque([(player, 0)])
    seen = {player}

    while queue:
        nickname, depth = queue.popleft()
        logger.info(
            f"Fetching player {nickname}, "
            f"processed: {len(seen) - len(queue)}, "
            f"queued: {len(queue)}, "
            f"depth: {depth}"
        )

        fetch_for_player(db, nickname, 1)

        for other in sorted(get_vs_nicknames(db, nickname)):
            if other in seen:
                continue
            seen.add(other)
            queue.append((other, depth + 1))

def main() -> None:
    db = sqlite3.connect("matches_draftout.db")
    db.executescript(
        """
        BEGIN;
        CREATE TABLE IF NOT EXISTS `player` (
            `nickname`       VARCHAR(32) NOT NULL,
            `season`         INT NOT NULL,
            `min_match_id`   BIGINT DEFAULT NULL,
            `max_match_id`   BIGINT DEFAULT NULL,
            `season_fetched` BOOL NOT NULL DEFAULT FALSE,
            PRIMARY KEY (`nickname`, `season`)
        );
        CREATE TABLE IF NOT EXISTS `match` (
            `id`     BIGINT PRIMARY KEY NOT NULL,
            `season` INT NOT NULL,
            `date`   DATETIME NOT NULL
        );
        CREATE TABLE IF NOT EXISTS `match_player` (
            `match_id`        BIGINT NOT NULL,
            `player_nickname` VARCHAR(32) NOT NULL,
            PRIMARY KEY (`match_id`, `player_nickname`),
            FOREIGN KEY (`match_id`) REFERENCES `match` (`id`)
        );
        CREATE INDEX IF NOT EXISTS `idx_match_player_nickname` ON `match_player` (`player_nickname`);
        COMMIT;
        """
    )

    run_bfs_from_player(db, RUN_BFS_FROM_PLAYER)

    db.close()


if __name__ == "__main__":
    main()
