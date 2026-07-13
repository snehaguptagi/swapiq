# Running SwapIQ on Neo4j

The live demo runs on an in-memory NetworkX graph so it needs zero setup. This
guide loads the identical schema into **Neo4j**, the production graph database,
to show the scaling path is real. Everything below is already on your machine.

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
Loaded: 508 products, N ingredients, N allergens

Safe substitutes for a nut-allergic vegan shopper (almond milk out of stock):
  SAFE  ... Oat Milk ...
  SAFE  ... Soy Milk ...
What the graph blocks (nut-containing plant milks it will never offer):
  BLOCK ... Cashew Milk ...
  BLOCK ... Almond Milk ...
```

## Step 3: See it in the Neo4j Browser

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

## For the demo

You do not need Neo4j running for the web demo. Use it to answer the judges'
"is this production-ready?" question: show the same graph and the same safety
query running in a real graph database, then point at the identical logic in
`graph_core.py`. The web app stays on NetworkX so it never depends on a local
service during the pitch.
