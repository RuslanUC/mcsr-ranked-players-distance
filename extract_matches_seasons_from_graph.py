import array
from os import environ

import igraph as ig


def main() -> None:
    app_type = environ.get("APP_TYPE", "mcsr-ranked")

    graph = ig.Graph.Read_Picklez(f"graph-{app_type}.pkl")
    with open(f"matches-{app_type}.bin", "wb") as f:
        f.write(array.array("I", graph.es["match"]).tobytes())
    with open(f"seasons-{app_type}.bin", "wb") as f:
        f.write(array.array("B", graph.es["season"]).tobytes())

    del graph.es["match"]
    del graph.es["season"]
    graph.write_picklez(f"graph-{app_type}-trimmed.pkl")


if __name__ == "__main__":
    main()
