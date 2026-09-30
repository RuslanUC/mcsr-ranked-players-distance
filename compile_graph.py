import array
import struct
from os import environ
from pathlib import Path
from typing import cast, Iterable

import igraph as ig


def main() -> None:
    app_type = environ.get("APP_TYPE", "mcsr-ranked")
    out_dir = Path(f"graph/{app_type}")
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Reading graph...")
    graph = ig.Graph.Read_Picklez(f"graph-{app_type}.pkl")

    with open(out_dir / "metadata.bin", "wb") as f:
        f.write(struct.pack("<II", graph.vcount(), graph.ecount()))

    print("Extracting matches...")
    with open(out_dir / "matches.bin", "wb") as f:
        f.write(array.array("I", graph.es["match"]).tobytes())

    print("Extracting seasons...")
    with open(out_dir / "seasons.bin", "wb") as f:
        f.write(array.array("B", graph.es["season"]).tobytes())

    print("Extracting players' nicknames...")
    with open(out_dir / "players.bin", "w") as f:
        f.write("\0".join(graph.vs["name"]))
        f.write("\0")

    print("Building csr...")

    offsets = [0] * (graph.vcount() + 1)
    neighbors = [0] * (graph.ecount() * 2)

    for edge in cast(Iterable[ig.Edge], graph.es):
        offsets[edge.source + 1] += 1
        offsets[edge.target + 1] += 1

    for v in range(1, graph.vcount() + 1):
        offsets[v] += offsets[v - 1]

    cursor = [0] * graph.vcount()
    for v in range(graph.vcount()):
        cursor[v] = offsets[v]

    edge_ids = [0] * (graph.ecount() * 2)

    for edge in cast(Iterable[ig.Edge], graph.es):
        eid = edge.index

        pos = cursor[edge.source]
        neighbors[pos] = edge.target
        edge_ids[pos] = eid
        cursor[edge.source] += 1

        pos = cursor[edge.target]
        neighbors[pos] = edge.source
        edge_ids[pos] = eid
        cursor[edge.target] += 1

    print("Saving offsets...")
    with open(out_dir / "offsets.bin", "wb") as f:
        f.write(array.array("I", offsets).tobytes())

    print("Saving neighbors...")
    with open(out_dir / "neighbors.bin", "wb") as f:
        f.write(array.array("I", neighbors).tobytes())

    print("Saving edge ids...")
    with open(out_dir / "edge_ids.bin", "wb") as f:
        f.write(array.array("I", edge_ids).tobytes())

    print("Calculated components...")
    components = sorted(graph.connected_components(mode="weak"), key=lambda comp: len(comp))
    del components[-1]
    with open(out_dir / "components.bin", "wb") as f:
        for component in components:
            f.write(struct.pack("<I", len(component)))
            f.write(array.array("I", component).tobytes())


if __name__ == "__main__":
    main()
