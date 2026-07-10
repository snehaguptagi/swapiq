"""Load the SwapIQ catalog into Neo4j as a real knowledge graph.

This proves the production path from the LLD: the same schema that runs
in-memory on NetworkX for the demo loads unchanged into Neo4j. Run it once
Neo4j is up (see NEO4J_SETUP.md), then run the safety query below.

Usage:
    python neo4j_loader.py                      # load the catalog
    python neo4j_loader.py --demo               # load, then run the safety query
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "api"))

from data_gen import INGREDIENT_ALLERGENS, generate_catalog

URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
USER = os.environ.get("NEO4J_USER", "neo4j")
PASSWORD = os.environ.get("NEO4J_PASSWORD", "swapiq-demo")


def load(driver):
    catalog = generate_catalog()
    with driver.session() as s:
        s.run("MATCH (n) DETACH DELETE n")
        s.run("CREATE CONSTRAINT product_id IF NOT EXISTS "
              "FOR (p:Product) REQUIRE p.id IS UNIQUE")

        for p in catalog:
            s.run(
                """
                MERGE (prod:Product {id: $id})
                SET prod.name = $name, prod.brand = $brand, prod.price = $price,
                    prod.price_tier = $price_tier
                MERGE (cat:Category {name: $category})
                MERGE (prod)-[:IN_CATEGORY]->(cat)
                WITH prod
                UNWIND $ingredients AS ing
                  MERGE (i:Ingredient {name: ing})
                  MERGE (prod)-[:CONTAINS]->(i)
                WITH prod
                UNWIND $tags AS tag
                  MERGE (t:DietTag {name: tag})
                  MERGE (prod)-[:HAS_TAG]->(t)
                """,
                id=p["id"], name=p["name"], brand=p["brand"], price=p["price"],
                price_tier=p["price_tier"], category=p["category"],
                ingredients=p["ingredients"], tags=p["diet_tags"],
            )

        for ing, allergen in INGREDIENT_ALLERGENS.items():
            s.run(
                """
                MATCH (i:Ingredient {name: $ing})
                MERGE (a:Allergen {name: $allergen})
                MERGE (i)-[:IS_A]->(a)
                """,
                ing=ing, allergen=allergen,
            )

        counts = s.run(
            "MATCH (p:Product) WITH count(p) AS products "
            "MATCH (i:Ingredient) WITH products, count(i) AS ingredients "
            "MATCH (a:Allergen) RETURN products, ingredients, count(a) AS allergens"
        ).single()
        print(f"Loaded: {counts['products']} products, {counts['ingredients']} ingredients, "
              f"{counts['allergens']} allergens")


def safety_query(driver):
    """The exact safety traversal, expressed in Cypher: safe plant-milk swaps
    for a nut-allergic vegan shopper when almond milk is out of stock."""
    print("\nSafe substitutes for a nut-allergic vegan shopper (almond milk out of stock):")
    with driver.session() as s:
        rows = s.run(
            """
            MATCH (oos:Product {id: 'P001'})-[:IN_CATEGORY]->(cat)
            MATCH (cand:Product)-[:IN_CATEGORY]->(cat)
            WHERE cand.id <> oos.id
              AND (cand)-[:HAS_TAG]->(:DietTag {name: 'vegan'})
              AND NOT EXISTS {
                    MATCH (cand)-[:CONTAINS]->(:Ingredient)-[:IS_A]->(a:Allergen)
                    WHERE a.name IN ['tree_nuts', 'peanuts']
              }
            RETURN cand.name AS name, cand.price AS price
            ORDER BY cand.price LIMIT 5
            """
        )
        for r in rows:
            print(f"  SAFE  {r['name']}  (Rs. {r['price']})")

        print("\nWhat the graph blocks (nut-containing plant milks it will never offer):")
        rows = s.run(
            """
            MATCH (cand:Product)-[:IN_CATEGORY]->(:Category {name: 'plant_milk'})
            MATCH (cand)-[:CONTAINS]->(i:Ingredient)-[:IS_A]->(a:Allergen)
            WHERE a.name = 'tree_nuts'
            RETURN DISTINCT cand.name AS name LIMIT 5
            """
        )
        for r in rows:
            print(f"  BLOCK {r['name']}")


if __name__ == "__main__":
    try:
        from neo4j import GraphDatabase
    except ImportError:
        sys.exit("Install the driver first:  pip install neo4j")

    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    try:
        driver.verify_connectivity()
    except Exception as e:
        sys.exit(f"Cannot reach Neo4j at {URI}. Start it first (see NEO4J_SETUP.md). {e}")

    load(driver)
    if "--demo" in sys.argv:
        safety_query(driver)
    driver.close()
    print("\nDone. Open http://localhost:7474 to browse the graph visually.")
