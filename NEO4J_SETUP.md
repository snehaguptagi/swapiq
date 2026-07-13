# Running SwapIQ on Neo4j

SwapIQ has a real Neo4j runtime backend. When it is selected, safety filtering,
swap weights, graph visualization, recall propagation and graph metrics query
Neo4j. NetworkX remains an explicit zero-infrastructure fallback.

Everything needed for local Neo4j testing is already on this machine.

## What is already installed (on your Desktop, in the Claude folder)

- `neo4j-community-5.26.0/` - Neo4j Community Edition 5.26 LTS
- `jdk21/` - a portable Java 21 runtime (Neo4j needs Java; nothing to install)
- `start-neo4j.bat` - one-click starter that wires the two together
- The initial password is already set to `swapiq-demo`

## Step 1: Start Neo4j

Double-click **`start-neo4j.bat`** on your Desktop (in the Claude folder), or in
PowerShell from that folder:

```powershell
$env:JAVA_HOME = "$PWD\jdk21\jdk-21.0.5+11"
.\neo4j-community-5.26.0\bin\neo4j.bat console
```

Leave the window open. When you see "Started", the database is up:
- Browser UI: http://localhost:7474  (login `neo4j` / `swapiq-demo`)
- Bolt endpoint: `bolt://localhost:7687`

## Step 2: Load the SwapIQ catalog

In a second terminal, from `swapiq-site`:

```powershell
pip install neo4j
python neo4j_loader.py --demo
```

Expected output:

```
Loaded: 508 products, 624 total nodes, 14010 relationships

Safe substitutes for a nut-allergic vegan shopper (almond milk out of stock):
  SAFE  ... Oat Milk ...
  SAFE  ... Soy Milk ...
What the graph blocks (nut-containing plant milks it will never offer):
  BLOCK ... Cashew Milk ...
  BLOCK ... Almond Milk ...
```

## Step 3: Run the API on Neo4j

In the same PowerShell session used to start the API:

```powershell
$env:SWAPIQ_GRAPH_BACKEND = "neo4j"
$env:NEO4J_URI = "bolt://localhost:7687"
$env:NEO4J_USER = "neo4j"
$env:NEO4J_PASSWORD = "swapiq-demo"
$env:NEO4J_DATABASE = "neo4j"
uvicorn api.index:app --reload --port 8000
```

Verify the runtime rather than relying on configuration alone:

```powershell
Invoke-RestMethod http://localhost:8000/api/health
```

The response must contain `"backend": "neo4j"`, `"persistent": true` and
`"connected": true`. Required Neo4j mode fails startup if the database is
unavailable or empty; it never silently drops to NetworkX.

## Step 4: See it in the Neo4j Browser

Open http://localhost:7474 and run the safety traversal in Cypher. This is the
exact logic from `graph_core.py`, now in the database:

```cypher
// Safe plant-milk swaps for a nut-allergic vegan when almond milk is out
MATCH (oos:Product {id: 'P001'})-[:IN_CATEGORY]->(cat)
MATCH (cand:Product)-[:IN_CATEGORY]->(cat)
WHERE cand.id <> oos.id
  AND (cand)-[:HAS_TAG]->(:DietTag {name: 'vegan'})
  AND NOT EXISTS {
        MATCH (cand)-[:CONTAINS]->(:Ingredient)-[:IS_A]->(a:Allergen)
        WHERE a.name IN ['tree_nuts', 'peanuts']
  }
RETURN cand.name, cand.price ORDER BY cand.price;
```

```cypher
// Visualise almond milk, its ingredients, and the allergen it carries
MATCH path = (p:Product {id:'P001'})-[:CONTAINS]->(:Ingredient)-[:IS_A]->(:Allergen)
RETURN path;
```

## Backend selection

- `SWAPIQ_GRAPH_BACKEND=neo4j`: require Neo4j and fail fast if unavailable.
- `SWAPIQ_GRAPH_BACKEND=auto`: use Neo4j when `NEO4J_URI` is configured; otherwise use NetworkX.
- `SWAPIQ_GRAPH_BACKEND=networkx`: force the offline fallback.
- `NEO4J_AUTO_SYNC=true`: idempotently upsert the deterministic demo graph at API startup. Prefer running `neo4j_loader.py` separately for hosted deployments.

For Neo4j Aura, replace the URI, username and password with the Aura credentials
and configure the same variables in the hosting provider. Do not commit database
credentials to Git.
