"""Graph wiring regression (no network).

Guards against B1: on pinned langgraph 0.2.x a node named like a state key ('plan')
raises at compile time. Building the graph here would have caught it.
"""

import numpy as np

from app.agent.graph import build_graph
from app.config import get_settings
from app.rag.index import CorpusIndex
from app.rag.loader import load_corpus


class _DummyEmbedder:
    def embed_query(self, text):
        return np.full(4, 0.5, dtype="float32")


def _corpus():
    s = get_settings()
    chunks = load_corpus(s.corpus_dir)
    matrix = np.full((len(chunks), 4), 0.5, dtype="float32")
    return CorpusIndex(chunks, matrix, _DummyEmbedder(), s)


def test_graph_compiles_and_has_expected_nodes():
    graph = build_graph(_corpus(), get_settings())
    nodes = set(graph.get_graph().nodes.keys())
    assert "planner" in nodes          # renamed to avoid the 'plan' state-key collision
    assert "plan" not in nodes
    assert {"agent", "tools", "critic", "finalize"} <= nodes
