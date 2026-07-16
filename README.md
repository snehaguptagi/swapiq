# SwapIQ

**The trust-and-safety graph layer for ecommerce catalogs.** SwapIQ turns any catalog into a verified graph of products, ingredients, attributes, allergens and buyer constraints, then runs every safety-sensitive workflow off it: safe out-of-stock substitution, listing-compliance auditing, safe discovery and recall propagation. The customer-facing wedge is substitution; the platform is one graph, many apps.

Built for a GenAI hackathon (Retail and Consumer Goods track), July 2026. See [docs/PRD.md](docs/PRD.md) for the full vision.

## The problem

On quick-commerce platforms, 7 to 10 percent of order lines are out of stock by the time a picker reaches the shelf, usually met with a silent refund that loses the sale and the customer. More broadly, similarity models that power discovery, substitution and merchandising do not understand safety or compliance: they cluster products by what they are made of, with no idea who can safely use them.

## The idea: similarity is not substitutability

Embedding recommenders think almond milk and cashew milk are nearly identical. For a nut-allergic customer, one is a hospital visit. Safety is a question of relationships, not similarity, and it must be a hard gate, not a score:

1. **Layer 1, a knowledge graph proves safety.** Products, ingredients, allergens/conflict-classes and diet tags form a network of facts. One traversal checks whether any path connects a candidate to something this buyer must avoid. Unsafe candidates are removed deterministically, before any AI runs.
2. **Layer 2, Claude ranks and explains.** The model receives only the safe candidates and ranks them on functional fit, nutrition, real store stock, certifications and brand affinity, then writes the one-line reason. An unsafe suggestion is structurally impossible.
3. **Every decision teaches the system.** Accept or decline updates the learned swap confidence.

## One graph, two verticals

The same graph, ranking, compliance and recall code runs over **579 SKUs across two verticals** with zero structural changes, the proof that a new ecommerce category is a data change, not a code change:

- **Grocery** (508 SKUs, 24 categories): "conflict" is a food allergen (nuts, gluten, dairy, soy, egg, sesame).
- **Beauty and haircare** (71 SKUs, 5 categories): "conflict" is a dermatological irritant (fragrance, sulfates, silicones, retinoids, salicylates).

## Live demo

The customer surface is a full quick-commerce storefront (campaign banners, image-led categories, search, cart, safety audit, checkout). The default cart creates a realistic stockout at checkout so the standard similarity result can be compared live with SwapIQ's graph-safe replacement, and a toggle switches the engine between a RAG baseline and SwapIQ. A separate operator **console** (integration, metrics, recall, graph explorer) and a **ListingIQ** compliance surface expose the platform behind the store.

## Architecture

```
public/index.html         Storefront + pre-checkout substitution moment (vanilla JS, no build)
public/console.html       Operator console: integration, metrics, recall, graph explorer
public/qa.html            ListingIQ catalog compliance QA
api/index.py              FastAPI service (Vercel serverless compatible)
api/data_gen.py           Deterministic 579-SKU, two-vertical catalog; allergens,
                          diet tags, use-cases, nutrition, certs all DERIVED
api/graph_core.py         NetworkX graph builder + pure learning function
api/graph_backend.py      Neo4j runtime backend + NetworkX fallback, one contract
api/commerce_signals.py   Layer-2 ranking above the safety graph (fit, nutrition,
                          stock, certifications, brand, operator-only economics)
api/agent.py              Claude ranking/explanation + deterministic fallback
api/listings.py           Listing generator and deterministic compliance rules
```

Safety is a hard deterministic gate (Layer 1); ranking is rich but can never override it (Layer 2). The catalog graph is persistent when Neo4j is configured. Learned swap confidence and the decision log stay in the browser for this demo and are passed per request, so the API is stateless; production moves that learning state to a tenant/store-scoped store.

## Run locally

```
pip install -r requirements.txt uvicorn
uvicorn api.index:app --reload --port 8000
```

Open http://localhost:8000. Set `ANTHROPIC_API_KEY` to enable Claude ranking; without it a deterministic fallback keeps the demo fully functional.

Without graph configuration the app uses the NetworkX fallback. To require the
real Neo4j backend, start Neo4j, load the catalog and set:

```powershell
$env:SWAPIQ_GRAPH_BACKEND = "neo4j"
$env:NEO4J_URI = "bolt://localhost:7687"
$env:NEO4J_USER = "neo4j"
$env:NEO4J_PASSWORD = "swapiq-demo"
python neo4j_loader.py --demo
uvicorn api.index:app --reload --port 8000
```

`GET /api/health` reports the active backend and persistence state.
See `.env.example` for local and Neo4j Aura configuration.

## Tests

```powershell
python -m unittest discover -s tests -v
```

With `NEO4J_URI`, `NEO4J_USER` and `NEO4J_PASSWORD` configured, the same command
also runs Neo4j/NetworkX parity tests. Without Neo4j it runs the fallback
contract and skips only the integration cases.

## Deploy (Vercel)

`vercel.json` routes `/api/*` to the FastAPI serverless function and serves the `public/` pages at `/`, `/qa.html` and `/console.html`.

1. Import the repo at [vercel.com/new](https://vercel.com/new) (framework preset: Other).
2. Add environment variable `ANTHROPIC_API_KEY` to enable Claude (optional; a deterministic fallback works without it).
3. Leave `SWAPIQ_GRAPH_BACKEND` unset so the serverless API uses the in-memory NetworkX graph (no database needed). To run hosted on Neo4j instead, add the Neo4j Aura variables from `.env.example` and set `SWAPIQ_GRAPH_BACKEND=neo4j`.
4. Deploy. Every push to `main` redeploys automatically.

## Neo4j graph backend

Neo4j is implemented as a real runtime backend, not only a loader. Safety
filtering, edge weights, graph visualization, recall propagation and platform
metrics query Neo4j when configured. `SWAPIQ_GRAPH_BACKEND=neo4j` fails startup
if the database is unavailable, preventing a silent fallback in production.
`auto` uses Neo4j when `NEO4J_URI` is present, while `networkx` explicitly keeps
the zero-infrastructure demo path. See [NEO4J_SETUP.md](NEO4J_SETUP.md).

## Documentation

- [Product Requirements (PRD)](docs/PRD.md)
- [Low-Level Design (LLD)](docs/LLD.md)
- [Neo4j setup](NEO4J_SETUP.md)
