import sqlite3
import timeit
from typing import Literal

from graphqlite import Graph


def main() -> None:
    db = sqlite3.connect("matches.db")
    cur = db.execute("SELECT `players` FROM `match`;")
    all_players = [row[0] for row in cur.fetchall()]
    db.close()

    seen_players = set()
    bulk_nodes: list[tuple[str, dict, Literal["Player"]]] = []
    bulk_edges: list[tuple[str, str, dict, Literal["LINK"]]] = []

    for players_separated in all_players:
        players = list(filter(bool, players_separated.split("|")))
        if len(players) != 2:
            continue
        for player in players:
            if player in seen_players:
                continue
            seen_players.add(player)
            bulk_nodes.append((player, {}, "Player"))
        bulk_edges.append((players[0], players[1], {}, "LINK"))

    g = Graph(":memory:")
    g.insert_graph_bulk(bulk_nodes, bulk_edges)
    del seen_players, bulk_nodes, bulk_edges

    print("Searching...")
    print(timeit.timeit(lambda: g.shortest_path("feinberg", "fatchudlolcow", weight_property=None), number=100))

    print(g.shortest_path("fatchudlolcow", "feinberg", weight_property=None))

if __name__ == "__main__":
    main()
