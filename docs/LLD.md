# SwapIQ: Low-Level Design

Version 3.0 - July 2026

## 1. System overview

```text
Customer browser
  public/index.html       QuickCart storefront + SwapIQ checkout moment
  public/qa.html          ListingIQ compliance test suite
  public/console.html     Operator console: integration, recall, graph explorer
        |
        | JSON over HTTP
        v
FastAPI API (api/index.py)
  +-- data_gen.py          deterministic 579-SKU, two-vertical catalog + 5 shoppers
  +-- graph_core.py        NetworkX graph builder + pure learning function
  +-- graph_backend.py     Neo4j backend + NetworkX backend, one shared contract
  +-- commerce_signals.py  ranking layer ABOVE the safety graph (fit, nutrition,
  |                         stock, certifications, brand, business economics)
  +-- agent.py             Claude ranking/explanation + deterministic fallback
  +-- listings.py          synthetic listing generator + compliance rule engine
        |
        +-- Neo4j: persistent production graph and Cypher safety traversal
        +-- NetworkX: explicit zero-infrastructure fallback (default on Vercel)
```

The frontend is plain HTML, CSS and JavaScript with no build step and no external runtime dependency (offline-safe; the only network calls are to this API). FastAPI runs under local Uvicorn and as a Vercel serverless function. The catalog and seeded graph are deterministic from a fixed seed and build once per process. Learned substitution weights and the decision log live in browser `localStorage` and are sent with the requests that need them, so the service is stateless and serverless-friendly.

## 2. The two-layer decision model

This is the single most important design decision and the reason the product is defensible.

- **Layer 1, safety (the knowledge graph).** A hard, deterministic gate. A candidate either has a graph path to something the shopper must avoid, or it does not. This layer is the only thing allowed to say "no", and nothing it rejects ever reaches the LLM. It is implemented as graph traversal so it is provable and auditable, not a score.
- **Layer 2, ranking (commerce_signals.py + agent.py).** Ordinary code and the LLM, running only on what Layer 1 already cleared. It decides which safe candidate is *best* using functional fit, nutrition, real stock, certifications, brand affinity and business economics. It can reorder; it can never override safety.

Any factor whose failure is dangerous belongs in Layer 1. Any factor that only affects preference belongs in Layer 2. Keeping them separate is what lets the safety guarantee stay provable while the ranking stays rich.

## 3. Runtime and deployment

- Local: `python run_server.py` (honors `PORT`, defaults to 8020) or `uvicorn api.index:app --port 8000`.
- Vercel: `vercel.json` rewrites `/api/*` to the `api/index.py` serverless function and maps `/`, `/qa.html`, `/console.html` to the static pages in `public/`. The `if not os.environ.get("VERCEL")` guard in `index.py` skips the local static mount in production, where Vercel serves the static files.
- Graph backend selection (`SWAPIQ_GRAPH_BACKEND`): `neo4j` requires a reachable database and fails startup otherwise; `auto` (default) uses Neo4j when `NEO4J_URI` is set, else NetworkX; `networkx` forces the fallback. On Vercel with no database, leave it unset so it resolves to NetworkX.
- `ANTHROPIC_API_KEY` enables Claude. Without it, the deterministic ranker and listing rewriter keep the same response shape.

## 4. Data model

### Product

```json
{
  "id": "P001",
  "name": "FreshFarm Almond Milk Unsweetened",
  "base_name": "Almond Milk Unsweetened",
  "brand": "FreshFarm",
  "category": "plant_milk",
  "vertical": "grocery",
  "price": 271,
  "price_tier": "mid",
  "ingredients": ["water", "almonds", "sea_salt"],
  "allergens": ["tree_nuts"],
  "diet_tags": ["vegan", "vegetarian", "gluten_free"],
  "use_cases": ["cereal", "coffee", "cooking"],
  "nutrition": {"calories": 49, "sugar_g": 2.8, "protein_g": 1.0},
  "certifications": ["jain_friendly", "halal"],
  "cost_price": 168,
  "margin_pct": 38.0,
  "clearance": false
}
```

`allergens`, `diet_tags`, `use_cases`, `nutrition` and `certifications` are all *derived* in `data_gen.py`, never hand-assigned per SKU, so the reasoning is honest: bad ingredient data produces a wrong-but-consistent graph, exactly as in production. `nutrition` is `null` for non-food categories rather than fabricated. `cost_price`, `margin_pct` and `clearance` are operator-only economics.

### Two verticals, one pipeline

The catalog spans **grocery** (508 SKUs, 24 categories) and **beauty/haircare** (71 SKUs, 5 categories), 579 SKUs and 19 brands total. `generate_catalog()` loops over `(vertical, templates, brand_pool)` pairs through one code path. In beauty, "allergen" is a dermatological conflict class (fragrance, sulfates, silicones, retinoids, salicylates), and the `NON_VEGAN` rule additionally excludes beeswax/lanolin/carmine. No graph, ranking, compliance or recall code is vertical-aware. Adding a vertical is a data change.

### Shopper

```json
{
  "id": "S1",
  "name": "Sneha (nut allergy, vegan)",
  "avoids_allergens": ["tree_nuts", "peanuts"],
  "diet": ["vegan"],
  "budget_sensitive": false,
  "preferred_brand": "GreenLeaf"
}
```

Five personas: nut+vegan, gluten-free, budget/no-constraint, egg+sesame, and fragrance+sulfate (skincare). `preferred_brand` feeds Layer-2 brand affinity.

### Listing

`listings.py` records carry title, description, claims, declared allergens, net quantity, FSSAI license, dietary mark and image count. Realistic defects are deterministically planted so the rule engine has real violations to catch.

## 5. Knowledge-graph schema (Layer 1)

| Element | Identifier | Relationship |
|---|---|---|
| Product | `P001` | Source node for catalog facts |
| Ingredient | `ing:almonds` | `(Product)-[:CONTAINS]->(Ingredient)` |
| Allergen / conflict class | `alg:tree_nuts`, `alg:fragrance` | `(Ingredient)-[:IS_A]->(Allergen)` |
| Diet tag | `tag:vegan` | `(Product)-[:HAS_TAG]->(DietTag)` |
| Category | `cat:plant_milk` | `(Product)-[:IN_CATEGORY]->(Category)` |
| Swap edge | product pair | `(Product)-[:SWAP_OK {weight}]->(Product)` |

The current dataset produces about 722 nodes and 15,491 edges. Swap priors combine same base product, shared ingredients and price closeness, then yield to browser-session learned weights after customer decisions. Note that Layer-2 signals (use case, nutrition, stock, certifications, brand, margin) are product/shopper attributes read directly by `commerce_signals.py`, not graph nodes; promoting them to real edges is a planned refinement (PRD Section 11).

## 6. Safety traversal (Layer 1)

`graph_backend.safe_candidates(oos_id, shopper, learned)` evaluates same-category candidates. In Neo4j mode a single Cypher query traverses category, ingredient, allergen, diet-tag and `SWAP_OK` relationships; NetworkX implements the identical contract in memory.

1. Traverse each candidate's `CONTAINS -> IS_A` paths and intersect the allergen/conflict classes with `shopper.avoids_allergens`.
2. Require every shopper diet tag to be present in the candidate's derived tags.
3. For budget-sensitive shoppers, enforce the price ceiling.
4. Return safe candidates plus blocked candidates, each with a cited, human-readable reason.

This is the hard safety boundary. Blocked candidates never reach Layer 2 or the LLM.

## 7. Commerce-signals ranking (Layer 2)

`commerce_signals.enrich_candidates()` runs on the safe set only. It:

1. Splits out candidates that are safe but out of stock at the fulfilling store into a distinct `unavailable` bucket (not confused with unsafe).
2. Attaches, per candidate: `use_case_match` (functional fit vs the out-of-stock item), `nutrition_note` (comparable / lower sugar / calorie delta; absent for non-food), `stock_level`, `certifications`, `brand_match`, and operator-only `business` (`margin_pct`, `clearance`).
3. Computes a composite `smart_score` (safety weight 0.55, functional fit 0.18, in-stock 0.10, brand match 0.08, clearance 0.05, margin up to 0.04) and sorts.

`agent.rank_and_explain()` then sends the top safe-and-available candidates to `claude-opus-4-8` with a structured JSON schema and an explicit instruction never to mention margin, cost or clearance to the shopper. The deterministic fallback reproduces the same ordering and a templated reason when Claude is unavailable.

## 8. Learning loop

`updated_weight(old, accepted, lr=0.25)` uses bounded exponential updates:

```text
accept:  new = old + 0.25 * (1 - old)
decline: new = old - 0.25 * old
```

The browser persists `{edge_key: {weight, decisions}}` and passes it to the offer, graph and decision endpoints. Server-side storage is omitted in the demo; production moves this to tenant/store-scoped storage.

## 9. ListingIQ rule engine

Separates decision from language, the same principle as the two-layer model:

1. `generate_listing()` derives listing content from the catalog and inserts deterministic defects.
2. `audit()` runs deterministic rules: undeclared allergens, false vegan/gluten-free claims, prohibited marketing claims, missing FSSAI license or net quantity, dietary-mark mismatch, insufficient images.
3. `/api/audit` returns score, severity, rule ID, evidence and fix.
4. `/api/fix` asks Claude to rewrite the listing; the deterministic findings remain authoritative, and a fallback rewrite keeps it working offline. Runs across both verticals with no rule changes.

## 10. Recall propagation

`GET /api/recall?ingredient=<name>` returns the linked SKUs, categories, listing count, mapped allergen and at-risk shopper profiles. Neo4j executes the ingredient-to-product/category/allergen traversal in Cypher; NetworkX implements the same contract from in-memory facts.

## 11. API contract

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/bootstrap` | Products, shoppers, demo carts, store id, Claude and graph status |
| POST | `/api/rag-offer` | Similarity-only baseline recommendation (the A/B comparison) |
| POST | `/api/safety-check` | Deterministic filtering; returns safe / blocked / unavailable counts, no LLM |
| POST | `/api/swap-offer` | Safe candidates, Layer-2 signals, Claude ranking + explanation |
| POST | `/api/decide` | Pure learned-weight update |
| POST | `/api/graph` | Product-centered nodes and edges for the canvas explorer |
| GET | `/api/qa-summary` | Aggregate ListingIQ scores and issue counts |
| GET | `/api/audit?product_id=P001` | Full listing audit for one product |
| POST | `/api/fix` | Corrected listing generated from cited findings |
| GET | `/api/recall?ingredient=almonds` | Recall impact across linked catalog entities |
| GET | `/api/platform` | Console metrics: catalog, graph, listing QA, store stock, margin, clearance |
| GET | `/api/health` | Readiness plus active graph backend and persistence state |

`safe`, `blocked` and `unavailable` counts always sum to `checked`. `swap-offer` candidates carry `signals` (customer-facing) and `business` (operator-facing) separately.

## 12. Frontend

### QuickCart (`public/index.html`)

One client state object holds shopper, engine mode (RAG vs SwapIQ), safe-only filter, cart, category, search, order and offer. It renders the multi-section home (banner, category tiles, per-category rails), category/search views, cart drawer, the pre-checkout substitution "moment" (customer phone on one side, the SwapIQ engine and ranking-factors panel on the other), checkout and confirmation. Category labels, colors, pack sizes and product icons all fall back gracefully, so new categories render without frontend changes.

### ListingIQ (`public/qa.html`)

Catalog-wide QA scoreboard with severity tiles and a per-listing report (findings, cited rules, fixes, AI rewrite). Covers every vertical automatically.

### Console (`public/console.html`)

Operator front door: a simulated store-connection flow with a live-building graph, platform and business/operations metrics, recall propagation, the graph explorer, and links to the store and ListingIQ as apps on the shared graph.

## 13. Tests

`tests/test_graph_backend.py` asserts the NetworkX and Neo4j backends return identical safe/blocked sets and identical graph counts, so the fallback is a true parity implementation, not an approximation.

## 14. Planned (see PRD Section 11)

Post-purchase returns/exchange (reusing the substitution traversal), a third compatibility-shaped vertical (electronics), an explicit config-driven attribute schema, and time-series console insights.
