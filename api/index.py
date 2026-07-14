"""SwapIQ API: FastAPI service with Neo4j production graph support.

Neo4j is used when configured; NetworkX is the explicit no-infrastructure
fallback. Session learning remains client-side and travels with each request.

Local dev:  uvicorn api.index:app --reload --port 8000
"""

import difflib
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI
from pydantic import BaseModel, Field

from data_gen import (INGREDIENT_ALLERGENS, STORES, generate_catalog,
                      generate_shoppers, generate_store_stock)
from graph_core import build_graph, updated_weight
from graph_backend import create_graph_backend
from agent import claude_available, get_api_key, rank_and_explain
from commerce_signals import enrich_candidates
import listings as listing_qa

app = FastAPI(title="SwapIQ API")

catalog = generate_catalog()
NX_G = build_graph(catalog)
graph_backend = create_graph_backend(NX_G, catalog)
shoppers = generate_shoppers()
products_by_id = {p["id"]: p for p in catalog}
store_stock = generate_store_stock(catalog)
STORE_ID = STORES[0]

DEMO_CARTS = {
    "S1": ["Almond Milk Unsweetened", "Whole Wheat Bread", "Salted Potato Chips"],
    "S2": ["Gluten Free Bread", "Basmati Rice 1kg", "Greek Yogurt Plain"],
    "S3": ["Toned Milk", "Marie Light Biscuits", "Cola 750ml"],
    "S4": ["Sesame Tahini", "Whole Wheat Bread", "Toned Milk"],
}


def _shopper(shopper_id):
    return next(s for s in shoppers if s["id"] == shopper_id)


def _slim(p):
    return {"id": p["id"], "name": p["name"], "price": p["price"],
            "brand": p["brand"], "base_name": p["base_name"],
            "category": p["category"].replace("_", " "),
            "allergens": [a.replace("_", " ") for a in p["allergens"]],
            "diet_tags": p["diet_tags"]}


def _sim_score(a, b):
    """Composition + name similarity, the way an embedding recommender clusters
    products. Products made of the same stuff sit close (almond milk near cashew
    milk) with zero awareness of who can safely eat them."""
    s = difflib.SequenceMatcher(None, a["base_name"], b["base_name"]).ratio()
    s += 2.0 * len(set(a["allergens"]) & set(b["allergens"]))
    s += 0.3 * len(set(a["ingredients"]) & set(b["ingredients"]))
    return s


def _sim_display(a, b):
    """A cosine-like 0..1 similarity for display in the RAG view."""
    name = difflib.SequenceMatcher(None, a["base_name"], b["base_name"]).ratio()
    ing = len(set(a["ingredients"]) & set(b["ingredients"]))
    al = len(set(a["allergens"]) & set(b["allergens"]))
    return round(min(0.98, 0.58 + 0.28 * name + 0.05 * ing + 0.07 * al), 2)


def _naive_pick(oos):
    same_cat = [p for p in catalog if p["category"] == oos["category"]
                and p["id"] != oos["id"] and p["base_name"] != oos["base_name"]]
    if not same_cat:
        return None
    return max(same_cat, key=lambda p: _sim_score(oos, p))


def _is_unsafe(product, shopper):
    return bool(set(product["allergens"]) & set(shopper["avoids_allergens"])) or \
        not set(shopper["diet"]) <= set(product["diet_tags"])


class OfferRequest(BaseModel):
    product_id: str
    shopper_id: str
    learned: dict = Field(default_factory=dict)


class DecideRequest(BaseModel):
    oos_id: str
    chosen_id: str
    accepted: bool
    learned: dict = Field(default_factory=dict)


class GraphRequest(BaseModel):
    focus: str
    learned: dict = Field(default_factory=dict)


@app.get("/api/bootstrap")
def bootstrap():
    carts = {sid: [next(p["id"] for p in catalog if p["base_name"] == b) for b in bases]
             for sid, bases in DEMO_CARTS.items()}
    return {
        "claude": claude_available(),
        "graph": graph_backend.health(),
        "store": STORE_ID,
        "shoppers": [
            {"id": s["id"], "name": s["name"],
             "avoids": [a.replace("_", " ") for a in s["avoids_allergens"]],
             "diet": s["diet"], "budget_sensitive": s["budget_sensitive"]}
            for s in shoppers
        ],
        "products": [_slim(p) for p in catalog],
        "demo_carts": carts,
    }


@app.post("/api/rag-offer")
def rag_offer(req: OfferRequest):
    """QuickCart's standard substitution recommender: retrieval by embedding
    similarity, exactly like a RAG pipeline. Ranks same-category products by how
    similar they are, with NO model of the shopper's allergies or diet. Returns
    the nearest matches and flags (for the demo) which ones are actually unsafe,
    a fact the similarity search itself never checks."""
    oos = products_by_id[req.product_id]
    shopper = _shopper(req.shopper_id)
    same = [p for p in catalog if p["category"] == oos["category"]
            and p["id"] != oos["id"] and p["base_name"] != oos["base_name"]]
    ranked = sorted(same, key=lambda p: _sim_score(oos, p), reverse=True)[:3]

    def entry(p):
        return {**_slim(p), "similarity": _sim_display(oos, p), "unsafe": _is_unsafe(p, shopper),
                "stock_level": store_stock.get(STORE_ID, {}).get(p["id"], "high"),
                "reason": f"Nearest match to {oos['name']} by embedding similarity"}

    picks = [entry(p) for p in ranked]
    return {
        "mode": "rag",
        "oos": _slim(oos),
        "best": picks[0] if picks else None,
        "alternatives": picks[1:],
        "method": "vector similarity search (RAG)",
        "checked_count": len(same),
    }


@app.post("/api/safety-check")
def safety_check(req: OfferRequest):
    """The deterministic half: graph safety traversal only, no LLM. Returns
    instantly so the UI can show what the graph removed before Claude ranks."""
    oos = products_by_id[req.product_id]
    shopper = _shopper(req.shopper_id)
    t0 = time.perf_counter()
    safe, blocked = graph_backend.safe_candidates(oos["id"], shopper, req.learned)
    graph_ms = round((time.perf_counter() - t0) * 1000, 1)
    enriched_safe, unavailable = enrich_candidates(
        safe, oos, shopper, store_stock, STORE_ID, products_by_id)
    naive = _naive_pick(oos)
    naive_out = {**_slim(naive), "unsafe": _is_unsafe(naive, shopper),
                 "stock_level": store_stock.get(STORE_ID, {}).get(naive["id"], "high")} if naive else None
    return {
        "oos": _slim(oos),
        "safe_count": len(enriched_safe), "blocked_count": len(blocked),
        "unavailable_count": len(unavailable),
        "checked_count": len(safe) + len(blocked), "graph_ms": graph_ms,
        "blocked": [{"name": b["name"], "reason": b["blocked_reason"]} for b in blocked[:10]],
        "unavailable": [{"name": u["name"], "reason": u["blocked_reason"]} for u in unavailable[:10]],
        "naive": naive_out,
    }


@app.post("/api/swap-offer")
def swap_offer(req: OfferRequest):
    oos = products_by_id[req.product_id]
    shopper = _shopper(req.shopper_id)

    t0 = time.perf_counter()
    safe, blocked = graph_backend.safe_candidates(oos["id"], shopper, req.learned)
    graph_ms = round((time.perf_counter() - t0) * 1000, 1)
    enriched_safe, unavailable = enrich_candidates(
        safe, oos, shopper, store_stock, STORE_ID, products_by_id)

    naive = _naive_pick(oos)
    naive_out = {**_slim(naive), "unsafe": _is_unsafe(naive, shopper),
                 "stock_level": store_stock.get(STORE_ID, {}).get(naive["id"], "high")} if naive else None

    base = {"oos": _slim(oos), "safe_count": len(enriched_safe), "blocked_count": len(blocked),
            "unavailable_count": len(unavailable),
            "checked_count": len(safe) + len(blocked), "graph_ms": graph_ms,
            "naive": naive_out,
            "blocked": [{"name": b["name"], "reason": b["blocked_reason"]} for b in blocked[:10]],
            "unavailable": [{"name": u["name"], "reason": u["blocked_reason"]} for u in unavailable[:10]]}

    if not enriched_safe:
        return {**base, "best": None, "alternatives": [], "rank_s": 0, "source": None}

    t1 = time.perf_counter()
    ranking = rank_and_explain(oos, enriched_safe, shopper)
    rank_s = round(time.perf_counter() - t1, 2)

    safe_by_id = {c["id"]: c for c in enriched_safe}

    def entry(r):
        cand = safe_by_id[r["product_id"]]
        return {**_slim(products_by_id[cand["id"]]), "reason": r["reason"],
                "weight": cand["weight"],
                "signals": {
                    "use_case_match": cand.get("use_case_match", []),
                    "certifications": cand.get("certifications", []),
                    "stock_level": cand.get("stock_level"),
                    "brand_match": cand.get("brand_match", False),
                    "nutrition_note": cand.get("nutrition_note"),
                },
                "business": cand.get("business", {}),
                "paths": graph_backend.explain_paths(oos["id"], cand, shopper)}

    best = next(r for r in ranking["ranking"] if r["product_id"] == ranking["best_id"])
    return {**base, "source": ranking["source"], "rank_s": rank_s, "best": entry(best),
            "alternatives": [entry(r) for r in ranking["ranking"]
                             if r["product_id"] != ranking["best_id"]]}


@app.post("/api/decide")
def decide(req: DecideRequest):
    """Pure learning step. The client stores the returned weight and passes it back."""
    old_w, _ = graph_backend.edge_weight(req.oos_id, req.chosen_id, req.learned)
    new_w = updated_weight(old_w, req.accepted)
    return {"edge": f"{req.oos_id}|{req.chosen_id}", "weight_before": old_w, "weight_after": new_w}


@app.post("/api/graph")
def graph_view(req: GraphRequest):
    """Subgraph around a product, queried from the active graph backend."""
    return graph_backend.graph_view(req.focus, req.learned)


# ---------------- ListingIQ: compliance QA ----------------

_LISTINGS = {p["id"]: listing_qa.generate_listing(p) for p in catalog}
_AUDITS = {p["id"]: listing_qa.audit(p, _LISTINGS[p["id"]], INGREDIENT_ALLERGENS) for p in catalog}


@app.get("/api/qa-summary")
def qa_summary():
    """Catalog-wide QA scoreboard: how many listings have issues, by severity."""
    rows, crit, warn, clean = [], 0, 0, 0
    for p in catalog:
        findings, score = _AUDITS[p["id"]]
        status = listing_qa.status_of(findings)
        if status == "critical":
            crit += 1
        elif status == "warning":
            warn += 1
        else:
            clean += 1
        rows.append({
            "id": p["id"], "name": p["name"], "category": p["category"].replace("_", " "),
            "status": status, "score": score,
            "critical": sum(1 for f in findings if f["severity"] == "critical"),
            "warning": sum(1 for f in findings if f["severity"] == "warning"),
            "top": findings[0]["title"] if findings else "Clean",
        })
    total = len(catalog)
    with_issues = crit + warn
    return {"total": total, "with_issues": with_issues, "critical": crit, "warning": warn,
            "clean": clean, "pct_issues": round(with_issues / total * 100) if total else 0, "rows": rows}


@app.get("/api/audit")
def audit_one(product_id: str):
    p = products_by_id[product_id]
    listing = _LISTINGS[product_id]
    findings, score = _AUDITS[product_id]
    return {
        "product": {"id": p["id"], "name": p["name"], "category": p["category"].replace("_", " "),
                    "ingredients": [i.replace("_", " ") for i in p["ingredients"]],
                    "true_allergens": [a.replace("_", " ") for a in p["allergens"]],
                    "diet_tags": p["diet_tags"]},
        "listing": listing, "findings": findings, "score": score,
        "status": listing_qa.status_of(findings)}


class FixRequest(BaseModel):
    product_id: str


@app.post("/api/fix")
def fix_listing(req: FixRequest):
    """LLM rewrites a compliant listing. Deterministic fallback if no key."""
    p = products_by_id[req.product_id]
    listing = _LISTINGS[req.product_id]
    findings, _ = _AUDITS[req.product_id]
    corrected = {
        "declared_allergens": sorted(p["allergens"]),
        "claims": [c for c in listing["claims"]
                   if c not in listing_qa.PROHIBITED_CLAIMS
                   and not (c == "vegan" and "vegan" not in p["diet_tags"])
                   and not (c == "gluten free" and "gluten_free" not in p["diet_tags"])
                   and not (c == "sugar free" and "sugar" in p["ingredients"])],
        "net_quantity": listing["net_quantity"] or listing_qa.PACK.get(p["category"], "1 unit"),
        "fssai_license": listing["fssai_license"] or "10012345000123",
        "veg_mark": listing["veg_mark_correct"]}
    key = get_api_key()
    rewrite = None
    if key and findings:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=key)
            prompt = (
                "You are a marketplace compliance editor. Rewrite this grocery listing so it is fully "
                "compliant: declare all allergens, drop false or prohibited claims, keep it honest and "
                "appealing. Return ONLY the corrected description, 2 short sentences.\n\n"
                f"Product: {p['name']}\nTrue ingredients: {', '.join(p['ingredients'])}\n"
                f"True allergens: {', '.join(p['allergens']) or 'none'}\nDiet: {', '.join(p['diet_tags'])}\n"
                f"Violations: {'; '.join(f['title'] for f in findings)}")
            resp = client.messages.create(model="claude-opus-4-8", max_tokens=300,
                                          messages=[{"role": "user", "content": prompt}])
            if resp.stop_reason != "refusal":
                rewrite = next((b.text for b in resp.content if b.type == "text"), None)
        except Exception:
            rewrite = None
    if not rewrite:
        rewrite = (f"{p['name']}. "
                   f"{'Contains ' + ', '.join(a.replace('_', ' ') for a in p['allergens']) + '. ' if p['allergens'] else ''}"
                   "Delivered fresh from QuickCart in minutes.")
    corrected["description"] = rewrite
    corrected["source"] = "claude" if (key and findings) else "fallback"
    return {"corrected": corrected}


@app.get("/api/recall")
def recall(ingredient: str):
    """Recall propagation: one traversal finds every SKU, listing, and at-risk
    shopper linked to a recalled ingredient. The graph does in milliseconds what
    a manual catalog sweep takes days to do."""
    key = ingredient.replace(" ", "_")
    impact = graph_backend.recall(key)
    aff = impact["products"]
    allergen = impact["allergen"] or INGREDIENT_ALLERGENS.get(key)
    cats = [category.replace("_", " ") for category in impact["categories"]]
    at_risk = [s["name"] for s in shoppers if allergen and allergen in s["avoids_allergens"]]
    return {"ingredient": ingredient.replace("_", " "),
            "allergen": (allergen or "none").replace("_", " "),
            "sku_count": len(aff), "categories": cats,
            "skus": [p["name"] for p in aff[:14]],
            "listing_count": len(aff), "shoppers_at_risk": at_risk}


@app.get("/api/platform")
def platform():
    """Platform-level snapshot for the operator console."""
    qa = qa_summary()
    graph_stats = graph_backend.stats()
    levels = store_stock[STORE_ID]
    out_pct = round(sum(1 for lvl in levels.values() if lvl == "out") / len(catalog) * 100, 1)
    avg_margin = round(sum(p["margin_pct"] for p in catalog) / len(catalog), 1)
    clearance_count = sum(1 for p in catalog if p["clearance"])
    return {"products": len(catalog), "categories": len({p["category"] for p in catalog}),
            "graph_backend": graph_backend.name, "graph_persistent": graph_backend.persistent,
            "graph_nodes": graph_stats["nodes"], "graph_edges": graph_stats["edges"],
            "listings_audited": qa["total"], "listings_with_issues": qa["with_issues"],
            "critical": qa["critical"], "shoppers": len(shoppers),
            "store_id": STORE_ID, "store_out_pct": out_pct,
            "avg_margin_pct": avg_margin, "clearance_skus": clearance_count}


@app.get("/api/health")
def health():
    """Readiness signal, including the active graph implementation."""
    return {"status": "ok", "graph": graph_backend.health(),
            "products": len(catalog), "claude": claude_available()}


# Local development only: serve the frontend. On Vercel, static files are
# served by the platform and this block is skipped.
if not os.environ.get("VERCEL"):
    from fastapi.staticfiles import StaticFiles
    public_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "public")
    if os.path.isdir(public_dir):
        app.mount("/", StaticFiles(directory=public_dir, html=True), name="static")
