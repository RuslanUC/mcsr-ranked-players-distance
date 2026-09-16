#define _FILE_OFFSET_BITS 64

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#include "stb_ds.h"
#include "lib.h"


int main(int argc, char** argv) {
    if(argc != 4) {
        fprintf(stderr, "Usage: %s /path/to/graph/directory from-player to-player\n", argv[0]);
        return 1;
    }

    Graph* g = graph_load(argv[1]);

    if(!g)
        return 1;

    printf("Loaded graph: %u vertices, %u edges\n", g->n, g->m);

    BFSContext* ctx = bfs_create(g);

    if(!ctx) {
        fprintf(stderr, "Failed allocating BFS context\n");
        graph_free(g);
        return 1;
    }

    ptrdiff_t source_idx = shgeti(g->nickname_to_vertex, argv[2]);
    if(source_idx < 0) {
        fprintf(stderr, "Player %s is not in graph\n", argv[2]);
        bfs_free(ctx);
        graph_free(g);
        return 1;
    }

    ptrdiff_t target_idx = shgeti(g->nickname_to_vertex, argv[3]);
    if(target_idx < 0) {
        fprintf(stderr, "Player %s is not in graph\n", argv[3]);
        bfs_free(ctx);
        graph_free(g);
        return 1;
    }

    uint32_t source = g->nickname_to_vertex[source_idx].value;
    uint32_t target = g->nickname_to_vertex[target_idx].value;

    const uint32_t max_depth = 10;
    uint32_t* path_vertices = malloc(((size_t)max_depth + 1) * sizeof(uint32_t));
    uint32_t* path_edges = malloc(((size_t)max_depth + 1) * sizeof(uint32_t));

    if(!path_vertices || !path_edges) {
        perror("malloc");
        free(path_vertices);
        free(path_edges);
        bfs_free(ctx);
        graph_free(g);
        return 1;
    }

    size_t path_len = shortest_path(ctx, source, target, max_depth, path_vertices, path_edges);

    if(path_len == 0) {
        printf("No path\n");
    } else {
        printf("Shortest path: %zu vertices, %zu edges\n", path_len, path_len - 1);

        for(size_t i = 0; i < path_len; ++i) {
            if(i > 0 && i < path_len) {
                printf("--[%u:%u]--> ", g->match_seasons[path_edges[i - 1]], g->match_ids[path_edges[i - 1]]);
            }
            printf("%s%s", (g->nicknames_buf + g->vertex_to_nickname_offset[path_vertices[i]]), i + 1 == path_len ? "\n" : " ");
        }
    }

    free(path_vertices);
    free(path_edges);
    bfs_free(ctx);
    graph_free(g);

    return 0;
}
