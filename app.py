from itertools import pairwise

from flask import Flask
import igraph as ig


app = Flask("mcsr-player-distance")
graph = ig.Graph.Read_Picklez("graph.pkl")


@app.get("/distance/<string:player1>/<string:player2>")
def get_players_distance(player1: str, player2: str) -> dict:
    path = graph.get_shortest_path(player1, player2)

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

    return {
        "matches": matches,
    }


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080)
