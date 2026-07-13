# SwapIQ: Low-Level Design

Version 2.0 - July 2026

## 1. System overview

```text
Customer browser
  public/index.html       QuickCart storefront + SwapIQ checkout moment
  public/qa.html          ListingIQ compliance test suite
  public/console.html     Operator console, recall and graph explorer
        |
        | JSON over HTTP
        v
FastAPI API (api/index.py)
  +-- data_gen.py         deterministic 508-SKU catalog and four shoppers
  +-- graph_core.py       NetworkX graph, safety traversal and learning
  +-- agent.py            Claude ranking/explanation + deterministic fallback
  +-- listings.py         synthetic listing generator and compliance rules
        |
        +-- Current demo: in-memory NetworkX DiGraph
        +-- Production path: Neo4j via neo4j_loader.py
```

The frontend is plain HTML, CSS and JavaScript with no build step or external runtime dependency. FastAPI is compatible with local Uvicorn and Vercel serverless routing. Learned substitution weights and the decision log are stored in browser `localStorage` and sent with relevant requests, keeping the demo API stateless.

## 2. Runtime and deployment

- Local command: `uvicorn api.index:app --reload --port 8000`.
- Vercel routes `/api/*` to `api/index.py` and serves `public/` statically.
- The catalog is deterministic from a fixed seed and builds once per API process.
- The live demo graph is a NetworkX `DiGraph`; no Neo4j connection is required.
- `ANTHROPIC_API_KEY` enables Claude. Without it, the deterministic ranker and listing fixer preserve the response shape.

## 3. Data model

### Product

```json
{
  "id": "P001",
  "name": "FreshFarm Almond Milk Unsweetened",
  "base_name": "Almond Milk Unsweetened",
  "brand": "FreshFarm",
  "category": "plant_milk",
  "price": 271,
  "price_tier": "mid",
  "ingredients": ["water", "almonds", "sea_salt"],
  "allergens": ["tree_nuts"],
  "diet_tags": ["vegan", "vegetarian", "gluten_free"]
}
```

Allergens and diet tags are derived from ingredient maps in `data_gen.py`; they are not assigned independently to products.

### Shopper

```json
{
  "id": "S1",
  "name": "Sneha (nut allergy, vegan)",
  "avoids_allergens": ["tree_nuts", "peanuts"],
  "diet": ["vegan"],
  "budget_sensitive": false
}
```

### Listing

Listing records in `listings.py` contain title, description, claims, declared allergens, net quantity, FSSAI license, dietary mark and image count. Realistic errors are deterministically planted so rule execution is testable.

## 4. Knowledge-graph schema

| Element | Identifier | Relationship |
|---|---|---|
| Product | `P001` | Source node for catalog facts |
| Ingredient | `ing:almonds` | `(Product)-[:CONTAINS]->(Ingredient)` |
| Allergen | `alg:tree_nuts` | `(Ingredient)-[:IS_A]->(Allergen)` |
| Diet tag | `tag:vegan` | `(Product)-[:HAS_TAG]->(DietTag)` |
| Category | `cat:plant_milk` | `(Product)-[:IN_CATEGORY]->(Category)` |
| Swap edge | product pair | `(Product)-[:SWAP_OK {weight}]->(Product)` |

The current dataset produces 624 nodes and 14,010 edges. Swap priors combine same base product, shared ingredients and price closeness, then yield to learned browser-session weights after customer decisions.

## 5. Safety traversal

`safe_candidates(G, oos_id, shopper, learned)` evaluates same-category candidates:

1. Traverse candidate `CONTAINS -> IS_A` paths and intersect allergens with `shopper.avoids_allergens`.
2. Require all shopper diet tags to exist in the candidate's derived tags.
3. For budget-sensitive shoppers, enforce the configured price ceiling.
4. Return safe candidates sorted by effective `SWAP_OK` weight plus blocked candidates with human-readable graph paths.

This is the hard safety boundary. Blocked candidates never reach Claude.

## 6. Ranking and explanation

`agent.rank_and_explain()` sends the top safe candidates to `claude-opus-4-8` using a structured JSON schema:

```json
{
  "best_id": "P123",
  "ranking": [
    {"product_id": "P123", "reason": "Nut-free vegan option at nearly the same price."}
  ]
}
```

Returned IDs are validated against the supplied candidate set. Missing credentials, network failures, refusals, malformed JSON or invalid IDs trigger the deterministic fallback.

## 7. Learning loop

`updated_weight(old, accepted, lr=0.25)` uses bounded exponential updates:

```text
accept:  new = old + 0.25 * (1 - old)
decline: new = old - 0.25 * old
```

The browser persists `{edge_key: {weight, decisions}}` and passes it to offer, graph and decision endpoints. Server-side storage is deliberately omitted in the demo; production moves this state to a tenant/store scoped database.

## 8. ListingIQ rule engine

The compliance pipeline separates decision logic from language generation:

1. `generate_listings()` derives listing content from the catalog and inserts deterministic defects.
2. `audit_listing()` runs rule checks for undeclared allergens, false vegan/gluten-free claims, prohibited marketing claims, missing FSSAI license or net quantity, dietary-mark mismatch and insufficient images.
3. `/api/audit` returns score, severity, rule ID, evidence and fix.
4. `/api/fix` asks Claude to rewrite the listing while deterministic findings remain authoritative; fallback rewriting keeps the workflow available offline.

## 9. Recall propagation

`GET /api/recall?ingredient=almonds` normalizes the ingredient key and returns linked SKUs, categories, listing count, mapped allergen and shopper profiles at risk. The current endpoint traverses the in-memory catalog facts; the Neo4j production implementation uses the equivalent graph query and can extend to suppliers, batches and orders.

## 10. API contract

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/bootstrap` | Products, shoppers, demo carts and Claude availability |
| POST | `/api/rag-offer` | Similarity-only comparison recommendation |
| POST | `/api/safety-check` | Deterministic graph filtering without an LLM call |
| POST | `/api/swap-offer` | Safe candidates, ranking, explanation and baseline comparison |
| POST | `/api/decide` | Pure learned-weight update |
| POST | `/api/graph` | Product-centered graph nodes and edges for canvas rendering |
| GET | `/api/qa-summary` | Aggregate ListingIQ scores and issue counts |
| GET | `/api/audit?product_id=P001` | Full listing audit for one product |
| POST | `/api/fix` | Corrected listing generated from cited findings |
| GET | `/api/recall?ingredient=almonds` | Recall impact across linked catalog entities |
| GET | `/api/platform` | Console metrics for catalog, graph and listing QA |

## 11. Frontend state and flows

### QuickCart

`public/index.html` maintains shopper, mode, safe-only filter, cart, category, search, order and offer state in one client object. It renders the full home page, category/search results, cart drawer, stockout moment and checkout views. The engine control is kept in a small demo dock so the shopping header remains consumer-facing.

### ListingIQ

`public/qa.html` loads summary data, filters listings by severity, opens detailed audits and calls the fix endpoint. Charts and results are dependency-free.

### Console

`public/console.html` combines `/api/platform`, `/api/bootstrap`, `/api/recall` and `/api/graph` into the integration animation, platform metrics, app catalog, recall report and canvas graph explorer.

## 12. NetworkX and Neo4j status

| Current demo | Production path |
|---|---|
| NetworkX in API memory | Neo4j cluster or managed Aura instance |
| 508 synthetic SKUs | Retailer catalog ETL with millions of SKUs |
| Browser-local learned weights | Tenant/store/region-scoped persistent state |
| Catalog facts rebuilt per process | Incremental product, supplier and batch updates |
| Ingredient recall lookup | Cypher traversal across ingredient, supplier, batch, order and shopper nodes |

`neo4j_loader.py` loads the same product, ingredient, allergen, diet and category schema into Neo4j. `NEO4J_SETUP.md` contains the local setup and Cypher safety query. The deployed web API does not currently query Neo4j and must be described as Neo4j-ready rather than Neo4j-powered.

## 13. Verification

- Python modules compile with `python -m py_compile`.
- `/api/bootstrap` returns 508 products, 24 categories and four shoppers.
- `/api/platform` reports 624 nodes, 14,010 edges and all 508 listings audited.
- Desktop and 390-pixel mobile layouts render without horizontal page overflow.
- Browser-tested flow: search -> cart -> RAG risk -> SwapIQ safe offer -> accept -> checkout -> order placed.
- Browser console contains no errors or warnings during the verified journey.
