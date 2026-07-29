import array
import igraph as ig


def main() -> None:
    graph = ig.Graph.Read_Picklez("graph.pkl")
    with open("matches.bin", "wb") as f:
        f.write(array.array("I", graph.es["match"]).tobytes())
    with open("seasons.bin", "wb") as f:
        f.write(array.array("B", graph.es["season"]).tobytes())

    del graph.es["match"]
    del graph.es["season"]
    graph.write_picklez("graph-trimmed.pkl")


if __name__ == "__main__":
    main()
