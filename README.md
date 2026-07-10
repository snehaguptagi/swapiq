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

The site is a single-screen live demo. Pick a shopper, mark an item out of stock, and watch the pipeline run: graph filter, Claude ranking, one-tap decision. Session impact (acceptance rate, revenue retained, projection at retail scale) accumulates ambiently in the header as you use it.

## Architecture

```
public/index.html      Frontend: vanilla HTML/CSS/JS, no build step
api/index.py           FastAPI service (Vercel serverless compatible)
api/data_gen.py        Synthetic catalog: ~200 SKUs; allergens and diet
                       tags derived from ingredient lists, never hand-set
api/graph_core.py      NetworkX knowledge graph, safety traversal,
                       pure learning function
api/agent.py           Claude ranking (structured JSON output) with a
                       deterministic fallback when no API key is set
```

The API is stateless: learned swap confidence and the decision log live in the browser (localStorage) and are passed per request, so the serverless deployment needs no database. In production the same schema moves to Neo4j and the learning state to the retailer's store.

## Run locally

```
pip install -r requirements.txt uvicorn
uvicorn api.index:app --reload --port 8000
```

Open http://localhost:8000. Set `ANTHROPIC_API_KEY` to enable Claude ranking; without it a deterministic fallback keeps the demo fully functional.

## Deploy

Deployed on Vercel. `vercel.json` routes `/api/*` to the FastAPI serverless function; `public/` is served statically. Add `ANTHROPIC_API_KEY` as a Vercel environment variable to enable Claude.

## Neo4j (production graph)

The demo runs on an in-memory NetworkX graph. The same schema loads unchanged
into Neo4j, the production graph database: see [NEO4J_SETUP.md](NEO4J_SETUP.md)
and `neo4j_loader.py`, which loads the catalog and runs the safety traversal as
Cypher.

## Documentation

- [Product Requirements (PRD)](docs/PRD.md)
- [Low-Level Design (LLD)](docs/LLD.md)
- [Neo4j setup](NEO4J_SETUP.md)
