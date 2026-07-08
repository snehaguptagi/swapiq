"""SwapIQ knowledge graph core, stateless for serverless deployment.

The graph (products, ingredients, allergens, diets) is deterministic and
rebuilt per instance. Learned SWAP confidence lives client-side and is passed
in per request, so the API needs no database for the demo.
"""

import networkx as nx

from data_gen import INGREDIENT_ALLERGENS


def build_graph(products):
    G = nx.DiGraph()
    for p in products:
        G.add_node(p["id"], node_type="product", **{k: v for k, v in p.items() if k != "id"})
        G.add_node(f"cat:{p['category']}", node_type="category", label=p["category"])
        G.add_edge(p["id"], f"cat:{p['category']}", edge_type="IN_CATEGORY")
        for ing in p["ingredients"]:
            G.add_node(f"ing:{ing}", node_type="ingredient", label=ing)
            G.add_edge(p["id"], f"ing:{ing}", edge_type="CONTAINS")
            if ing in INGREDIENT_ALLERGENS:
                allergen = INGREDIENT_ALLERGENS[ing]
                G.add_node(f"alg:{allergen}", node_type="allergen", label=allergen)
                G.add_edge(f"ing:{ing}", f"alg:{allergen}", edge_type="IS_A")
        for tag in p["diet_tags"]:
            G.add_node(f"tag:{tag}", node_type="diet_tag", label=tag)
            G.add_edge(p["id"], f"tag:{tag}", edge_type="HAS_TAG")
    _seed_swap_edges(G, products)
    return G


def _seed_swap_edges(G, products):
    """Cold-start SWAP priors from attribute similarity. Feedback then moves them."""
    by_cat = {}
    for p in products:
        by_cat.setdefault(p["category"], []).append(p)
    for cat_products in by_cat.values():
        for a in cat_products:
            for b in cat_products:
                if a["id"] == b["id"]:
                    continue
                score = 0.35
                if a["base_name"] == b["base_name"]:
                    score += 0.30
                shared = len(set(a["ingredients"]) & set(b["ingredients"]))
                score += min(shared * 0.06, 0.18)
                price_gap = abs(a["price"] - b["price"]) / max(a["price"], 1)
                score += 0.12 * max(0, 1 - price_gap)
                G.add_edge(a["id"], b["id"], edge_type="SWAP_OK",
                           weight=round(min(score, 0.95), 3))


def product_allergens(G, product_id):
    """Traversal: product -CONTAINS-> ingredient -IS_A-> allergen."""
    allergens = set()
    for _, ing, d in G.out_edges(product_id, data=True):
        if d.get("edge_type") == "CONTAINS":
            for _, alg, d2 in G.out_edges(ing, data=True):
                if d2.get("edge_type") == "IS_A":
                    allergens.add(alg.split(":", 1)[1])
    return allergens


def edge_weight(G, a, b, learned):
    """Learned client-side weight wins over the seeded prior."""
    entry = (learned or {}).get(f"{a}|{b}")
    if entry:
        return entry["weight"], entry.get("decisions", 0)
    if G.has_edge(a, b):
        return G.edges[a, b]["weight"], 0
    return 0.3, 0


def safe_candidates(G, oos_product_id, shopper, learned=None):
    """The deterministic safety filter. Runs before any AI."""
    oos = G.nodes[oos_product_id]
    safe, blocked = [], []
    for node, data in G.nodes(data=True):
        if data.get("node_type") != "product" or node == oos_product_id:
            continue
        if data["category"] != oos["category"]:
            continue

        reason = None
        hit = product_allergens(G, node) & set(shopper["avoids_allergens"])
        if hit:
            reason = f"contains an ingredient classified as {'/'.join(sorted(hit))}, which this shopper avoids"
        elif not set(shopper["diet"]) <= set(data["diet_tags"]):
            missing = set(shopper["diet"]) - set(data["diet_tags"])
            reason = f"does not carry the {'/'.join(sorted(missing))} tag this shopper requires"
        elif shopper.get("budget_sensitive") and data["price"] > oos["price"] * 1.15:
            reason = f"price Rs. {data['price']} exceeds the budget tolerance versus Rs. {oos['price']}"

        w, n = edge_weight(G, oos_product_id, node, learned)
        entry = {
            "id": node, "name": data["name"], "price": data["price"],
            "price_tier": data["price_tier"], "diet_tags": data["diet_tags"],
            "allergens": sorted(product_allergens(G, node)),
            "weight": w, "decisions": n,
        }
        if reason:
            entry["blocked_reason"] = reason
            blocked.append(entry)
        else:
            safe.append(entry)

    safe.sort(key=lambda c: c["weight"], reverse=True)
    return safe, blocked


def explain_paths(G, oos_product_id, candidate, shopper):
    """Human-readable graph paths behind a decision."""
    cand_node = G.nodes[candidate["id"]]
    paths = [f"{cand_node['name']} -IN_CATEGORY-> {cand_node['category']} (same as the out-of-stock item)"]
    if shopper["avoids_allergens"]:
        avoided = ", ".join(shopper["avoids_allergens"])
        paths.append(f"Shopper -AVOIDS-> {avoided}; no CONTAINS path from {cand_node['name']} reaches these: SAFE")
    if candidate["allergens"]:
        paths.append(f"{cand_node['name']} -CONTAINS-> allergens: {', '.join(candidate['allergens'])} (none conflict)")
    for tag in shopper["diet"]:
        paths.append(f"{cand_node['name']} -HAS_TAG-> {tag} (matches shopper diet)")
    paths.append(f"{G.nodes[oos_product_id]['name']} -SWAP_OK({candidate['weight']:.2f})-> {cand_node['name']} "
                 f"(learned from {candidate['decisions']} decisions this session)")
    return paths


def updated_weight(old_weight, accepted, lr=0.25):
    """Pure learning step: accept pulls the confidence up, decline pushes it down."""
    w = old_weight
    return round(w + lr * (1 - w) if accepted else w - lr * w, 3)
