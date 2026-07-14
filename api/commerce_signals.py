"""Commerce signals: ranking factors beyond safety and availability.

The graph answers one hard question: is this candidate safe for this shopper.
That boundary never moves. Everything here is a SECOND layer that decides
which safe candidate is actually the best one to offer, and it reasons over
factors the safety graph was never meant to hold:

  - functional fit     (USED_FOR: does it serve the same purpose)
  - nutrition          (comparable calories/sugar/protein, not just allergen-free)
  - real store stock   (a safe candidate that is ALSO out of stock helps no one)
  - certifications     (organic, halal, Jain-friendly)
  - brand affinity      (this shopper's own accept/reject history)
  - business economics  (margin, clearance stock) - shown to the operator, not the shopper

A candidate that is safe but out of stock at the fulfilling store moves to a
separate `unavailable` bucket. It is not unsafe, so it is never confused with
an allergy block; it is simply not offerable right now.
"""


def _nutrition_note(oos, cand):
    on, cn = oos.get("nutrition"), cand.get("nutrition")
    if not on or not cn:
        return None
    d_cal = cn["calories"] - on["calories"]
    d_sugar = cn["sugar_g"] - on["sugar_g"]
    if d_sugar <= -3:
        return f"{abs(round(d_sugar))}g less sugar per 100g"
    if abs(d_cal) <= max(10, on["calories"] * 0.12):
        return "comparable nutrition"
    if d_cal > 0:
        return f"{round(d_cal)} more kcal per 100g"
    return f"{abs(round(d_cal))} fewer kcal per 100g"


def enrich_candidates(safe, oos, shopper, store_stock, store_id, products_by_id):
    """Attach commerce signals to graph-safe candidates, split off ones that
    are also out of stock at the fulfilling store, and reorder by a composite
    score. Returns (enriched_sorted_candidates, unavailable_candidates).

    Not capped here: callers need the true safe-and-available count for
    `safe_count`. agent.rank_and_explain caps to 6 before ranking/prompting.
    """
    stock_map = store_stock.get(store_id, {})
    oos_uses = set(oos.get("use_cases", []))
    preferred_brand = shopper.get("preferred_brand")

    enriched, unavailable = [], []
    for c in safe:
        full = products_by_id[c["id"]]
        level = stock_map.get(c["id"], "high")
        if level == "out":
            unavailable.append({**c, "stock_level": level,
                                 "blocked_reason": f"in stock in the catalog, but out of stock "
                                                   f"right now at {store_id}"})
            continue

        use_match = sorted(oos_uses & set(full.get("use_cases", [])))
        brand_match = preferred_brand is not None and full["brand"] == preferred_brand
        certs = full.get("certifications", [])
        note = _nutrition_note(oos, full)
        margin_pct = full.get("margin_pct", 0) or 0
        clearance = bool(full.get("clearance"))

        smart_score = (
            c["weight"] * 0.55
            + (0.18 if use_match else 0.0)
            + (0.10 if level == "high" else 0.03)
            + (0.08 if brand_match else 0.0)
            + (0.05 if clearance else 0.0)
            + min(margin_pct, 40) / 40 * 0.04
        )
        enriched.append({
            **c,
            "brand": full["brand"],
            "use_cases": full.get("use_cases", []),
            "use_case_match": use_match,
            "certifications": certs,
            "stock_level": level,
            "brand_match": brand_match,
            "nutrition_note": note,
            "business": {"margin_pct": margin_pct, "clearance": clearance},
            "smart_score": round(smart_score, 4),
        })

    enriched.sort(key=lambda c: c["smart_score"], reverse=True)
    return enriched, unavailable
