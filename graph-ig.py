import sqlite3
import timeit

import igraph as ig


def main() -> None:
    db = sqlite3.connect("matches.db")
    cur = db.execute("SELECT `players` FROM `match`;")
    all_players = [row[0] for row in cur.fetchall()]
    db.close()

    bulk_edges: list[tuple[str, str]] = []
    seen = set()

    g = ig.Graph()

    for players_separated in all_players:
        players = list(filter(bool, players_separated.split("|")))
        if len(players) != 2:
            continue
        for player in players:
            if player not in seen:
                seen.add(player)
                g.add_vertex(player)
        bulk_edges.append((players[0], players[1]))

    g.add_edges(bulk_edges)

    del bulk_edges

    print("Searching...")
    print(timeit.timeit(lambda: g.get_shortest_path("feinberg", "fatchudlolcow"), number=100))

    print(g.get_shortest_path("fatchudlolcow", "feinberg"))

    print(g.vs[1])

if __name__ == "__main__":
    main()
