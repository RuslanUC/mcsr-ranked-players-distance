import sqlite3
from os import environ

import igraph as ig
from tqdm import tqdm


def main() -> None:
    app_type = environ.get("APP_TYPE", "mcsr-ranked")

    edges: dict[tuple[str, str], tuple[int, int]] = {}
    seen_players = set()

    g = ig.Graph()

    print("Selecting matches...")
    with sqlite3.connect(f"matches_{app_type}.db") as db:
        cur = db.execute("""
        SELECT mp1.match_id, m.season, mp1.player_nickname, mp2.player_nickname
        FROM `match_player` mp1
            INNER JOIN `match_player` mp2 on mp2.match_id = mp1.match_id AND mp1.player_nickname < mp2.player_nickname
            INNER JOIN `match` m ON mp1.match_id = m.id;
        """)

        for match_id, season, player1, player2 in tqdm(cur, desc="Adding matches to the graph"):
            for player in (player1, player2):
                if player not in seen_players:
                    seen_players.add(player)
                    g.add_vertex(player)

            key = player1, player2
            if key not in edges or match_id > edges[key][0]:
                edges[key] = match_id, season

    edges_to_add = []
    attrs_to_add = {"match": [], "season": []}

    for uv, (match_id, season) in tqdm(edges.items(), desc="Adding metadata"):
        edges_to_add.append(uv)
        attrs_to_add["match"].append(match_id)
        attrs_to_add["season"].append(season)

    print("Adding matches...")
    g.add_edges(edges_to_add, attrs_to_add)

    del edges

    print("Saving graph...")
    g.write_picklez(f"graph-{app_type}.pkl")

if __name__ == "__main__":
    main()
