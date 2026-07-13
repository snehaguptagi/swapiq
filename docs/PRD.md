# SwapIQ: Product Requirements Document

Version 2.1 - July 2026
Retail and Consumer Goods / Commerce Infrastructure

## 1. Product vision

SwapIQ is the product-safety knowledge graph for commerce. It converts catalog data into verified relationships between products, ingredients, allergens, dietary rules and shopper constraints, then powers multiple operational workflows from that shared graph.

The customer-facing wedge is safe out-of-stock substitution. The broader platform automates product-safety work that ecommerce brands and retailers otherwise perform manually: catalog QA, listing compliance, recall propagation and shopper-safe discovery.

## 2. Problem statement

Commerce platforms increasingly use AI to make catalog and fulfillment decisions, but similarity models do not understand safety or compliance. Almond milk and cashew milk may be close in embedding space while both are unsafe for a shopper with a tree-nut allergy. A listing can sound persuasive while omitting a mandatory allergen declaration. A recalled ingredient can appear across hundreds of SKUs that an operations team must find manually.

These failures create refunds, churn, marketplace suppression, regulatory exposure and customer harm. The system needs a deterministic safety layer before generative AI is allowed to rank or write.

## 3. Product surfaces

| Surface | Primary user | Job to be done |
|---|---|---|
| QuickCart storefront | Shopper | Search, browse, build a cart and check out from a complete quick-commerce experience |
| SwapIQ substitution | Shopper / fulfillment team | Resolve a post-order stockout with a safe, sensible replacement and a clear explanation |
| SwapIQ Console | Ecommerce operations | Connect a catalog, inspect graph coverage, monitor applications and trigger recall analysis |
| ListingIQ | Catalog and compliance teams | Audit listings, cite violations and generate a compliant correction |
| Safe Search | Shopper / retailer | Filter the catalog to products verified against the current shopper profile |
| Recall propagation | Safety and operations teams | Trace one affected ingredient to every linked SKU, listing, category and at-risk shopper |

## 4. Target users and buyers

- Shoppers with allergies, dietary constraints or strong product preferences.
- Ecommerce and quick-commerce operations teams responsible for fulfillment and catalog quality.
- Food, supplement and regulated-category brands selling across several marketplaces.
- Retail platform engineering teams that want an API rather than a new commerce stack.
- Compliance and product-safety teams that need cited, repeatable checks.

The initial buyer is a mid-market retailer or D2C brand that cannot justify building a product-safety graph internally. The value metric is revenue recovered, listings protected and manual review time avoided.

## 5. Current scope

### Implemented

- Full responsive quick-commerce storefront with hero campaigns, 24 categories, search, product rails, profile selection, cart, checkout and order confirmation.
- Deterministic synthetic catalog with 508 SKUs, 12 brands and ingredient-derived allergens and diet tags.
- Four shopper profiles covering nut, gluten, egg and sesame constraints plus budget sensitivity.
- Similarity-only RAG baseline for an explicit A/B comparison.
- Knowledge-graph safety traversal before ranking.
- Claude ranking and explanation with a deterministic fallback.
- Accept/refund learning loop stored per browser session.
- Safe-for-me catalog filtering and cart-level safety audit.
- ListingIQ audit library for allergens, claims, required fields, dietary marks and listing completeness.
- AI-assisted compliant listing rewrite.
- Operator console with platform metrics, graph explorer, simulated store connection and recall propagation.
- Neo4j runtime backend for safety filtering, graph views, recall propagation, edge weights and metrics.
- Explicit NetworkX fallback with automated parity tests against Neo4j.
- Health endpoint that reports the active backend and persistence state.

### Not yet productionized

- Live retailer catalog, inventory, payment or marketplace integrations.
- Authentication, tenant isolation, persistent server-side learning and role-based access control.
- Continuous marketplace policy synchronization.
- Hosted Neo4j Aura credentials and production tenant data. The backend is implemented and locally validated; deployment still requires a managed database.
- Human approval workflow, audit-log retention and regulatory certification.

## 6. Core user journeys

### Safe stockout resolution

1. A shopper checks out with a constrained profile.
2. The picker reports an ordered SKU as out of stock.
3. The graph scans same-category candidates and removes allergen, diet and budget conflicts.
4. Claude receives only safe candidates, ranks them and writes a one-line reason.
5. The shopper accepts the replacement or requests a refund.
6. The decision updates the learned swap confidence.

### Listing compliance QA

1. A catalog team opens the 508-listing test suite.
2. ListingIQ scores each listing and groups critical, warning and clean results.
3. A reviewer opens a finding and sees severity, rule, evidence and prescribed fix.
4. The system generates a corrected listing for human approval.

### Recall propagation

1. A supplier or safety team flags an ingredient.
2. The console traverses linked products, categories, listings and allergen relationships.
3. The operator receives the affected SKU count, product list and at-risk shopper profiles.

## 7. Functional requirements

### Storefront

- Render all 24 categories and at least 500 products without a build step.
- Support responsive desktop and mobile layouts without horizontal page overflow.
- Support search, category navigation, quantity controls, cart totals and checkout.
- Preserve the RAG-to-SwapIQ comparison as an unobtrusive demo control.

### Safety engine

- Never send a graph-blocked candidate to the LLM.
- Return a cited reason for every blocked candidate.
- Return a deterministic answer when Claude is unavailable or invalid.
- Keep learned weights bounded between 0 and 1.

### ListingIQ

- Audit every catalog listing against deterministic rules.
- Expose score, severity, rule ID, evidence and fix.
- Use the LLM only for rewriting, not for deciding whether a deterministic rule passed.

### Console and recall

- Report catalog, graph and listing-QA metrics from live API data.
- Visualize a product-centered graph.
- Return recall impact from a focused ingredient query.

## 8. Success metrics

| Area | Metric |
|---|---|
| Safety | Zero constraint-violating candidates after graph filtering |
| Substitution | Acceptance rate and revenue retained per 100 stockouts |
| Performance | Graph filtering measured in milliseconds; complete offer remains usable with fallback |
| Compliance | Critical issues detected, false-positive rate and review time saved per listing |
| Recall | Time to identify all linked SKUs compared with a manual catalog sweep |
| Product | Search-to-cart, cart-to-checkout and successful end-to-end demo completion |

## 9. Business model and go-to-market

The initial product is a B2B API and operations console priced by catalog size, audited listing volume and substitution events. The first design partner should be a food or supplement brand selling across at least three channels, where listing compliance and ingredient quality already have an owner and budget.

The expansion path is one graph powering several applications: substitution, safe search, compliance, recall and eventually regulated-category workflows. The defensible asset is the verified catalog graph plus accumulated acceptance and rule-performance data, not model access.

## 10. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Missing or wrong ingredient data | Fail closed for constrained shoppers and flag incomplete catalog records |
| LLM latency, outage or invalid output | Deterministic fallback with the same response contract |
| False confidence from synthetic data | Present data as synthetic and validate with a design partner's real catalog before commercial claims |
| Marketplace policies change | Versioned policy packs with rule source and effective date |
| Feature copied by a large retailer | Sell multi-tenant infrastructure to the long tail and compound the cross-workflow graph asset |
| Neo4j silently falls back in production | `SWAPIQ_GRAPH_BACKEND=neo4j` fails startup unless Neo4j is reachable; `/api/health` exposes the active backend |

## 11. Release acceptance criteria

- 508 products and 24 categories load from `/api/bootstrap`.
- Storefront search, category browsing, cart and checkout work on desktop and mobile.
- The seeded hero journey shows the unsafe RAG cashew-milk recommendation, then a safe SwapIQ oat-milk replacement.
- Accepting the substitute updates the cart and allows order completion.
- ListingIQ audits all 508 listings and exposes detailed findings.
- Console metrics, recall endpoint and graph explorer render without browser errors.
- Neo4j and NetworkX return identical safe/blocked sets and graph counts in the backend contract tests.
- `/api/health` reports `neo4j`, `persistent: true` when the production backend is selected.
- README, PRD, LLD and Neo4j setup accurately match the shipped implementation.
