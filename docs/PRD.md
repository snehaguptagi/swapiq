# SwapIQ: Product Requirements Document

Version 3.0 - July 2026
Ecommerce Infrastructure (Trust and Safety Layer)

## 1. Product vision

SwapIQ is the trust-and-safety graph layer for ecommerce catalogs, the layer any retailer selling physical products eventually needs, the same way payments needed Stripe and messaging needed Twilio.

Every retail category has its own version of the same problem: a product has attributes that can conflict with what a buyer needs, or with a rule a regulator or marketplace imposes, and today that check is either skipped or done by hand. Grocery calls the attribute an "allergen." Skincare calls it an "irritant." Electronics calls it a "compatibility spec." Toys and baby products call it an "age-safety certification." The graph shape underneath all of them is identical: a product is composed of verifiable attributes, a buyer or a regulation states a constraint, and a hard traversal proves whether the two conflict before any AI is allowed to rank or write.

SwapIQ builds that graph once per catalog and runs every downstream workflow off it: safe substitution when something goes out of stock, compliance auditing of every listing, safe discovery and search, recall propagation when an input turns out to be bad, and (planned) safe returns and exchanges. The defensible asset is the verified graph and the accumulated acceptance data it learns from, not the LLM, which is why the product is explicitly built to keep the safety decision deterministic and the graph backend swappable.

**The strategic bet this version proves**: expansion should go *across categories within ecommerce* (grocery to skincare to electronics), not *out of ecommerce into a new industry* (grocery to pharma). Same buyer (an ecommerce platform or brand), same integration shape, same lifecycle, a materially larger addressable catalog. Section 3 below shows why that path was validated, not just proposed, this version: the skincare vertical was added as pure data with zero changes to the graph, ranking or compliance code.

## 2. Problem statement

Commerce platforms increasingly use AI to make catalog, discovery and fulfillment decisions, but similarity models do not understand safety, compatibility or compliance. Almond milk and cashew milk sit close together in embedding space while one is dangerous to a nut-allergic shopper. A fragrance-laden night cream looks like a fine substitute for a fragrance-free one to a recommender that has never modeled skin sensitivity. A listing can sound persuasive while omitting a mandatory allergen declaration or a required certification mark. A recalled ingredient, material or component can appear across hundreds of SKUs that an operations team must find by hand.

These failures create refunds, churn, marketplace suppression, regulatory exposure and, in the worst case, physical harm. The category changes; the shape of the failure does not. The system needs a deterministic safety layer before generative AI is allowed to rank or write, and that layer needs to be cheap to extend to a new product category, or it never earns the word "platform."

## 3. Product surfaces and the commerce lifecycle

SwapIQ is organized around the stages every ecommerce catalog passes through, not around a single feature. Each row is a real surface in the product; the right column is the proof or the plan.

| Lifecycle stage | Surface | Job to be done | Status |
|---|---|---|---|
| 1. Onboard | SwapIQ Console connect flow | Ingest a catalog from a platform (Shopify/WooCommerce/CSV) and auto-build the graph, live, in front of the operator | Built: simulated connect flow with live node/edge counters |
| 2. Compliance | ListingIQ | Audit every listing against category-appropriate rules, cite the violation, generate a compliant rewrite | Built for food (allergen declaration, false diet claims, FSSAI fields); generalized automatically to skincare with zero new rule code |
| 3. Discovery | Safe Search | Filter the whole catalog to what is compatible with this specific buyer, not just what's in stock | Built: "safe for me" toggle, generalizes across verticals |
| 4. Cart and fulfillment | SwapIQ substitution | Resolve a stockout with a safe, ranked, explained replacement | Built: graph safety filter, functional fit, nutrition (food) or skip (non-food), real per-store stock, certifications, brand affinity, business signals (margin/clearance, operator-only) |
| 5. Post-purchase | Returns and exchange assistant | Suggest a safe, compatible alternative when a shopper returns an item, the same traversal as substitution, triggered by a return instead of a stockout | Planned this phase |
| 6. Safety operations | Recall propagation | Trace one bad input (ingredient, material, component, batch) to every affected SKU, listing and at-risk buyer in one traversal | Built, live in the console |
| 7. Insights | Console metrics | Report revenue recovered, listings protected, compliance issues caught, stock health, margin exposure, as evidence a buyer can show their own leadership | Built as a live snapshot; time-series trending is planned |

### Cross-category proof (shipped this version)

A second vertical, skincare and haircare (71 SKUs, 5 categories, 7 brands), was added as pure catalog data. "Allergen" became a dermatological conflict class (fragrance, sulfates, silicones, retinoids, salicylates); "vegan" now also excludes beeswax, lanolin and carmine through the same derivation rule that already excluded dairy and eggs; "cruelty-free" is a new brand-derived certification alongside organic and halal. `graph_core.py`, `graph_backend.py`, `agent.py`, `commerce_signals.py` and `listings.py` required zero structural changes. This is the load-bearing evidence for the vision statement in Section 1: a new ecommerce category is a data change, not a code change.

## 4. Target users and buyers

- Shoppers with allergies, sensitivities, dietary constraints, compatibility needs or strong preferences, across whatever category they are buying in.
- Ecommerce and quick-commerce operations teams responsible for fulfillment and catalog quality.
- Food, supplement, beauty, and other regulated or safety-sensitive category brands selling across several marketplaces.
- Retail platform engineering teams that want an API and a graph, not a new commerce stack to run.
- Compliance and product-safety teams that need cited, repeatable, category-agnostic checks.

The initial buyer is a mid-market retailer or D2C brand, in food or beauty, that cannot justify building a product-safety graph internally. The expansion buyer, once the platform proves a second and third vertical, is a multi-category marketplace that wants one compliance and substitution layer across all of its sellers' catalogs instead of one per category. The value metric is revenue recovered, listings protected, manual review time avoided and time to onboard a new product category.

## 5. Current scope

### Implemented

- Full responsive quick-commerce storefront: hero campaigns, 29 categories across two verticals, search, product rails, profile selection, cart, checkout and order confirmation.
- Deterministic synthetic catalog, 579 SKUs, 19 brands, two verticals (grocery and beauty/haircare), with ingredient-derived allergens, diet tags and dermatological conflict classes.
- Five shopper profiles: nut, gluten, egg, sesame and fragrance/sulfate constraints, plus budget sensitivity.
- Similarity-only RAG baseline for an explicit A/B comparison, verified to fail identically (and instructively) on both verticals.
- Knowledge-graph safety traversal before any ranking, in both NetworkX and Neo4j backends.
- A commerce-signals ranking layer above the safety graph: functional fit, nutrition (food only), real per-store stock (with a distinct "safe but unavailable" state), certifications, brand affinity, and operator-only business signals (margin, clearance).
- Claude ranking and explanation with a deterministic fallback; margin and clearance are explicitly withheld from the shopper-facing prompt and reason text.
- Accept/refund learning loop stored per browser session.
- Safe-for-me catalog filtering and cart-level safety audit.
- ListingIQ audit library for allergens, claims, required fields, dietary marks and listing completeness, running automatically across both verticals.
- AI-assisted compliant listing rewrite.
- Operator console: platform metrics, graph explorer, simulated store connection with a live-building graph, recall propagation, and a business/operations metrics panel.
- Neo4j runtime backend for safety filtering, graph views, recall propagation, edge weights and metrics.
- Explicit NetworkX fallback with automated parity tests against Neo4j.
- Health endpoint that reports the active backend and persistence state.

### Not yet productionized

- Live retailer catalog, inventory, payment or marketplace integrations.
- Authentication, tenant isolation, persistent server-side learning and role-based access control.
- Continuous marketplace policy synchronization.
- Hosted Neo4j Aura credentials and production tenant data. The backend is implemented and locally validated; deployment still requires a managed database.
- Human approval workflow, audit-log retention and regulatory certification.
- Post-purchase returns/exchange assistant (Section 3, row 5).
- A third vertical proving compatibility-shaped, not allergen-shaped, conflicts (Section 11).
- Time-series trending for console insights (currently a live snapshot only).
- A formally category-agnostic schema (today's generalization works because the field names, `ingredients`/`allergens`/`diet_tags`, happen to be reusable; a config-driven attribute schema is the more honest long-term version, see Section 11).

## 6. Core user journeys

### Safe stockout resolution

1. A shopper checks out with a constrained profile, in any vertical.
2. The picker (or platform event) reports an ordered SKU as out of stock.
3. The graph scans same-category candidates and removes conflicting candidates, whether that conflict is an allergen, an irritant, or (planned) a compatibility mismatch.
4. Claude receives only safe candidates, ranks them on fit, nutrition where relevant, stock and certifications, and writes a one-line reason. Margin and clearance stay operator-only.
5. The shopper accepts the replacement or requests a refund.
6. The decision updates the learned swap confidence.

### Listing compliance QA

1. A catalog team opens the listing test suite, spanning every vertical in the catalog.
2. ListingIQ scores each listing and groups critical, warning and clean results.
3. A reviewer opens a finding and sees severity, rule, evidence and prescribed fix.
4. The system generates a corrected listing for human approval.

### Recall propagation

1. A supplier or safety team flags a bad input.
2. The console traverses linked products, categories, listings and conflict-class relationships.
3. The operator receives the affected SKU count, product list and at-risk shopper profiles.

### Cross-category onboarding (the vision proof)

1. A new product category's catalog (ingredient/material list, category taxonomy, brand list) is added as data.
2. The existing conflict-class map is extended with the category's own conflict vocabulary (a two-line addition, not new logic).
3. The graph, ranking, compliance and recall surfaces work on the new category with no code change, verified live for skincare/haircare this version.

## 7. Functional requirements

### Storefront

- Render every category across every onboarded vertical, and at least 500 products, without a build step.
- Support responsive desktop and mobile layouts without horizontal page overflow.
- Support search, category navigation, quantity controls, cart totals and checkout.
- Preserve the RAG-to-SwapIQ comparison as an unobtrusive demo control, working identically regardless of vertical.

### Safety engine

- Never send a graph-blocked candidate to the LLM.
- Return a cited reason for every blocked candidate.
- Return a deterministic answer when Claude is unavailable or invalid.
- Keep learned weights bounded between 0 and 1.
- Treat "safe but unavailable at this store" as distinct from "unsafe"; never conflate the two in the UI or the API contract.

### Commerce-signals ranking layer

- Never let functional fit, nutrition, certifications, stock or brand affinity override the safety graph's hard filter; these signals only reorder what already passed.
- Never surface margin or clearance status to the shopper-facing reason or the LLM prompt; these are operator-only.
- Degrade gracefully when a signal doesn't apply to a category (for example, no fabricated nutrition on a moisturizer).

### ListingIQ

- Audit every catalog listing, across every vertical, against deterministic rules.
- Expose score, severity, rule ID, evidence and fix.
- Use the LLM only for rewriting, not for deciding whether a deterministic rule passed.

### Console and recall

- Report catalog, graph and listing-QA metrics from live API data, including per-vertical and cross-vertical totals.
- Visualize a product-centered graph.
- Return recall impact from a focused ingredient or material query.

## 8. Success metrics

| Area | Metric |
|---|---|
| Safety | Zero constraint-violating candidates after graph filtering, in every onboarded vertical |
| Substitution | Acceptance rate and revenue retained per 100 stockouts |
| Performance | Graph filtering measured in milliseconds; complete offer remains usable with fallback |
| Compliance | Critical issues detected, false-positive rate and review time saved per listing |
| Recall | Time to identify all linked SKUs compared with a manual catalog sweep |
| Product | Search-to-cart, cart-to-checkout and successful end-to-end demo completion |
| Platform (new) | Time and code changed to onboard a new product category; target is data-only, as demonstrated for skincare |

## 9. Business model and go-to-market

The initial product is a B2B API and operations console priced by catalog size, audited listing volume and substitution events. The first design partner should be a food or beauty brand selling across at least three channels, where listing compliance and ingredient quality already have an owner and budget.

The expansion path is explicitly horizontal within ecommerce first: one graph, one integration, growing across product categories (grocery, beauty, and next a compatibility-shaped category) before it is ever pitched as multi-industry. The defensible asset is the verified catalog graph plus accumulated acceptance and rule-performance data, not model access, and that asset compounds fastest by adding categories to an existing retailer relationship rather than by chasing new industries.

## 10. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Missing or wrong ingredient/material data | Fail closed for constrained shoppers and flag incomplete catalog records |
| LLM latency, outage or invalid output | Deterministic fallback with the same response contract |
| False confidence from synthetic data | Present data as synthetic and validate with a design partner's real catalog before commercial claims |
| Marketplace policies change | Versioned policy packs with rule source and effective date |
| Feature copied by a large retailer | Sell multi-tenant, multi-category infrastructure to the long tail and compound the cross-workflow graph asset |
| Neo4j silently falls back in production | `SWAPIQ_GRAPH_BACKEND=neo4j` fails startup unless Neo4j is reachable; `/api/health` exposes the active backend |
| Cross-category generalization is coincidental, not structural | Section 11's schema-generalization work turns "the field names happen to reuse" into an explicit, config-driven attribute model |

## 11. Roadmap: this phase

1. **Post-purchase returns and exchange assistant.** Reuse the substitution traversal, triggered by a return event instead of a stockout, to suggest a safe, compatible alternative rather than a bare refund. Closes the lifecycle loop in Section 3.
2. **A third vertical proving compatibility, not allergen, conflicts.** Electronics or mobile accessories: a phone case or charger's "conflict" is a device/voltage/region mismatch, not an ingredient. This is the harder, more convincing proof, since it cannot reuse the ingredient-shaped mental model at all, it has to prove the underlying graph primitive (attribute, constraint, traversal) is genuinely general.
3. **Schema generalization.** Promote the currently-implicit reuse (ingredients/allergens/diet_tags happening to work for skincare) into an explicit, config-driven attribute and conflict-class schema, so onboarding vertical four does not depend on another coincidence.
4. **Console insights trending.** Move from a live snapshot to time-series metrics (acceptance rate over time, compliance issues resolved per week), the artifact an operator actually reports upward.

## 12. Release acceptance criteria

### Shipped this version

- 579 products across 29 categories and two verticals load from `/api/bootstrap`.
- Storefront search, category browsing, cart and checkout work on desktop and mobile, for both verticals.
- The seeded hero journey shows the unsafe RAG cashew-milk recommendation, then a safe SwapIQ oat-milk replacement.
- A second seeded journey (Meera, fragrance/sulfate allergy) shows the identical safety and ranking pipeline resolving a skincare stockout with zero code differences from the grocery path.
- Accepting a substitute updates the cart and allows order completion.
- ListingIQ audits all 579 listings, across both verticals, and exposes detailed findings.
- Console metrics, recall endpoint and graph explorer render without browser errors and reflect both verticals.
- Neo4j and NetworkX return identical safe/blocked sets and graph counts in the backend contract tests.
- `/api/health` reports `neo4j`, `persistent: true` when the production backend is selected.
- README, PRD, LLD and Neo4j setup accurately match the shipped implementation.

### Planned for next version

- A post-purchase returns/exchange flow with its own seeded journey.
- A third, compatibility-shaped vertical with a seeded journey that does not rely on the ingredient/allergen mental model.
- Console insights shown as a trend, not only a current snapshot.
