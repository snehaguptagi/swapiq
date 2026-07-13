"""Knowledge-graph backend selection for SwapIQ.

Neo4j is the production backend. NetworkX remains an explicit local/serverless
fallback so the demo stays runnable without external infrastructure.

Selection:
  SWAPIQ_GRAPH_BACKEND=neo4j   require Neo4j; fail startup if unavailable
  SWAPIQ_GRAPH_BACKEND=networkx force the in-memory fallback
  SWAPIQ_GRAPH_BACKEND=auto     use Neo4j when NEO4J_URI is configured (default)

Set NEO4J_AUTO_SYNC=true for local development to upsert the deterministic demo
catalog and SWAP_OK edges into a fresh database at startup.
"""

import os

from data_gen import INGREDIENT_ALLERGENS
from graph_core import (edge_weight as nx_edge_weight,
                        explain_paths as nx_explain_paths,
                        safe_candidates as nx_safe_candidates)


def _truthy(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class NetworkXBackend:
    name = "networkx"
    persistent = False

    def __init__(self, graph, catalog):
        self.graph = graph
        self.catalog = catalog
        self.products = {p["id"]: p for p in catalog}

    def safe_candidates(self, oos_id, shopper, learned=None):
        return nx_safe_candidates(self.graph, oos_id, shopper, learned)

    def edge_weight(self, a, b, learned=None):
        return nx_edge_weight(self.graph, a, b, learned)

    def explain_paths(self, oos_id, candidate, shopper):
        return nx_explain_paths(self.graph, oos_id, candidate, shopper)

    def graph_view(self, focus, learned=None):
        nodes, edges, seen = [], [], set()

        def add_node(nid, ntype, label):
            if nid not in seen:
                seen.add(nid)
                nodes.append({"id": nid, "type": ntype, "label": label})

        add_node(focus, "product", self.graph.nodes[focus]["name"])
        for _, target, data in self.graph.out_edges(focus, data=True):
            edge_type = data.get("edge_type")
            if edge_type in ("CONTAINS", "IN_CATEGORY", "HAS_TAG"):
                target_data = self.graph.nodes[target]
                add_node(target, target_data["node_type"], target_data.get("label", target))
                edges.append({"from": focus, "to": target, "label": edge_type})
                if edge_type == "CONTAINS":
                    for _, allergen, allergen_edge in self.graph.out_edges(target, data=True):
                        if allergen_edge.get("edge_type") == "IS_A":
                            add_node(allergen, "allergen", self.graph.nodes[allergen]["label"])
                            edges.append({"from": target, "to": allergen, "label": "IS_A"})

        swaps = []
        for _, target, data in self.graph.out_edges(focus, data=True):
            if data.get("edge_type") == "SWAP_OK":
                weight, _ = self.edge_weight(focus, target, learned)
                swaps.append((target, weight))
        for target, weight in sorted(swaps, key=lambda item: item[1], reverse=True)[:4]:
            add_node(target, "product", self.graph.nodes[target]["name"])
            edges.append({"from": focus, "to": target, "label": f"SWAP {weight:.2f}"})
        return {"nodes": nodes, "edges": edges, "focus": focus}

    def recall(self, ingredient):
        affected = [p for p in self.catalog if ingredient in p["ingredients"]]
        allergen = INGREDIENT_ALLERGENS.get(ingredient)
        return {
            "allergen": allergen,
            "products": affected,
            "categories": sorted({p["category"] for p in affected}),
        }

    def stats(self):
        return {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
        }

    def health(self):
        return {"backend": self.name, "persistent": self.persistent, "connected": True}


class Neo4jBackend:
    name = "neo4j"
    persistent = True

    def __init__(self, graph, catalog):
        try:
            from neo4j import GraphDatabase
        except ImportError as exc:
            raise RuntimeError("The neo4j Python driver is not installed") from exc

        self.graph = graph
        self.catalog = catalog
        self.products = {p["id"]: p for p in catalog}
        self.uri = os.environ["NEO4J_URI"]
        self.user = os.environ.get("NEO4J_USER", "neo4j")
        self.password = os.environ.get("NEO4J_PASSWORD", "")
        self.database = os.environ.get("NEO4J_DATABASE", "neo4j")
        connection_timeout = float(os.environ.get("NEO4J_CONNECTION_TIMEOUT", "10"))
        self.driver = GraphDatabase.driver(
            self.uri, auth=(self.user, self.password), connection_timeout=connection_timeout
        )
        self.driver.verify_connectivity()

        if _truthy("NEO4J_AUTO_SYNC"):
            self.sync_catalog()
        self._validate_graph()

    def _session(self):
        return self.driver.session(database=self.database)

    def _product_count(self):
        with self._session() as session:
            return session.run("MATCH (p:Product) RETURN count(p) AS n").single()["n"]

    def _validate_graph(self):
        expected = {
            "products": len(self.catalog),
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
        }
        actual = {"products": self._product_count(), **self.stats()}
        if actual != expected:
            raise RuntimeError(
                "Neo4j graph is incomplete or stale. "
                f"Expected {expected}; found {actual}. Run neo4j_loader.py or set "
                "NEO4J_AUTO_SYNC=true against a dedicated SwapIQ database."
            )

    @staticmethod
    def _chunks(rows, size=1000):
        for start in range(0, len(rows), size):
            yield rows[start:start + size]

    def sync_catalog(self):
        """Idempotently upsert the demo catalog and graph relationships."""
        constraints = [
            ("product_id", "Product", "id"),
            ("ingredient_name", "Ingredient", "name"),
            ("allergen_name", "Allergen", "name"),
            ("diet_tag_name", "DietTag", "name"),
            ("category_name", "Category", "name"),
        ]
        with self._session() as session:
            for constraint, label, prop in constraints:
                session.run(
                    f"CREATE CONSTRAINT {constraint} IF NOT EXISTS "
                    f"FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE"
                ).consume()

            product_rows = [{
                "id": p["id"], "name": p["name"], "base_name": p["base_name"],
                "brand": p["brand"], "category": p["category"], "price": p["price"],
                "price_tier": p["price_tier"], "diet_tags": p["diet_tags"],
            } for p in self.catalog]
            for rows in self._chunks(product_rows):
                session.run(
                    """
                    UNWIND $rows AS row
                    MERGE (p:Product {id: row.id})
                    SET p.name = row.name, p.base_name = row.base_name,
                        p.brand = row.brand, p.category = row.category,
                        p.price = row.price, p.price_tier = row.price_tier,
                        p.diet_tags = row.diet_tags
                    MERGE (c:Category {name: row.category})
                    MERGE (p)-[:IN_CATEGORY]->(c)
                    """, rows=rows
                ).consume()

            ingredient_rows = [
                {"product_id": p["id"], "ingredient": ingredient}
                for p in self.catalog for ingredient in p["ingredients"]
            ]
            for rows in self._chunks(ingredient_rows):
                session.run(
                    """
                    UNWIND $rows AS row
                    MATCH (p:Product {id: row.product_id})
                    MERGE (i:Ingredient {name: row.ingredient})
                    MERGE (p)-[:CONTAINS]->(i)
                    """, rows=rows
                ).consume()

            tag_rows = [
                {"product_id": p["id"], "tag": tag}
                for p in self.catalog for tag in p["diet_tags"]
            ]
            for rows in self._chunks(tag_rows):
                session.run(
                    """
                    UNWIND $rows AS row
                    MATCH (p:Product {id: row.product_id})
                    MERGE (t:DietTag {name: row.tag})
                    MERGE (p)-[:HAS_TAG]->(t)
                    """, rows=rows
                ).consume()

            allergen_rows = [
                {"ingredient": ingredient, "allergen": allergen}
                for ingredient, allergen in INGREDIENT_ALLERGENS.items()
            ]
            session.run(
                """
                UNWIND $rows AS row
                MATCH (i:Ingredient {name: row.ingredient})
                MERGE (a:Allergen {name: row.allergen})
                MERGE (i)-[:IS_A]->(a)
                """, rows=allergen_rows
            ).consume()

            swap_rows = [
                {"from": source, "to": target, "weight": data["weight"]}
                for source, target, data in self.graph.edges(data=True)
                if data.get("edge_type") == "SWAP_OK"
            ]
            for rows in self._chunks(swap_rows):
                session.run(
                    """
                    UNWIND $rows AS row
                    MATCH (a:Product {id: row.from}), (b:Product {id: row.to})
                    MERGE (a)-[r:SWAP_OK]->(b)
                    SET r.weight = row.weight
                    """, rows=rows
                ).consume()

    def safe_candidates(self, oos_id, shopper, learned=None):
        query = """
        MATCH (oos:Product {id: $oos_id})-[:IN_CATEGORY]->(category:Category)
        MATCH (candidate:Product)-[:IN_CATEGORY]->(category)
        WHERE candidate.id <> $oos_id
        CALL (candidate) {
          MATCH (candidate)-[:CONTAINS]->(:Ingredient)-[:IS_A]->(allergen:Allergen)
          RETURN collect(DISTINCT allergen.name) AS allergens
        }
        CALL (candidate) {
          MATCH (candidate)-[:HAS_TAG]->(tag:DietTag)
          RETURN collect(DISTINCT tag.name) AS tags
        }
        OPTIONAL MATCH (oos)-[swap:SWAP_OK]->(candidate)
        WITH oos, candidate, allergens, tags, coalesce(swap.weight, 0.3) AS weight,
             [a IN allergens WHERE a IN $avoids] AS conflicts,
             [d IN $diet WHERE NOT (d IN tags)] AS missing_tags
        RETURN candidate.id AS id, candidate.name AS name, candidate.price AS price,
               candidate.price_tier AS price_tier, tags, allergens, weight,
               conflicts, missing_tags,
               ($budget_sensitive AND candidate.price > oos.price * 1.15) AS over_budget,
               oos.price AS oos_price
        """
        with self._session() as session:
            rows = session.run(
                query, oos_id=oos_id, avoids=shopper["avoids_allergens"],
                diet=shopper["diet"], budget_sensitive=shopper.get("budget_sensitive", False)
            ).data()

        safe, blocked = [], []
        for row in rows:
            learned_entry = (learned or {}).get(f"{oos_id}|{row['id']}")
            weight = learned_entry["weight"] if learned_entry else row["weight"]
            decisions = learned_entry.get("decisions", 0) if learned_entry else 0
            entry = {
                "id": row["id"], "name": row["name"], "price": row["price"],
                "price_tier": row["price_tier"], "diet_tags": row["tags"],
                "allergens": sorted(row["allergens"]), "weight": weight,
                "decisions": decisions,
            }
            if row["conflicts"]:
                entry["blocked_reason"] = (
                    "contains an ingredient classified as "
                    f"{'/'.join(sorted(row['conflicts']))}, which this shopper avoids"
                )
            elif row["missing_tags"]:
                entry["blocked_reason"] = (
                    f"does not carry the {'/'.join(sorted(row['missing_tags']))} "
                    "tag this shopper requires"
                )
            elif row["over_budget"]:
                entry["blocked_reason"] = (
                    f"price Rs. {row['price']} exceeds the budget tolerance "
                    f"versus Rs. {row['oos_price']}"
                )

            (blocked if "blocked_reason" in entry else safe).append(entry)

        safe.sort(key=lambda candidate: candidate["weight"], reverse=True)
        return safe, blocked

    def edge_weight(self, a, b, learned=None):
        learned_entry = (learned or {}).get(f"{a}|{b}")
        if learned_entry:
            return learned_entry["weight"], learned_entry.get("decisions", 0)
        with self._session() as session:
            record = session.run(
                """
                MATCH (a:Product {id: $a}), (b:Product {id: $b})
                OPTIONAL MATCH (a)-[r:SWAP_OK]->(b)
                RETURN coalesce(r.weight, 0.3) AS weight
                """, a=a, b=b
            ).single()
        return record["weight"], 0

    def explain_paths(self, oos_id, candidate, shopper):
        oos = self.products[oos_id]
        chosen = self.products[candidate["id"]]
        paths = [
            f"{chosen['name']} -IN_CATEGORY-> {chosen['category']} (same as the out-of-stock item)"
        ]
        if shopper["avoids_allergens"]:
            avoided = ", ".join(shopper["avoids_allergens"])
            paths.append(
                f"Shopper -AVOIDS-> {avoided}; Neo4j found no CONTAINS/IS_A path "
                f"from {chosen['name']} to these allergens: SAFE"
            )
        if candidate["allergens"]:
            paths.append(
                f"{chosen['name']} -CONTAINS-> allergens: "
                f"{', '.join(candidate['allergens'])} (none conflict)"
            )
        for tag in shopper["diet"]:
            paths.append(f"{chosen['name']} -HAS_TAG-> {tag} (matches shopper diet)")
        paths.append(
            f"{oos['name']} -SWAP_OK({candidate['weight']:.2f})-> {chosen['name']} "
            f"(learned from {candidate['decisions']} decisions this session)"
        )
        return paths

    @staticmethod
    def _node_id(label, name):
        prefixes = {
            "Ingredient": "ing", "Allergen": "alg", "DietTag": "tag",
            "Category": "cat",
        }
        return f"{prefixes[label]}:{name}"

    def graph_view(self, focus, learned=None):
        with self._session() as session:
            product = session.run(
                "MATCH (p:Product {id: $focus}) RETURN p.name AS name", focus=focus
            ).single()
            facts = session.run(
                """
                MATCH (p:Product {id: $focus})-[r:CONTAINS|IN_CATEGORY|HAS_TAG]->(n)
                RETURN type(r) AS relationship, labels(n)[0] AS label, n.name AS name
                """, focus=focus
            ).data()
            allergen_paths = session.run(
                """
                MATCH (p:Product {id: $focus})-[:CONTAINS]->(i:Ingredient)-[:IS_A]->(a:Allergen)
                RETURN i.name AS ingredient, a.name AS allergen
                """, focus=focus
            ).data()
            swaps = session.run(
                """
                MATCH (p:Product {id: $focus})-[r:SWAP_OK]->(candidate:Product)
                RETURN candidate.id AS id, candidate.name AS name, r.weight AS weight
                """, focus=focus
            ).data()

        nodes = [{"id": focus, "type": "product", "label": product["name"]}]
        edges, seen = [], {focus}

        def add_node(node_id, node_type, label):
            if node_id not in seen:
                seen.add(node_id)
                nodes.append({"id": node_id, "type": node_type, "label": label})

        type_map = {
            "Ingredient": "ingredient", "Category": "category", "DietTag": "diet_tag"
        }
        for fact in facts:
            target = self._node_id(fact["label"], fact["name"])
            add_node(target, type_map[fact["label"]], fact["name"])
            edges.append({"from": focus, "to": target, "label": fact["relationship"]})
        for path in allergen_paths:
            ingredient = f"ing:{path['ingredient']}"
            allergen = f"alg:{path['allergen']}"
            add_node(allergen, "allergen", path["allergen"])
            edges.append({"from": ingredient, "to": allergen, "label": "IS_A"})

        weighted_swaps = []
        for swap in swaps:
            learned_entry = (learned or {}).get(f"{focus}|{swap['id']}")
            weight = learned_entry["weight"] if learned_entry else swap["weight"]
            weighted_swaps.append((swap, weight))
        for swap, weight in sorted(weighted_swaps, key=lambda item: item[1], reverse=True)[:4]:
            add_node(swap["id"], "product", swap["name"])
            edges.append({"from": focus, "to": swap["id"], "label": f"SWAP {weight:.2f}"})
        return {"nodes": nodes, "edges": edges, "focus": focus}

    def recall(self, ingredient):
        with self._session() as session:
            rows = session.run(
                """
                MATCH (ingredient:Ingredient {name: $ingredient})<-[:CONTAINS]-(p:Product)
                OPTIONAL MATCH (ingredient)-[:IS_A]->(allergen:Allergen)
                OPTIONAL MATCH (p)-[:IN_CATEGORY]->(category:Category)
                RETURN p.id AS id, p.name AS name, p.category AS product_category,
                       p.price AS price, category.name AS category, allergen.name AS allergen
                """, ingredient=ingredient
            ).data()
        products = [self.products[row["id"]] for row in rows]
        return {
            "allergen": next((row["allergen"] for row in rows if row["allergen"]), None),
            "products": products,
            "categories": sorted({row["category"] or row["product_category"] for row in rows}),
        }

    def stats(self):
        with self._session() as session:
            record = session.run(
                """
                CALL () { MATCH (n) RETURN count(n) AS nodes }
                CALL () { MATCH ()-[r]->() RETURN count(r) AS edges }
                RETURN nodes, edges
                """
            ).single()
        return {"nodes": record["nodes"], "edges": record["edges"]}

    def health(self):
        self.driver.verify_connectivity()
        return {
            "backend": self.name, "persistent": self.persistent, "connected": True,
            "database": self.database,
        }

    def close(self):
        self.driver.close()


def create_graph_backend(graph, catalog):
    mode = os.environ.get("SWAPIQ_GRAPH_BACKEND", "auto").strip().lower()
    if mode not in {"auto", "neo4j", "networkx"}:
        raise RuntimeError("SWAPIQ_GRAPH_BACKEND must be auto, neo4j or networkx")
    if mode == "networkx":
        return NetworkXBackend(graph, catalog)

    uri_configured = bool(os.environ.get("NEO4J_URI"))
    if mode == "neo4j" and not uri_configured:
        raise RuntimeError("SWAPIQ_GRAPH_BACKEND=neo4j requires NEO4J_URI")
    if not uri_configured:
        return NetworkXBackend(graph, catalog)

    try:
        return Neo4jBackend(graph, catalog)
    except Exception:
        if mode == "neo4j":
            raise
        return NetworkXBackend(graph, catalog)
