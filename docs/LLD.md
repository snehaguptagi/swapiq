# SwapIQ: Low-Level Design

## 1. System overview

```
Browser (public/index.html)
  |  localStorage: learned swap confidence + decision log (per session)
  |
  |  GET  /api/bootstrap      catalog, shoppers, demo carts, Claude status
  |  POST /api/swap-offer     {product_id, shopper_id, learned} -> offer
  |  POST /api/decide         {oos_id, chosen_id, accepted, learned} -> new weight
  |  POST /api/graph          {focus, learned} -> subgraph for rendering
  v
FastAPI (api/index.py, Vercel serverless)
  |
  +-- graph_core.py   NetworkX DiGraph, safety traversal, pure learning step
  +-- agent.py        Claude ranking (claude-opus-4-8, structured JSON) + fallback
  +-- data_gen.py     deterministic synthetic catalog (seeded)
```

The API is stateless. The graph is deterministic and rebuilt per serverless instance (about 260 nodes, builds in milliseconds). Learned state travels with each request from the browser, which makes the demo deployable with zero infrastructure and keeps concurrent sessions isolated.

## 2. Data model

### Product (data_gen.py)

```
{ id, name, base_name, brand, category, price, price_tier,
  ingredients: [str], allergens: [str], diet_tags: [str] }
```

Allergens and diet tags are derived from the ingredient list through two ground-truth maps (INGREDIENT_ALLERGENS, NON_VEGAN, GLUTEN_INGREDIENTS), never hand-assigned. This keeps the graph reasoning honest: if the ingredient list is wrong, the graph is wrong, exactly as in production.

### Graph schema (graph_core.py)

| Element | Form | Meaning |
|---|---|---|
| Product node | `P001` | One SKU with all attributes |
| Ingredient node | `ing:almonds` | Linked from products |
| Allergen node | `alg:tree_nuts` | Linked from ingredients |
| Diet tag node | `tag:vegan` | Linked from products |
| Category node | `cat:plant_milk` | Linked from products |
| CONTAINS edge | product -> ingredient | From the label |
| IS_A edge | ingredient -> allergen | Ground-truth map |
| HAS_TAG edge | product -> diet tag | Derived |
| IN_CATEGORY edge | product -> category | Catalog |
| SWAP_OK edge | product -> product, weight 0..1 | Seeded prior + learning |

SWAP_OK priors are seeded from attribute similarity: same base product across brands +0.30, shared ingredients up to +0.18, price closeness up to +0.12, floor 0.35, cap 0.95.

## 3. The safety traversal

`safe_candidates(G, oos_id, shopper, learned)` for every same-category product:

1. **Allergen check:** product -CONTAINS-> ingredient -IS_A-> allergen, intersected with `shopper.avoids_allergens`. Any hit removes the candidate with a cited reason.
2. **Diet check:** shopper diet tags must be a subset of the candidate's derived tags.
3. **Budget check:** if the shopper is budget sensitive, price must be within 115 percent of the out-of-stock item.

Returns (safe sorted by SWAP confidence descending, blocked with reasons). Deterministic, about 1 ms for 200 SKUs. The blocked list is surfaced in the UI as proof of work.

## 4. The ranking layer

`rank_and_explain(oos, candidates, shopper)` sends the top 6 safe candidates to Claude (`claude-opus-4-8`) with a structured output JSON schema:

```
{ best_id: str, ranking: [{ product_id: str, reason: str }] }
```

The prompt states explicitly that all candidates already passed the safety check, so the model's job is judgment and language only: rank by fit (same use, price closeness, past acceptance weight) and write one honest customer-facing line each. Responses are validated against the candidate id set; any failure (no key, network, refusal, invalid ids) falls through to a deterministic ranker with the same response shape, so the demo cannot stall.

## 5. The learning loop

`updated_weight(old, accepted, lr=0.25)`:

```
accept:  w' = w + 0.25 * (1 - w)     0.59 -> 0.69 -> 0.77 ...
decline: w' = w - 0.25 * w           0.59 -> 0.44 -> 0.33 ...
```

The client stores `{edge_key: {weight, decisions}}` in localStorage and passes it with every request; `edge_weight()` gives the learned value precedence over the seeded prior. Asymptotic, bounded in (0, 1), and immediately visible in the demo (the offer's cited acceptance percentage moves after each decision).

## 6. The similarity baseline (for the comparison)

`_naive_pick(oos)` emulates an embedding recommender: name similarity plus a strong bonus for shared allergen families and shared ingredients, which is how embeddings actually cluster products (nut milk next to nut milk). No safety awareness. For the nut-allergic persona and almond milk it deterministically selects cashew milk, which the UI flags as the suggestion SwapIQ's graph deleted before ranking.

## 7. API contract

### POST /api/swap-offer

Request: `{ product_id, shopper_id, learned }`

Response:

```
{ oos: {id, name, price, category, allergens},
  checked_count, safe_count, blocked_count, graph_ms, rank_s,
  source: "claude" | "fallback",
  best: { id, name, price, reason, weight, paths: [str] },
  alternatives: [same shape],
  blocked: [{name, reason}],
  naive: {id, name, price, allergens, unsafe: bool} }
```

### POST /api/decide

Request: `{ oos_id, chosen_id, accepted, learned }`
Response: `{ edge, weight_before, weight_after }` (pure function, client persists)

### POST /api/graph

Request: `{ focus, learned }`
Response: `{ nodes: [{id, type, label}], edges: [{from, to, label}] }` rendered by a dependency-free canvas radial layout in the frontend.

## 8. Frontend

Single self-contained `public/index.html`, vanilla JS, no build step, no external dependencies (works offline except the Claude call server-side). Structure: header with ambient session stats, an impact strip that appears after the first decision (projection with adjustable assumptions), the two-panel demo (order, response), and a footer with contextual modals (graph explorer, API view, session log, reset). All state in localStorage.

## 9. Production path

| Demo | Production |
|---|---|
| NetworkX in memory, 200 SKUs | Neo4j, same schema, millions of SKUs |
| Learned weights in localStorage | Retailer-side store keyed by region/store |
| Synthetic catalog | Catalog ETL + LLM extraction from FSSAI ingredient labels |
| Stockout via button | Picker-app event on a queue |
| One Claude call per stockout | Same, roughly 1 second and under a rupee per event |
