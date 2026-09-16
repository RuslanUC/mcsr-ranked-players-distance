#include <Python.h>

#include "lib.h"
#include "stb_ds.h"

typedef struct {
    PyObject_HEAD

    Graph* graph;
    BFSContext* bfs_ctx;
    uint32_t* path_vertices;
    uint32_t* path_edges;
    int max_depth;
} Py_MatchesGraph;

static void Py_MatchesGraph_dealloc(Py_MatchesGraph* self) {
    bfs_free(self->bfs_ctx);
    graph_free(self->graph);
    free(self->path_vertices);
    free(self->path_edges);

    ((PyObject*)self)->ob_type->tp_free(self);
}

static int Py_MatchesGraph_init(Py_MatchesGraph* self, PyObject* args, PyObject* kwargs) {
    const char* graph_dir;
    int use_mmap = 0;

    int max_depth = 8;

    static char *kwlist[] = {"graph_dir", "max_depth", "mmap", NULL};
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "s|ip", kwlist, &graph_dir, &max_depth, &use_mmap)) {
        return -1;
    }

    if(max_depth <= 0) {
        PyErr_SetString(PyExc_ValueError, "max_depth must be a positive number");
        return -1;
    }

    if(max_depth > BFS_MAX_DEPTH) {
        PyErr_Format(PyExc_ValueError, "max_depth must not exceed %u", BFS_MAX_DEPTH);
        return -1;
    }

    self->max_depth = max_depth;

    Graph* graph = use_mmap ? graph_load_mmap(graph_dir) : graph_load(graph_dir);
    if(!graph) {
        PyErr_SetString(PyExc_ValueError, "Failed to load graph: [TODO: exact error]");
        return -1;
    }

    self->graph = graph;

    BFSContext* ctx = bfs_create(graph);
    if(!ctx) {
        PyErr_SetString(PyExc_MemoryError, "Failed to create bfs context.");
        return -1;
    }

    self->bfs_ctx = ctx;

    size_t path_capacity = (size_t)max_depth + 1;
    if(path_capacity > graph->n)
        path_capacity = graph->n;
    if(path_capacity == 0)
        path_capacity = 1;

    uint32_t* path_vertices = malloc(path_capacity * sizeof(uint32_t));
    uint32_t* path_edges = malloc(path_capacity * sizeof(uint32_t));

    if(!path_vertices || !path_edges) {
        free(path_vertices);
        free(path_edges);
        PyErr_SetString(PyExc_MemoryError, "Failed to allocate path arrays.");
        return -1;
    }

    self->path_vertices = path_vertices;
    self->path_edges = path_edges;

    return 0;
}

static PyObject* Py_MatchesGraph_get_path(Py_MatchesGraph* self, PyObject* args, PyObject* kwargs) {
    const char* player1;
    const char* player2;

    static char *kwlist[] = {"player1", "player2", NULL};
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "ss", kwlist, &player1, &player2)) {
        return NULL;
    }

    NicknameToVertex* nickname_to_vertex = self->graph->nickname_to_vertex;

    ptrdiff_t source_idx;
    stbds_hmget_key_ts(nickname_to_vertex, sizeof(*nickname_to_vertex), (void*) player1, sizeof(nickname_to_vertex->key), &source_idx, STBDS_HM_STRING);
    if(source_idx < 0) {
        PyErr_Format(PyExc_ValueError, "player \"%s\" is not in graph", player1);
        return NULL;
    }

    ptrdiff_t target_idx;
    stbds_hmget_key_ts(nickname_to_vertex, sizeof(*nickname_to_vertex), (void*) player2, sizeof(nickname_to_vertex->key), &target_idx, STBDS_HM_STRING);
    if(target_idx < 0) {
        PyErr_Format(PyExc_ValueError, "player \"%s\" is not in graph", player2);
        return NULL;
    }

    const uint32_t source = nickname_to_vertex[source_idx].value;
    const uint32_t target = nickname_to_vertex[target_idx].value;

    uint32_t* path_vertices = self->path_vertices;
    uint32_t* path_edges = self->path_edges;

    const size_t path_len = shortest_path(self->bfs_ctx, source, target, self->max_depth, path_vertices, path_edges);

    if(path_len == 0) {
        return PyList_New(0);
    }

    PyObject* result = PyList_New((Py_ssize_t)path_len - 1);
    if(!result)
        return NULL;

    const char* nicknames_buf = self->graph->nicknames_buf;
    const uint32_t* vertex_to_nickname_offset = self->graph->vertex_to_nickname_offset;
    const uint32_t* match_ids = self->graph->match_ids;
    const uint8_t* match_seasons = self->graph->match_seasons;

    for(size_t i = 0; i < path_len - 1; ++i) {
        const char* player1_name = nicknames_buf + vertex_to_nickname_offset[path_vertices[i]];
        const char* player2_name = nicknames_buf + vertex_to_nickname_offset[path_vertices[i + 1]];
        PyObject* item = Py_BuildValue("(ssIB)", player1_name, player2_name, match_ids[path_edges[i]], match_seasons[path_edges[i]]);
        if(!item) {
            Py_DECREF(result);
            return NULL;
        }
        PyList_SET_ITEM(result, (Py_ssize_t)i, item);
    }

    return result;
}

static PyObject* Py_MatchesGraph_vcount(Py_MatchesGraph* self, PyObject* Py_UNUSED(args)) {
    return PyLong_FromUnsignedLong(self->graph->n);
}

static PyObject* Py_MatchesGraph_ecount(Py_MatchesGraph* self, PyObject* Py_UNUSED(args)) {
    return PyLong_FromUnsignedLong(self->graph->m);
}

static PyObject* Py_MatchesGraph_has_player(Py_MatchesGraph* self, PyObject* args, PyObject* kwargs) {
    const char* nickname;

    static char *kwlist[] = {"nickname", NULL};
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "s", kwlist, &nickname)) {
        return NULL;
    }

    NicknameToVertex* nickname_to_vertex = self->graph->nickname_to_vertex;

    ptrdiff_t source_idx;
    stbds_hmget_key_ts(nickname_to_vertex, sizeof(*nickname_to_vertex), (void*) nickname, sizeof(nickname_to_vertex->key), &source_idx, STBDS_HM_STRING);

    if(source_idx >= 0)
        Py_RETURN_TRUE;
    Py_RETURN_FALSE;
}

static PyMethodDef Py_MatchesGraph_methods[] = {
    {"get_path", (PyCFunction)Py_MatchesGraph_get_path, METH_VARARGS | METH_KEYWORDS, 0,},
    {"vcount", (PyCFunction)Py_MatchesGraph_vcount, METH_NOARGS, 0,},
    {"ecount", (PyCFunction)Py_MatchesGraph_ecount, METH_NOARGS, 0,},
    {"has_player", (PyCFunction)Py_MatchesGraph_has_player, METH_VARARGS | METH_KEYWORDS, 0,},
    {NULL}
};

static PyType_Slot Py_MatchesGraph_slots[] = {
    {Py_tp_dealloc, Py_MatchesGraph_dealloc},
    {Py_tp_hash, PyObject_HashNotImplemented},
    {Py_tp_methods, Py_MatchesGraph_methods},
    {Py_tp_init, Py_MatchesGraph_init},
    {0, NULL}
};

static PyType_Spec pymcsrd_c_MatchesGraph_spec = {
    .name = "pymcsrd_c.MatchesGraph",
    .basicsize = sizeof(Py_MatchesGraph),
    .itemsize = 0,
    .flags = Py_TPFLAGS_DEFAULT,
    .slots = Py_MatchesGraph_slots,
};

static PyModuleDef pymcsrd_c_module = {
    .m_base = PyModuleDef_HEAD_INIT,
    .m_name = "pymcsrd_c",
    .m_doc = 0,
    .m_size = 0,
};

PyMODINIT_FUNC PyInit_pymcsrd_c(void) {
    PyObject* MatchesGraphType = NULL;

    PyObject* m = PyModule_Create(&pymcsrd_c_module);
    if(!m) {
        goto failed;
    }

    MatchesGraphType = PyType_FromSpec(&pymcsrd_c_MatchesGraph_spec);
    if(!MatchesGraphType) {
        goto failed;
    }

    if(PyModule_AddObject(m, "MatchesGraph", MatchesGraphType)) {
        goto failed;
    }

    return m;

failed:
    Py_XDECREF(MatchesGraphType);
    Py_XDECREF(m);
    return NULL;
}
