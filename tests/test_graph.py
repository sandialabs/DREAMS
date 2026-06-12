"""
Initial tests for graph creation
"""

import unittest
from pathlib import Path
import pandas as pd
import networkx as nx

import dreams

PARENT_DIR = Path(__file__).parent.resolve()
MODEL_DIR = Path(PARENT_DIR.parent, "demos", 'models')

class TestGraph(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        super(TestGraph, self).__init__(*args, **kwargs)
        # Default attributes
        self.model_fp = MODEL_DIR / "sfo_p1udt1469" / "Main.dss"

    def test_incidence_matrix_creation(self):
        # test creation and return of incidence matrix
        graph = dreams.Graph(self.model_fp, init=False)
        inc_matrix = graph.get_incidence_matrix()
        self.assertIsInstance(inc_matrix, pd.DataFrame)

    def test_get_directed_graph(self):
        # test creation of directed graph via class init
        graph = dreams.Graph(self.model_fp)
        self.assertIsInstance(graph.G, nx.MultiDiGraph)


if __name__ == "__main__":
    unittest.main()
