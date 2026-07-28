import string
from itertools import pairwise

from diskcache import Cache
from flask import Flask, Response
import igraph as ig

NICKNAME_ALLOWED_CHARACTERS = {*string.ascii_letters, *string.digits, "_"}

app = Flask("mcsr-player-distance")
graph = ig.Graph.Read_Picklez("graph.pkl")
cache = Cache("cache-matches")


@app.after_request
def set_cors_headers(response: Response) -> Response:
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "*"
    response.headers["Content-Security-Policy"] = "connect-src *;"
    return response


def _nickname_is_valid(nickname: str) -> bool:
    if len(nickname) < 2 or len(nickname) > 16:
        return False
    return all(ch in NICKNAME_ALLOWED_CHARACTERS for ch in nickname)


@app.get("/distance/<string:player1>/<string:player2>")
def get_players_distance(player1: str, player2: str) -> dict:
    if not _nickname_is_valid(player1):
        return {"matches": [], "additional_info": "Nickname of first player is invalid"}

    if not _nickname_is_valid(player2):
        return {"matches": [], "additional_info": "Nickname of second player is invalid"}

    player1 = player1.lower()
    player2 = player2.lower()

    response_cache_key = "full-resp", player1, player2
    if cached_response := cache.get(response_cache_key):
        return cached_response

    info = None
    rev = False
    if player2 > player1:
        rev = True
        player1, player2 = player2, player1

    path_cache_key = "path", player1, player2
    if (path := cache.get(path_cache_key)) is None:
        try:
            path = graph.get_shortest_path(player1, player2)
        except ValueError:
            try:
                graph.vs.find(player1)
            except ValueError:
                info = f"Unknown player \"{player1}\". "
            else:
                info = f"Unknown player \"{player2}\". "
            info += "You can find more info here: https://github.com/RuslanUC/mcsr-ranked-players-distance."
            path = []
        cache[path_cache_key] = path

    if rev:
        path.reverse()

    matches = []
    for v1, v2 in pairwise(path):
        p1 = graph.vs[v1]["name"]
        p2 = graph.vs[v2]["name"]
        edge = graph.es[graph.get_eid(v1, v2)]
        matches.append({
            "id": edge["match"],
            "season": edge["season"],
            "player1": p1,
            "player2": p2,
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
