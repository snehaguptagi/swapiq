"""Load and verify the complete SwapIQ graph in Neo4j.

This uses the same Neo4j backend as the FastAPI service, including Product,
Ingredient, Allergen, DietTag, Category and weighted SWAP_OK relationships.

Usage:
    python neo4j_loader.py
    python neo4j_loader.py --demo
"""

import os
import sys


API_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "api")
sys.path.insert(0, API_DIR)

from data_gen import generate_catalog, generate_shoppers
from graph_backend import Neo4jBackend
from graph_core import build_graph


def main():
    os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
    os.environ.setdefault("NEO4J_USER", "neo4j")
    os.environ.setdefault("NEO4J_PASSWORD", "swapiq-demo")
    os.environ.setdefault("NEO4J_DATABASE", "neo4j")
    os.environ["NEO4J_AUTO_SYNC"] = "true"

    catalog = generate_catalog()
    backend = Neo4jBackend(build_graph(catalog), catalog)
    try:
        stats = backend.stats()
        print(
            f"Loaded: {len(catalog)} products, {stats['nodes']} total nodes, "
            f"{stats['edges']} relationships"
        )

        if "--demo" in sys.argv:
            shopper = generate_shoppers()[0]
            safe, blocked = backend.safe_candidates("P001", shopper, {})
            print("\nSafe substitutes for a nut-allergic vegan shopper:")
            for candidate in safe[:5]:
                print(f"  SAFE  {candidate['name']}  (Rs. {candidate['price']})")
            print("\nWhat Neo4j blocks before the AI runs:")
            for candidate in blocked[:5]:
                print(f"  BLOCK {candidate['name']} - {candidate['blocked_reason']}")
    finally:
        backend.close()

    print("\nDone. Open http://localhost:7474 to browse the graph visually.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        sys.exit(f"Neo4j load failed: {exc}")
