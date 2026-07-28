import sqlite3

import igraph as ig


def main() -> None:
    db = sqlite3.connect("matches.db")
    cur = db.execute("SELECT `id`, `players`, `season` FROM `match`;")
    all_players = cur.fetchall()
    db.close()

    edges: dict[tuple[str, str], tuple[int, int]] = {}
    seen_players = set()

    g = ig.Graph()

    for match_id, players_separated, season in all_players:
        players = list(filter(bool, players_separated.split("|")))
        if len(players) != 2:
            continue
        for player in players:
            if player not in seen_players:
                seen_players.add(player)
                g.add_vertex(player)
        tup = players[0], players[1]
        tup_rev = players[1], players[0]
        if tup in edges:
            latest_match, _ = edges[tup]
            if match_id > latest_match:
                edges[tup] = match_id, season
        elif tup_rev in edges:
            latest_match, _ = edges[tup_rev]
            if match_id > latest_match:
                edges[tup_rev] = match_id, season
        else:
            edges[tup] = match_id, season

    edges_to_add = []
    attrs_to_add = {"match": [], "season": []}

    for uv, (match_id, season) in edges.items():
        edges_to_add.append(uv)
        attrs_to_add["match"].append(match_id)
        attrs_to_add["season"].append(season)

    g.add_edges(edges_to_add, attrs_to_add)

    del seen_players, edges

    g.write_picklez("graph.pkl")

if __name__ == "__main__":
    main()
