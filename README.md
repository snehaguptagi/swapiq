# SwapIQ

**When an ordered grocery item goes out of stock, keep the sale.** SwapIQ offers the customer a substitute that is provably safe for their allergies, diet and budget, explained in one honest line, and it learns from every accept or decline.

Built for a GenAI hackathon (Retail and Consumer Goods track), July 2026.

## The problem

On quick-commerce platforms, 7 to 10 percent of order lines are out of stock by the time a picker reaches the shelf. Today the standard response is a silent refund: the retailer loses the sale after already paying for delivery, and the customer opens the competitor's app. Research shows only 25 percent of shoppers are ever offered a substitute, while about 90 percent have at least one item they will not compromise on.

## The idea: similarity is not substitutability

Embedding-based recommenders think almond milk and cashew milk are nearly identical. For a nut-allergic customer, one of them is a hospital visit. Substitutability is a question of relationships, not similarity:

1. **A knowledge graph proves safety.** Products, ingredients, allergens and diet tags form a network of facts. One traversal checks whether any path connects a candidate to something this shopper avoids. Unsafe candidates are deleted deterministically, in milliseconds, before any AI runs.
2. **Claude ranks and explains.** The model receives only the safe candidates, with prices and past acceptance data, picks the best fit and writes the one-line reason the customer sees. An unsafe suggestion is structurally impossible.
3. **Every decision teaches the system.** Accept or decline updates the learned swap confidence between the two products.

## Live demo

The customer surface is a full quick-commerce storefront: campaign banners, 24 image-led categories, search, 500+ products, cart, safety audit, checkout and order confirmation. The default demo cart creates a realistic stockout during checkout so the standard similarity result can be compared with SwapIQ's graph-safe replacement. A separate operator console and listing-compliance QA surface expose the platform behind the store.

## Architecture

```
public/index.html      Frontend: vanilla HTML/CSS/JS, no build step
public/console.html    Operator console, recall propagation and graph explorer
public/qa.html         ListingIQ catalog compliance QA
api/index.py           FastAPI service (Vercel serverless compatible)
api/data_gen.py        Synthetic catalog: 500+ SKUs; allergens and diet
                       tags derived from ingredient lists, never hand-set
api/graph_backend.py   Neo4j runtime backend + NetworkX fallback contract
api/graph_core.py      NetworkX fallback graph and pure learning function
api/agent.py           Claude ranking (structured JSON output) with a
                       deterministic fallback when no API key is set
api/listings.py        Listing generator and deterministic compliance rules
```

The catalog graph is persistent when Neo4j is configured. Learned swap confidence and the decision log remain in the browser for this demo and are passed per request; production moves that learning state to a tenant/store-scoped data store.

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

## Deploy

Deployed on Vercel. `vercel.json` routes `/api/*` to the FastAPI serverless function; `public/` is served statically. Add `ANTHROPIC_API_KEY` for Claude and the Neo4j variables above (normally using Neo4j Aura) to run the hosted API on Neo4j.

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
