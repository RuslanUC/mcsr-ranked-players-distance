import string
from os import environ

from diskcache import Cache
from flask import Flask, Response, request
from pymcsrd_c import MatchesGraph

NICKNAME_ALLOWED_CHARACTERS = {*string.ascii_letters, *string.digits, "_"}
APP_TYPE = environ.get("APP_TYPE", "mcsr-ranked")

app = Flask("mcsr-player-distance")
cache = Cache("cache-matches")
graph = MatchesGraph(f"graph/{APP_TYPE}", mmap=True)
players_count = graph.vcount()
matches_count = graph.ecount()


@app.after_request
def set_cors_headers(response: Response) -> Response:
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "*"
    if request.path.startswith("/distance"):
        response.headers["Cache-Control"] = "max-age=14400,public,stale-if-error=43200"
    return response


def _nickname_is_valid(nickname: str) -> bool:
    if len(nickname) < 2 or len(nickname) > 16:
        return False
    return all(ch in NICKNAME_ALLOWED_CHARACTERS for ch in nickname)


@app.get("/stats")
def get_graph_stats() -> dict:
    return {"players": players_count, "matches": matches_count}


@app.get("/distance/<string:player1>/<string:player2>")
def get_players_distance(player1: str, player2: str) -> dict:
    if not _nickname_is_valid(player1):
        return {"matches": [], "additional_info": "Nickname of first player is invalid"}

    if not _nickname_is_valid(player2):
        return {"matches": [], "additional_info": "Nickname of second player is invalid"}

    player1 = player1.lower()
    player2 = player2.lower()

    response_cache_key = f"full-resp:{APP_TYPE}:{player1}-{player2}".encode("latin1")
    if cached_response := cache.get(response_cache_key):
        return cached_response

    info = None
    rev = False
    if player2 > player1:
        rev = True
        player1, player2 = player2, player1

    path_cache_key = f"path:{APP_TYPE}:{player1}-{player2}".encode("latin1")
    if (path := cache.get(path_cache_key)) is None:
        path = graph.get_path(player1, player2)

        if not path:
            info = ""
            if not graph.has_player(player1):
                info = f"Unknown player \"{player1}\". "
            elif not graph.has_player(player2):
                info = f"Unknown player \"{player2}\". "

            info += (
                "You may have spelt nickname wrong or matches of this player are not scanned yet. "
                "Right now matches from season 12 are not scanned."
            )

        cache[path_cache_key] = path

    if rev:
        path.reverse()

    matches = []
    for player1, player2, match_id, match_season in path:
        matches.append({
            "id": match_id,
            "season": match_season,
            "player1": player1,
            "player2": player2,
        })

    result = {
        "matches": matches,
        "additional_info": info,
    }

    cache[response_cache_key] = result

    return result


@app.get("/health")
def healthcheck() -> dict:
    return {"ok": True}


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8888)
