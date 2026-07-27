import sqlite3

import networkx as nx

from main import PLAYER1, PLAYER2


def main() -> None:
    db = sqlite3.connect("matches.db")
    cur = db.execute("SELECT `players` FROM `match`;")
    all_players = [row[0] for row in cur.fetchall()]
    db.close()

    g = nx.Graph()
    for players_separated in all_players:
        players = list(filter(bool, players_separated.split("|")))
        if len(players) != 2:
            continue
        g.add_edge(players[0], players[1])

    print("Shortest:")
    for path in nx.all_shortest_paths(g, PLAYER1, PLAYER2):
        print(path)


if __name__ == "__main__":
    main()
