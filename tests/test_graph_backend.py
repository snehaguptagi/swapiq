"""Backend contract and NetworkX/Neo4j parity tests."""

import os
import sys
import unittest
from pathlib import Path


API_DIR = Path(__file__).resolve().parents[1] / "api"
sys.path.insert(0, str(API_DIR))

from data_gen import generate_catalog, generate_shoppers  # noqa: E402
from graph_backend import Neo4jBackend, NetworkXBackend  # noqa: E402
from graph_core import build_graph  # noqa: E402


class NetworkXBackendContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = generate_catalog()
        cls.graph = build_graph(cls.catalog)
        cls.backend = NetworkXBackend(cls.graph, cls.catalog)
        cls.shopper = generate_shoppers()[0]

    def test_safety_filter_blocks_allergen_paths(self):
        safe, blocked = self.backend.safe_candidates("P001", self.shopper, {})
        self.assertEqual(16, len(safe))
        self.assertEqual(5, len(blocked))
        self.assertEqual("FreshFarm Oat Milk Barista", safe[0]["name"])
        self.assertTrue(any("Cashew Milk" in item["name"] for item in blocked))
        self.assertTrue(all("tree_nuts" in item["blocked_reason"] for item in blocked))

    def test_graph_view_contains_facts_and_swaps(self):
        view = self.backend.graph_view("P001", {})
        labels = {edge["label"] for edge in view["edges"]}
        self.assertIn("CONTAINS", labels)
        self.assertIn("IN_CATEGORY", labels)
        self.assertIn("IS_A", labels)
        self.assertTrue(any(label.startswith("SWAP ") for label in labels))

    def test_recall_traces_all_linked_products(self):
        result = self.backend.recall("almonds")
        self.assertEqual("tree_nuts", result["allergen"])
        self.assertEqual(29, len(result["products"]))
        self.assertIn("plant_milk", result["categories"])

    def test_graph_size_is_deterministic(self):
        # 579 SKUs across the grocery + beauty verticals
        self.assertEqual({"nodes": 722, "edges": 15491}, self.backend.stats())


@unittest.skipUnless(os.environ.get("NEO4J_URI"), "NEO4J_URI is not configured")
class Neo4jParityContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = generate_catalog()
        cls.graph = build_graph(cls.catalog)
        cls.networkx = NetworkXBackend(cls.graph, cls.catalog)
        cls.neo4j = Neo4jBackend(cls.graph, cls.catalog)
        cls.shopper = generate_shoppers()[0]

    @classmethod
    def tearDownClass(cls):
        cls.neo4j.close()

    def test_safety_results_match_networkx(self):
        nx_safe, nx_blocked = self.networkx.safe_candidates("P001", self.shopper, {})
        neo_safe, neo_blocked = self.neo4j.safe_candidates("P001", self.shopper, {})
        self.assertEqual({item["id"] for item in nx_safe}, {item["id"] for item in neo_safe})
        self.assertEqual({item["id"] for item in nx_blocked}, {item["id"] for item in neo_blocked})
        self.assertEqual(nx_safe[0]["id"], neo_safe[0]["id"])

    def test_graph_counts_match_networkx(self):
        self.assertEqual(self.networkx.stats(), self.neo4j.stats())


if __name__ == "__main__":
    unittest.main()
