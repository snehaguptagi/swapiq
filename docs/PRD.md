# SwapIQ: Product Requirements Document

GenAI Hackathon, Retail and Consumer Goods track. July 2026.

## 1. Problem statement

A knowledge graph powered substitution intelligence agent for grocery ecommerce that models products, ingredients, allergens, dietary rules and shopper preferences as a graph, guarantees constraint-safe substitutes for out-of-stock items through graph traversal, uses GenAI to rank and explain each swap with cited graph paths, and learns from every accept or reject decision.

## 2. The problem, from first principles

**Fact 1. Stockouts after ordering are structural in quick commerce.** Ten-minute delivery requires small dark stores whose inventory changes faster than any stock counter can track. Replenishment cycles run 24 to 48 hours and availability in fresh categories sits below 75 percent across major Indian platforms. 7 to 10 percent of order lines are out of stock at pick time. This cannot be prevented; only the response to it can improve.

**Fact 2. The current response destroys value on both sides.** Three out of four times the customer gets a silent refund. The retailer loses revenue it already paid delivery costs for. About 90 percent of shoppers have at least one item they will not compromise on, and failing it sends them to a competitor app that is 30 seconds away.

**Fact 3. Similarity is not substitutability.** Current systems pick substitutes by text or embedding similarity. Almond milk and cashew milk are nearly identical in embedding space; for a nut-allergic customer one of them is dangerous. Whether a product can replace another depends on relationships (ingredients, allergens, diets, price, usage), which similarity scores discard.

**Therefore:** model the relationships explicitly in a knowledge graph. Hard constraints are enforced by graph traversal before any AI runs, so an unsafe suggestion is structurally impossible. The LLM adds judgment (which safe option fits best) and language (the one-line reason that makes a customer tap yes). Every decision feeds back into the graph.

## 3. Users

| User | Need | Surface |
|---|---|---|
| Shopper | A safe, sensible replacement with an honest reason, decided in one tap | Swap offer in the order flow |
| Category manager | Acceptance rate, revenue retained vs refunded, failing SKUs | Session stats and decision log |
| Platform engineering | A drop-in service that consumes events they already produce | One API call: POST /api/swap-offer |

## 4. Scope

**In scope (hackathon):** synthetic catalog of about 200 SKUs with ingredient-derived allergens and diet tags; three demo shopper personas; knowledge graph safety filtering; Claude ranking with structured output and a deterministic fallback; learning loop; live web demo with ambient business impact; comparison against a similarity-only baseline.

**Out of scope:** real inventory or payment integration, mobile app, production Neo4j deployment, authentication.

## 5. Success metrics

1. **Demo:** a stockout resolves into an accepted safe substitution end to end in under 5 seconds, with a cited explanation.
2. **Safety:** zero constraint-violating suggestions, provable by construction: unsafe products never reach the LLM.
3. **Business:** the demo computes revenue retained vs refunded live, and projects it at retailer scale with an open formula.

## 6. Business case

At a 10 percent stockout rate, every percentage point of substitution acceptance is refund revenue recovered plus a churn event avoided. Example at defaults (1,500 orders per day per store, 8 percent stockout, Rs. 150 average item, 70 percent acceptance): about Rs. 12,600 recovered per store per day, roughly Rs. 46 lakh per store per year, over Rs. 900 crore per year across a 2,000 store network. Published research: substitution acceptance improves from 66 percent (random) to 75 percent or more with personalised, constraint-aware suggestions.

## 7. Key risks and mitigations

| Risk | Mitigation |
|---|---|
| Missing or wrong ingredient data | Fail safe: a product with unknown ingredients is never offered to a constrained shopper; flagged to catalog ops |
| LLM latency or outage during demo | Deterministic fallback ranker produces the same response shape |
| Cold start (no acceptance history) | SWAP confidence seeded from attribute similarity priors; learning takes over immediately |
| Judges question data realism | Allergens and diet tags are derived from ingredient lists, never hand-assigned; FSSAI labels carry this data in production |
