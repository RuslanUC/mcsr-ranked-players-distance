#define _POSIX_C_SOURCE 200809L
#define _FILE_OFFSET_BITS 64

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>

#define STB_DS_IMPLEMENTATION
#include "stb_ds.h"

#include "lib.h"

#define TMP_STR_BUF_SIZE 4096
static char tmp_str_buf[TMP_STR_BUF_SIZE] = {0};

static int read_exact(FILE* f, void* buf, size_t size) {
    return fread(buf, 1, size, f) == size;
}

static FILE* fopen_in_dir(const char* directory, const char* filename) {
    const int length = snprintf(tmp_str_buf, TMP_STR_BUF_SIZE, "%s/%s", directory, filename);
    if(length < 0 || length >= TMP_STR_BUF_SIZE)
        return NULL;

    FILE* f = fopen(tmp_str_buf, "rb");
    if(!f) {
        perror(filename);
        return NULL;
    }

    return f;
}

static int load_exact_file(const char* directory, const char* filename, size_t size, int use_mmap, void** result) {
    FILE* f = fopen_in_dir(directory, filename);
    if(!f)
        return 0;

    struct stat st;
    if(fstat(fileno(f), &st) != 0 || st.st_size < 0 || (uintmax_t)st.st_size < (uintmax_t)size) {
        fprintf(stderr, "%s is shorter than expected\n", filename);
        fclose(f);
        return 0;
    }

    if(size == 0) {
        *result = NULL;
        fclose(f);
        return 1;
    }

    if(use_mmap) {
        void* mapping = mmap(NULL, size, PROT_READ, MAP_SHARED, fileno(f), 0);
        fclose(f);

        if(mapping == MAP_FAILED) {
            perror(filename);
            return 0;
        }

        *result = mapping;
        return 1;
    }

    void* data = malloc(size);
    if(!data) {
        perror("malloc");
        fclose(f);
        return 0;
    }

    const int success = read_exact(f, data, size);
    fclose(f);

    if(!success) {
        fprintf(stderr, "Failed reading %s\n", filename);
        free(data);
        return 0;
    }

    *result = data;
    return 1;
}

static Graph* graph_load_impl(const char* filename, int use_mmap) {
    uint32_t n, m;

    {
        FILE* f = fopen_in_dir(filename, "metadata.bin");
        if(!f)
            return NULL;

        if(!read_exact(f, &n, sizeof(n)) || !read_exact(f, &m, sizeof(m))) {
            fprintf(stderr, "Invalid metadata.bin\n");
            fclose(f);
            return NULL;
        }

        fclose(f);
    }

    Graph* g = calloc(1, sizeof(*g));
    if(!g) {
        perror("calloc");
        return NULL;
    }

    g->n = n;
    g->m = m;
    g->use_mmap = use_mmap;

    if(m > UINT32_MAX / 2) {
        fprintf(stderr, "Graph has too many edges\n");
        graph_free(g);
        return NULL;
    }

    g->vertex_to_nickname_offset = malloc((size_t)n * sizeof(uint32_t));

    if(n > 0 && !g->vertex_to_nickname_offset) {
        perror("malloc");
        graph_free(g);
        return NULL;
    }

    if(!load_exact_file(filename, "offsets.bin", ((size_t)n + 1) * sizeof(uint32_t), use_mmap, (void**)&g->offsets)) {
        graph_free(g);
        return NULL;
    }

    if(g->offsets[0] != 0 || g->offsets[n] != m * 2) {
        fprintf(stderr, "Invalid CSR offsets\n");
        graph_free(g);
        return NULL;
    }

    for(uint32_t v = 0; v < n; ++v) {
        if(g->offsets[v] > g->offsets[v + 1]) {
            fprintf(stderr, "Invalid CSR offsets at vertex %u\n", v);
            graph_free(g);
            return NULL;
        }
    }

    if(!load_exact_file(filename, "neighbors.bin", (size_t)m * 2 * sizeof(uint32_t), use_mmap, (void**)&g->neighbors)) {
        graph_free(g);
        return NULL;
    }

    for(uint32_t i = 0; i < m * 2; ++i) {
        if(g->neighbors[i] >= n) {
            fprintf(stderr, "Invalid neighbor at edge %u\n", i);
            graph_free(g);
            return NULL;
        }
    }

    if(!load_exact_file(filename, "matches.bin", (size_t)m * sizeof(uint32_t), use_mmap, (void**)&g->match_ids) ||
       !load_exact_file(filename, "seasons.bin", (size_t)m * sizeof(uint8_t), use_mmap, (void**)&g->match_seasons) ||
       !load_exact_file(filename, "edge_ids.bin", (size_t)m * 2 * sizeof(uint32_t), use_mmap, (void**)&g->edge_ids)) {
        graph_free(g);
        return NULL;
    }

    {
        FILE* f = fopen_in_dir(filename, "players.bin");
        if(!f) {
            graph_free(g);
            return NULL;
        }

        struct stat st;
        if(fstat(fileno(f), &st) != 0 || st.st_size < 0 || st.st_size > 1024 * 1024 * 2) {
            fprintf(stderr, "players.bin exceeds 2MB\n");
            fclose(f);
            graph_free(g);
            return NULL;
        }
        const size_t file_size = (size_t)st.st_size;
        fclose(f);
        g->nicknames_size = file_size;

        if(!load_exact_file(filename, "players.bin", file_size, use_mmap, (void**)&g->nicknames_buf)) {
            graph_free(g);
            return NULL;
        }

        const char* buf = g->nicknames_buf;

        for(uint32_t i = 0; i < n; ++i) {
            if(buf >= g->nicknames_buf + file_size) {
                fprintf(stderr, "Invalid players.bin has less nicknames then vertices\n");
                graph_free(g);
                return NULL;
            }

            g->vertex_to_nickname_offset[i] = (uint32_t)(buf - g->nicknames_buf);
            shput(g->nickname_to_vertex, buf, i);
            buf += strlen(buf) + 1;
        }
    }

    {
        FILE* f = fopen_in_dir(filename, "components.bin");
        if(!f) {
            graph_free(g);
            return NULL;
        }

        uint32_t num_vertices = 0;
        uint32_t component_id = 1;
        while(fread(&num_vertices, sizeof(num_vertices), 1, f) == 1) {
            uint32_t vertex_id;
            for(uint32_t i = 0; i < num_vertices; ++i) {
                if(fread(&vertex_id, sizeof(vertex_id), 1, f) != 1) {
                    fprintf(stderr, "Unexpected EOF when reading components.bin\n");
                    graph_free(g);
                    return NULL;
                }
                hmput(g->vertex_to_component, vertex_id, component_id);
            }

            component_id++;
        }

        fclose(f);
    }

    return g;
}

Graph* graph_load(const char* filename) {
    return graph_load_impl(filename, 0);
}

Graph* graph_load_mmap(const char* filename) {
    return graph_load_impl(filename, 1);
}

void graph_free(Graph* g) {
    if(!g)
        return;

    if(g->use_mmap) {
        if(g->offsets)
            munmap(g->offsets, ((size_t)g->n + 1) * sizeof(uint32_t));
        if(g->neighbors)
            munmap(g->neighbors, (size_t)g->m * 2 * sizeof(uint32_t));
        if(g->match_ids)
            munmap(g->match_ids, (size_t)g->m * sizeof(uint32_t));
        if(g->match_seasons)
            munmap(g->match_seasons, (size_t)g->m * sizeof(uint8_t));
        if(g->edge_ids)
            munmap(g->edge_ids, (size_t)g->m * 2 * sizeof(uint32_t));
    } else {
        free(g->offsets);
        free(g->neighbors);
        free(g->match_ids);
        free(g->match_seasons);
        free(g->edge_ids);
    }
    free(g->vertex_to_nickname_offset);
    shfree(g->nickname_to_vertex);
    if(g->use_mmap) {
        if(g->nicknames_buf)
            munmap(g->nicknames_buf, g->nicknames_size);
    } else {
        free(g->nicknames_buf);
    }
    hmfree(g->vertex_to_component);
    free(g);
}

BFSContext* bfs_create(Graph* g) {
    BFSContext* ctx = calloc(1, sizeof(*ctx));
    if(!ctx)
        return NULL;

    ctx->g = g;

    size_t n = g->n;

    ctx->state_fwd = calloc(n, sizeof(uint32_t));
    ctx->state_bwd = calloc(n, sizeof(uint32_t));

    ctx->queue_fwd = malloc(n * sizeof(uint32_t));
    ctx->queue_bwd = malloc(n * sizeof(uint32_t));

    if(!ctx->state_fwd || !ctx->state_bwd || !ctx->queue_fwd || !ctx->queue_bwd) {
        bfs_free(ctx);
        return NULL;
    }

    ctx->generation = 0;

    return ctx;
}

void bfs_free(BFSContext* ctx) {
    if(!ctx)
        return;

    free(ctx->state_fwd);
    free(ctx->state_bwd);
    free(ctx->queue_fwd);
    free(ctx->queue_bwd);
    free(ctx);
}

uint32_t bidirectional_bfs(BFSContext* ctx, uint32_t source, uint32_t target, uint32_t max_depth) {
    Graph* g = ctx->g;

    if(source >= g->n || target >= g->n)
        return UINT32_MAX;

    if(source == target)
        return source;

    VertexToComponent* vertex_to_component = ctx->g->vertex_to_component;

    ptrdiff_t source_idx;
    ptrdiff_t target_idx;
    hmget_ts(vertex_to_component, source, source_idx);
    hmget_ts(vertex_to_component, target, target_idx);
    const uint32_t source_component_id = source_idx >= 0 ? vertex_to_component[source_idx].value : 0;
    const uint32_t target_component_id = target_idx >= 0 ? vertex_to_component[target_idx].value : 0;

    if(source_component_id != target_component_id)
        return UINT32_MAX;

    ++ctx->generation;

    if(ctx->generation > BFS_MAX_DEPTH) {
        memset(ctx->state_fwd, 0, (size_t)g->n * sizeof(uint32_t));
        memset(ctx->state_bwd, 0, (size_t)g->n * sizeof(uint32_t));
        ctx->generation = 1;
    }

    uint32_t gen = ctx->generation;
    uint32_t generation_bits = gen << 16;

    size_t head_fwd = 0;
    size_t tail_fwd = 0;

    size_t head_bwd = 0;
    size_t tail_bwd = 0;

    ctx->queue_fwd[tail_fwd++] = source;
    ctx->queue_bwd[tail_bwd++] = target;

    ctx->state_fwd[source] = generation_bits;
    ctx->state_bwd[target] = generation_bits;

    uint32_t depth_fwd = 0;
    uint32_t depth_bwd = 0;

    uint32_t best_meeting = UINT32_MAX;
    uint32_t best_distance = UINT32_MAX;

    uint64_t frontier_edges_fwd = (uint64_t)g->offsets[source + 1] - g->offsets[source];
    uint64_t frontier_edges_bwd = (uint64_t)g->offsets[target + 1] - g->offsets[target];

    for(;;) {
        uint32_t next_fwd_depth = depth_fwd + 1;
        uint32_t next_bwd_depth = depth_bwd + 1;

        if(best_distance != UINT32_MAX && next_fwd_depth + next_bwd_depth >= best_distance) {
            break;
        }

        if(head_fwd >= tail_fwd && head_bwd >= tail_bwd) {
            break;
        }

        int expand_fwd;

        if(head_bwd >= tail_bwd) {
            expand_fwd = 1;
        } else if(head_fwd >= tail_fwd) {
            expand_fwd = 0;
        } else {
            expand_fwd = frontier_edges_fwd <= frontier_edges_bwd;
        }

        if(expand_fwd) {
            if(depth_fwd >= max_depth)
                break;

            size_t level_end = tail_fwd;
            uint32_t next_depth = depth_fwd + 1;
            uint64_t next_frontier_edges = 0;

            while(head_fwd < level_end) {
                uint32_t v = ctx->queue_fwd[head_fwd++];

                uint32_t begin = g->offsets[v];
                uint32_t end = g->offsets[v + 1];

                for(uint32_t i = begin; i < end; ++i) {
                    uint32_t u = g->neighbors[i];

                    if((ctx->state_fwd[u] >> 16) == gen)
                        continue;

                    ctx->state_fwd[u] = generation_bits | next_depth;

                    if((ctx->state_bwd[u] >> 16) == gen) {
                        uint32_t candidate = next_depth + (ctx->state_bwd[u] & BFS_MAX_DEPTH);

                        if(candidate <= max_depth &&
                            candidate < best_distance) {
                            best_distance = candidate;
                            best_meeting = u;
                        }
                    }

                    ctx->queue_fwd[tail_fwd++] = u;
                    next_frontier_edges += (uint64_t)g->offsets[u + 1] - g->offsets[u];
                }
            }

            depth_fwd = next_depth;
            frontier_edges_fwd = next_frontier_edges;
        } else {
            if(depth_bwd >= max_depth)
                break;

            size_t level_end = tail_bwd;
            uint32_t next_depth = depth_bwd + 1;
            uint64_t next_frontier_edges = 0;

            while(head_bwd < level_end) {
                uint32_t v = ctx->queue_bwd[head_bwd++];

                uint32_t begin = g->offsets[v];
                uint32_t end = g->offsets[v + 1];

                for(uint32_t i = begin; i < end; ++i) {
                    uint32_t u = g->neighbors[i];

                    if((ctx->state_bwd[u] >> 16) == gen)
                        continue;

                    ctx->state_bwd[u] = generation_bits | next_depth;

                    if((ctx->state_fwd[u] >> 16) == gen) {
                        uint32_t candidate = (ctx->state_fwd[u] & BFS_MAX_DEPTH) + next_depth;

                        if(candidate <= max_depth &&
                            candidate < best_distance) {
                            best_distance = candidate;
                            best_meeting = u;
                        }
                    }

                    ctx->queue_bwd[tail_bwd++] = u;
                    next_frontier_edges += (uint64_t)g->offsets[u + 1] - g->offsets[u];
                }
            }

            depth_bwd = next_depth;
            frontier_edges_bwd = next_frontier_edges;
        }
    }

    return best_meeting;
}

size_t reconstruct_path(BFSContext* ctx, uint32_t source, uint32_t target, uint32_t meeting, uint32_t* out_vertices, uint32_t* out_edges) {
    Graph* g = ctx->g;
    const uint32_t generation_bits = ctx->generation << 16;
    size_t vertex_count = 0;
    uint32_t v = meeting;

    out_vertices[vertex_count++] = v;

    while(v != source) {
        uint32_t depth = ctx->state_fwd[v] & BFS_MAX_DEPTH;
        int found = 0;

        for(uint32_t i = g->offsets[v]; i < g->offsets[v + 1]; ++i) {
            uint32_t u = g->neighbors[i];
            uint32_t state = ctx->state_fwd[u];

            if((state & UINT32_C(0xffff0000)) == generation_bits && (state & BFS_MAX_DEPTH) + 1 == depth) {
                out_edges[vertex_count - 1] = g->edge_ids[i];
                out_vertices[vertex_count++] = u;
                v = u;
                found = 1;
                break;
            }
        }

        if(!found)
            return 0;
    }

    for(size_t i = 0, j = vertex_count - 1; i < j; ++i, --j) {
        uint32_t tmp = out_vertices[i];
        out_vertices[i] = out_vertices[j];
        out_vertices[j] = tmp;
    }

    if(vertex_count > 1) {
        for(size_t i = 0, j = vertex_count - 2; i < j; ++i, --j) {
            uint32_t tmp = out_edges[i];
            out_edges[i] = out_edges[j];
            out_edges[j] = tmp;
        }
    }

    v = meeting;

    while(v != target) {
        uint32_t depth = ctx->state_bwd[v] & BFS_MAX_DEPTH;
        int found = 0;

        for(uint32_t i = g->offsets[v]; i < g->offsets[v + 1]; ++i) {
            uint32_t u = g->neighbors[i];
            uint32_t state = ctx->state_bwd[u];

            if((state & UINT32_C(0xffff0000)) == generation_bits && (state & BFS_MAX_DEPTH) + 1 == depth) {
                out_edges[vertex_count - 1] = g->edge_ids[i];
                out_vertices[vertex_count++] = u;
                v = u;
                found = 1;
                break;
            }
        }

        if(!found)
            return 0;
    }

    return vertex_count;
}

size_t shortest_path(BFSContext* ctx, uint32_t source, uint32_t target, uint32_t max_depth, uint32_t* out_vertices, uint32_t* out_edges) {
    uint32_t meeting = bidirectional_bfs(ctx, source, target, max_depth);

    if(meeting == UINT32_MAX)
        return 0;

    return reconstruct_path(ctx, source, target, meeting, out_vertices, out_edges);
}
