import string
from itertools import pairwise

from diskcache import Cache
from flask import Flask
import igraph as ig

NICKNAME_ALLOWED_CHARACTERS = {*string.ascii_letters, *string.digits, "_"}

app = Flask("mcsr-player-distance")
graph = ig.Graph.Read_Picklez("graph.pkl")
cache = Cache("cache-matches")


def _nickname_is_valid(nickname: str) -> bool:
    if len(nickname) < 2 or len(nickname) > 16:
        return False
    return all(ch in NICKNAME_ALLOWED_CHARACTERS for ch in nickname)


@app.get("/distance/<string:player1>/<string:player2>")
def get_players_distance(player1: str, player2: str) -> dict:
    if not _nickname_is_valid(player1) or not _nickname_is_valid(player2):
        return {"matches": []}

    matches_cache_key = "resp", player1, player2
    if cached_matches := cache.get(("resp", player1, player2)):
        return {"matches": cached_matches}

    rev = False
    if player2 > player1:
        rev = True
        player1, player2 = player2, player1

    path_cache_key = "path", player1, player2
    if (path := cache.get(path_cache_key)) is None:
        try:
            path = graph.get_shortest_path(player1, player2)
        except ValueError:
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

    cache[matches_cache_key] = matches

    return {
        "matches": matches,
    }


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080)
