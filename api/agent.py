"""SwapIQ GenAI layer: Claude ranks graph-cleared candidates and writes the reason.

Only receives candidates that already passed the knowledge graph safety filter.
Falls back to a deterministic ranker if no ANTHROPIC_API_KEY is configured,
so the demo never stalls.
"""

import json
import os

MODEL = "claude-opus-4-8"

RANKING_SCHEMA = {
    "type": "object",
    "properties": {
        "best_id": {"type": "string"},
        "ranking": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["product_id", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["best_id", "ranking"],
    "additionalProperties": False,
}


def get_api_key():
    """Env var first (Vercel), then a local secrets file for laptop demos."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    try:
        import tomllib
        candidates = [
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                         ".streamlit", "secrets.toml"),
        ]
        for path in candidates:
            if os.path.exists(path):
                with open(path, "rb") as f:
                    k = tomllib.load(f).get("ANTHROPIC_API_KEY")
                    if k:
                        os.environ["ANTHROPIC_API_KEY"] = k
                        return k
    except Exception:
        pass
    return None


def claude_available():
    return bool(get_api_key())


def rank_and_explain(oos_product, candidates, shopper, top_n=3):
    candidates = candidates[:6]
    result = _rank_with_claude(oos_product, candidates, shopper, top_n)
    if result:
        result["source"] = "claude"
        return result
    result = _rank_fallback(oos_product, candidates, shopper, top_n)
    result["source"] = "fallback"
    return result


def _rank_with_claude(oos_product, candidates, shopper, top_n):
    key = get_api_key()
    if not key:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
    except Exception:
        return None

    context = {
        "out_of_stock": {"name": oos_product["name"], "price": oos_product["price"]},
        "shopper": {
            "avoids_allergens": shopper["avoids_allergens"],
            "diet": shopper["diet"],
            "budget_sensitive": shopper.get("budget_sensitive", False),
        },
        "candidates": [
            {"product_id": c["id"], "name": c["name"], "price": c["price"],
             "diet_tags": c["diet_tags"], "past_acceptance_weight": c["weight"]}
            for c in candidates
        ],
    }
    prompt = (
        "You are a grocery substitution assistant. An ordered item is out of stock. "
        "Every candidate below has ALREADY passed a knowledge-graph safety check for this "
        "shopper's allergies and diet, so all are safe. Your job is judgment and language: "
        f"rank the top {top_n} candidates by how well they replace the out-of-stock item "
        "(same use, price closeness, past acceptance weight), and write ONE short, honest, "
        "customer-facing reason for each. Mention the acceptance rate as a percentage when "
        "the weight is above 0.5.\n\n"
        f"Context:\n{json.dumps(context, indent=1)}"
    )
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            output_config={"format": {"type": "json_schema", "schema": RANKING_SCHEMA}},
            messages=[{"role": "user", "content": prompt}],
        )
        if response.stop_reason == "refusal":
            return None
        text = next(b.text for b in response.content if b.type == "text")
        data = json.loads(text)
        valid_ids = {c["id"] for c in candidates}
        data["ranking"] = [r for r in data["ranking"] if r["product_id"] in valid_ids][:top_n]
        if not data["ranking"]:
            return None
        if data["best_id"] not in valid_ids:
            data["best_id"] = data["ranking"][0]["product_id"]
        return data
    except Exception:
        return None


def _rank_fallback(oos_product, candidates, shopper, top_n):
    def score(c):
        price_gap = abs(c["price"] - oos_product["price"]) / max(oos_product["price"], 1)
        return c["weight"] + 0.15 * max(0, 1 - price_gap)

    ranked = sorted(candidates, key=score, reverse=True)[:top_n]
    ranking = []
    for c in ranked:
        bits = [f"Same category as {oos_product['base_name']}"]
        diff = c["price"] - oos_product["price"]
        if diff < 0:
            bits.append(f"Rs. {-diff} cheaper")
        elif diff > 0:
            bits.append(f"Rs. {diff} more")
        else:
            bits.append("same price")
        if shopper["diet"]:
            bits.append(", ".join(shopper["diet"]))
        if shopper["avoids_allergens"]:
            bits.append("free of " + ", ".join(a.replace("_", " ") for a in shopper["avoids_allergens"]))
        if c["weight"] > 0.5:
            bits.append(f"{round(c['weight'] * 100)}% of similar shoppers accepted this swap")
        ranking.append({"product_id": c["id"], "reason": ". ".join(bits) + "."})
    return {"best_id": ranking[0]["product_id"], "ranking": ranking}
