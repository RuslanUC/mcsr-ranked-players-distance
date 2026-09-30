#pragma once

#include <stddef.h>
#include <stdint.h>

#define BFS_MAX_DEPTH UINT16_MAX

typedef struct {
    const char* key;
    uint32_t value;
} NicknameToVertex;

typedef struct {
    uint32_t key;
    uint32_t value;
} VertexToComponent;

typedef struct Graph {
    uint32_t n;
    uint32_t m;

    int use_mmap;
    size_t nicknames_size;

    uint32_t* offsets; // n + 1
    uint32_t* neighbors; // m * 2

    char* nicknames_buf;
    NicknameToVertex* nickname_to_vertex; // n
    uint32_t* vertex_to_nickname_offset; // n
    uint32_t* match_ids; // m
    uint8_t* match_seasons; // m
    uint32_t* edge_ids; // m * 2
    // component ids start at 1
    VertexToComponent* vertex_to_component;
} Graph;

typedef struct BFSContext {
    Graph* g;

    uint32_t* state_fwd; // high 16 bits: generation; low 16 bits: distance
    uint32_t* state_bwd;

    uint32_t* queue_fwd;
    uint32_t* queue_bwd;

    uint32_t generation;
} BFSContext;

Graph* graph_load(const char* filename);
Graph* graph_load_mmap(const char* filename);
void graph_free(Graph* g);

BFSContext* bfs_create(Graph* g);
void bfs_free(BFSContext* ctx);

uint32_t bidirectional_bfs(BFSContext* ctx, uint32_t source, uint32_t target, uint32_t max_depth) ;
size_t reconstruct_path(BFSContext* ctx, uint32_t source, uint32_t target, uint32_t meeting, uint32_t* out_vertices, uint32_t* out_edges);
size_t shortest_path(BFSContext* ctx, uint32_t source, uint32_t target, uint32_t max_depth, uint32_t* out_vertices, uint32_t* out_edges);
