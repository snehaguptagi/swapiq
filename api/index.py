"""SwapIQ API: stateless FastAPI service, deployable on Vercel serverless.

Session state (learned swap confidence, decision log) lives in the client and
is passed per request, so no database is needed for the demo.

Local dev:  uvicorn api.index:app --reload --port 8000
"""

import difflib
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI
from pydantic import BaseModel

from data_gen import generate_catalog, generate_shoppers
from graph_core import (build_graph, edge_weight, explain_paths,
                        safe_candidates, updated_weight)
from agent import claude_available, rank_and_explain

app = FastAPI(title="SwapIQ API")

catalog = generate_catalog()
G = build_graph(catalog)
shoppers = generate_shoppers()
products_by_id = {p["id"]: p for p in catalog}

DEMO_CARTS = {
    "S1": ["Almond Milk Unsweetened", "Whole Wheat Bread", "Salted Potato Chips"],
    "S2": ["Gluten Free Bread", "Basmati Rice 1kg", "Greek Yogurt Plain"],
    "S3": ["Toned Milk", "Marie Light Biscuits", "Cola 750ml"],
}


def _shopper(shopper_id):
    return next(s for s in shoppers if s["id"] == shopper_id)


def _slim(p):
    return {"id": p["id"], "name": p["name"], "price": p["price"],
            "category": p["category"].replace("_", " "),
            "allergens": [a.replace("_", " ") for a in p["allergens"]]}


def _naive_pick(oos):
    """Emulates an embedding-similarity engine: clusters by composition, no safety."""
    same_cat = [p for p in catalog if p["category"] == oos["category"]
                and p["id"] != oos["id"] and p["base_name"] != oos["base_name"]]
    if not same_cat:
        return None

    def score(p):
        s = difflib.SequenceMatcher(None, oos["base_name"], p["base_name"]).ratio()
        s += 2.0 * len(set(oos["allergens"]) & set(p["allergens"]))
        s += 0.3 * len(set(oos["ingredients"]) & set(p["ingredients"]))
        return s

    return max(same_cat, key=score)


def _is_unsafe(product, shopper):
    return bool(set(product["allergens"]) & set(shopper["avoids_allergens"])) or \
        not set(shopper["diet"]) <= set(product["diet_tags"])


class OfferRequest(BaseModel):
    product_id: str
    shopper_id: str
    learned: dict = {}


class DecideRequest(BaseModel):
    oos_id: str
    chosen_id: str
    accepted: bool
    learned: dict = {}


class GraphRequest(BaseModel):
    focus: str
    learned: dict = {}


@app.get("/api/bootstrap")
def bootstrap():
    carts = {sid: [next(p["id"] for p in catalog if p["base_name"] == b) for b in bases]
             for sid, bases in DEMO_CARTS.items()}
    return {
        "claude": claude_available(),
        "shoppers": [
            {"id": s["id"], "name": s["name"],
             "avoids": [a.replace("_", " ") for a in s["avoids_allergens"]],
             "diet": s["diet"], "budget_sensitive": s["budget_sensitive"]}
            for s in shoppers
        ],
        "products": [_slim(p) for p in catalog],
        "demo_carts": carts,
    }


@app.post("/api/safety-check")
def safety_check(req: OfferRequest):
    """The deterministic half: graph safety traversal only, no LLM. Returns
    instantly so the UI can show what the graph removed before Claude ranks."""
    oos = products_by_id[req.product_id]
    shopper = _shopper(req.shopper_id)
    t0 = time.perf_counter()
    safe, blocked = safe_candidates(G, oos["id"], shopper, req.learned)
    graph_ms = round((time.perf_counter() - t0) * 1000, 1)
    naive = _naive_pick(oos)
    naive_out = {**_slim(naive), "unsafe": _is_unsafe(naive, shopper)} if naive else None
    return {
        "oos": _slim(oos),
        "safe_count": len(safe), "blocked_count": len(blocked),
        "checked_count": len(safe) + len(blocked), "graph_ms": graph_ms,
        "blocked": [{"name": b["name"], "reason": b["blocked_reason"]} for b in blocked[:10]],
        "naive": naive_out,
    }


@app.post("/api/swap-offer")
def swap_offer(req: OfferRequest):
    oos = products_by_id[req.product_id]
    shopper = _shopper(req.shopper_id)

    t0 = time.perf_counter()
    safe, blocked = safe_candidates(G, oos["id"], shopper, req.learned)
    graph_ms = round((time.perf_counter() - t0) * 1000, 1)

    naive = _naive_pick(oos)
    naive_out = {**_slim(naive), "unsafe": _is_unsafe(naive, shopper)} if naive else None

    base = {"oos": _slim(oos), "safe_count": len(safe), "blocked_count": len(blocked),
            "checked_count": len(safe) + len(blocked), "graph_ms": graph_ms,
            "naive": naive_out,
            "blocked": [{"name": b["name"], "reason": b["blocked_reason"]} for b in blocked[:10]]}

    if not safe:
        return {**base, "best": None, "alternatives": [], "rank_s": 0, "source": None}

    t1 = time.perf_counter()
    ranking = rank_and_explain(oos, safe, shopper)
    rank_s = round(time.perf_counter() - t1, 2)

    safe_by_id = {c["id"]: c for c in safe}

    def entry(r):
        cand = safe_by_id[r["product_id"]]
        return {**_slim(products_by_id[cand["id"]]), "reason": r["reason"],
                "weight": cand["weight"],
                "paths": explain_paths(G, oos["id"], cand, shopper)}

    best = next(r for r in ranking["ranking"] if r["product_id"] == ranking["best_id"])
    return {**base, "source": ranking["source"], "rank_s": rank_s, "best": entry(best),
            "alternatives": [entry(r) for r in ranking["ranking"]
                             if r["product_id"] != ranking["best_id"]]}


@app.post("/api/decide")
def decide(req: DecideRequest):
    """Pure learning step. The client stores the returned weight and passes it back."""
    old_w, _ = edge_weight(G, req.oos_id, req.chosen_id, req.learned)
    new_w = updated_weight(old_w, req.accepted)
    return {"edge": f"{req.oos_id}|{req.chosen_id}", "weight_before": old_w, "weight_after": new_w}


@app.post("/api/graph")
def graph_view(req: GraphRequest):
    """Subgraph around a product for the frontend canvas renderer."""
    focus = req.focus
    nodes, edges, seen = [], [], set()

    def add_node(nid, ntype, label):
        if nid not in seen:
            seen.add(nid)
            nodes.append({"id": nid, "type": ntype, "label": label})

    add_node(focus, "product", G.nodes[focus]["name"])
    for _, v, d in G.out_edges(focus, data=True):
        et = d.get("edge_type")
        if et in ("CONTAINS", "IN_CATEGORY", "HAS_TAG"):
            data = G.nodes[v]
            add_node(v, data["node_type"], data.get("label", v))
            edges.append({"from": focus, "to": v, "label": et})
            if et == "CONTAINS":
                for _, v2, d2 in G.out_edges(v, data=True):
                    if d2.get("edge_type") == "IS_A":
                        add_node(v2, "allergen", G.nodes[v2]["label"])
                        edges.append({"from": v, "to": v2, "label": "IS_A"})

    swaps = []
    for _, v, d in G.out_edges(focus, data=True):
        if d.get("edge_type") == "SWAP_OK":
            w, _n = edge_weight(G, focus, v, req.learned)
            swaps.append((v, w))
    for v, w in sorted(swaps, key=lambda x: x[1], reverse=True)[:4]:
        add_node(v, "product", G.nodes[v]["name"])
        edges.append({"from": focus, "to": v, "label": f"SWAP {w:.2f}"})
    return {"nodes": nodes, "edges": edges, "focus": focus}


# Local development only: serve the frontend. On Vercel, static files are
# served by the platform and this block is skipped.
if not os.environ.get("VERCEL"):
    from fastapi.staticfiles import StaticFiles
    public_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "public")
    if os.path.isdir(public_dir):
        app.mount("/", StaticFiles(directory=public_dir, html=True), name="static")
