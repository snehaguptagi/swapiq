"""In-process smoke test for the SwapIQ API (no network needed)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "api"))

from index import bootstrap, swap_offer, decide, graph_view, OfferRequest, DecideRequest, GraphRequest

b = bootstrap()
print(f"bootstrap: claude={b['claude']}, products={len(b['products'])}, shoppers={len(b['shoppers'])}")

o = swap_offer(OfferRequest(product_id="P001", shopper_id="S1", learned={}))
print(f"offer: best={o['best']['name']} | source={o['source']} | safe={o['safe_count']} | "
      f"blocked={o['blocked_count']} | {o['graph_ms']}ms + {o['rank_s']}s")
print(f"naive: {o['naive']['name']} unsafe={o['naive']['unsafe']}")
print(f"reason: {o['best']['reason']}")
assert o["naive"]["unsafe"], "naive pick should be unsafe for nut-allergic shopper"
assert all("cashew" not in a["name"].lower() for a in [o["best"]] + o["alternatives"]), "SAFETY VIOLATION"

d = decide(DecideRequest(oos_id="P001", chosen_id=o["best"]["id"], accepted=True, learned={}))
print(f"decide: {d['weight_before']} -> {d['weight_after']}")

learned = {d["edge"]: {"weight": d["weight_after"], "decisions": 1}}
o2 = swap_offer(OfferRequest(product_id="P001", shopper_id="S1", learned=learned))
print(f"learned applied: best weight now {o2['best']['weight']} (was {o['best']['weight']})")

g = graph_view(GraphRequest(focus="P001", learned=learned))
print(f"graph: {len(g['nodes'])} nodes, {len(g['edges'])} edges")
print("ALL CHECKS PASSED")
