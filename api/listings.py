"""ListingIQ: compliance and quality QA for product listings.

Same knowledge graph as SwapIQ, different job. For every product listing it
checks: are all allergens declared (FSSAI-mandated), are diet claims true
(vegan / gluten-free), are prohibited claims present, are mandatory fields
there. Detection is DETERMINISTIC (ingredient graph + rule library) so a
finding is provable; the LLM is only used to rewrite a compliant version.

Listings are synthetic and deliberately messy (planted issues), the way a real
catalog is, so the audit has real violations to catch. The detection is honest:
it reasons over the same ingredient -> allergen truth the store uses.
"""

# Claims that are restricted or prohibited for packaged food listings in India
# (FSSAI / consumer protection) and on major marketplaces.
PROHIBITED_CLAIMS = [
    "100% natural", "chemical free", "cures acidity", "clinically proven",
    "miracle food", "detox", "no side effects", "boosts immunity",
    "doctor recommended", "anti-ageing",
]

PACK = {"plant_milk": "1 L", "dairy_milk": "1 L", "yogurt": "400 g", "dairy_alternatives": "200 g",
        "cheese": "200 g", "bread": "400 g", "pasta": "500 g", "noodles": "280 g", "spreads": "340 g",
        "snacks": "52 g", "biscuits": "250 g", "chocolate": "80 g", "staples": "1 kg",
        "pulses_dal": "1 kg", "tea_coffee": "250 g", "breakfast": "475 g", "sauces": "500 g",
        "frozen": "500 g", "dry_fruits": "500 g", "fruits_veg": "1 kg", "eggs": "6 pcs",
        "beverages": "750 ml", "health": "500 g", "baby": "300 g",
        "skincare_cleanser": "150 ml", "skincare_moisturizer": "50 g",
        "skincare_serum": "30 ml", "skincare_suncare": "100 ml", "haircare": "200 ml"}


def _hash(s):
    h = 0
    for c in s:
        h = (h * 31 + ord(c)) % 100000
    return h


def generate_listing(p):
    """A realistic, deliberately imperfect marketplace listing for a product."""
    h = _hash(p["id"])
    pack = PACK.get(p["category"], "1 unit")

    declared = list(p["allergens"])
    # ~40% of listings drop an allergen from the declaration (the classic error)
    if declared and h % 5 < 2:
        declared.pop(h % len(declared))

    claims = []
    if h % 7 == 0:
        claims.append("vegan")
    if h % 7 == 1:
        claims.append("gluten free")
    if h % 7 == 2:
        claims.append("sugar free")
    if h % 3 == 0:
        claims.append(PROHIBITED_CLAIMS[h % len(PROHIBITED_CLAIMS)])
    claims.append("fresh")

    has_egg = "eggs" in p["ingredients"] or "egg_whites" in p["ingredients"]
    return {
        "title": f"{p['name']} {pack}",
        "description": f"Buy {p['name']} online. {', '.join(c.title() for c in claims)}. "
                       f"Delivered in minutes from QuickCart.",
        "declared_allergens": declared,
        "claims": claims,
        "net_quantity": None if h % 13 == 0 else pack,
        "fssai_license": None if h % 11 == 0 else f"100{h % 100000:05d}0012",
        "veg_mark": "veg" if (not has_egg or h % 4 != 0) else "veg",  # egg items wrongly marked veg when h%4==0
        "veg_mark_correct": "non-veg" if has_egg else "veg",
        "images": 1 if h % 9 == 0 else 2 + h % 3,
        "category": p["category"],
    }


SEV_PENALTY = {"critical": 34, "warning": 12, "info": 4}


def audit(p, listing, ingredient_allergens):
    """Return (findings, score). Findings are provable from ingredients + rules."""
    findings = []
    truth = set(p["allergens"])
    declared = set(listing["declared_allergens"])

    # R1 CRITICAL: undeclared allergen (FSSAI 2.2.2 mandatory allergen declaration)
    for a in sorted(truth - declared):
        src = next((i for i in p["ingredients"] if ingredient_allergens.get(i) == a), a)
        findings.append({
            "rule": "R1", "severity": "critical", "title": "Undeclared allergen",
            "detail": f"Contains {src.replace('_', ' ')} ({a.replace('_', ' ')}) but the allergen is not declared.",
            "fix": f"Add '{a.replace('_', ' ')}' to the allergen declaration.",
        })

    # R2 CRITICAL: false 'vegan' claim
    if "vegan" in listing["claims"] and "vegan" not in p["diet_tags"]:
        bad = [i for i in p["ingredients"] if i in {"milk_solids", "cream", "butter", "cheese",
               "yogurt_cultures", "eggs", "egg_whites", "honey", "paneer", "ghee", "khoa",
               "condensed_milk", "whey", "casein", "milk_powder"}]
        findings.append({"rule": "R2", "severity": "critical", "title": "False 'vegan' claim",
            "detail": f"Listing claims vegan but contains {', '.join(b.replace('_', ' ') for b in bad)}.",
            "fix": "Remove the vegan claim, or reformulate. A false claim is a legal and marketplace violation."})

    # R3 CRITICAL: false 'gluten free' claim
    if "gluten free" in listing["claims"] and "gluten_free" not in p["diet_tags"]:
        findings.append({"rule": "R3", "severity": "critical", "title": "False 'gluten free' claim",
            "detail": "Listing claims gluten free but contains a gluten source (wheat / semolina / maida / barley / rye).",
            "fix": "Remove the gluten-free claim."})

    # R4 CRITICAL/WARNING: mandatory fields
    if not listing["fssai_license"]:
        findings.append({"rule": "R4", "severity": "critical", "title": "Missing FSSAI license number",
            "detail": "Packaged food listings must display a valid FSSAI license number.",
            "fix": "Add the FSSAI license number to the listing."})
    if not listing["net_quantity"]:
        findings.append({"rule": "R4", "severity": "warning", "title": "Missing net quantity",
            "detail": "Net quantity (weight / volume) is a mandatory declaration.",
            "fix": "Add the net quantity."})

    # R5 WARNING: prohibited / restricted claims
    for c in listing["claims"]:
        if c in PROHIBITED_CLAIMS:
            findings.append({"rule": "R5", "severity": "warning", "title": "Prohibited marketing claim",
                "detail": f"'{c}' is a restricted claim for packaged food and is commonly rejected by marketplaces.",
                "fix": f"Remove '{c}' or support it with the required certification."})

    # R6 WARNING: sugar-free but contains sugar
    if "sugar free" in listing["claims"] and "sugar" in p["ingredients"]:
        findings.append({"rule": "R6", "severity": "warning", "title": "Misleading 'sugar free' claim",
            "detail": "Listing claims sugar free but sugar is an ingredient.",
            "fix": "Remove the sugar-free claim."})

    # R7 CRITICAL: veg/non-veg mark mismatch
    if listing["veg_mark"] != listing["veg_mark_correct"]:
        findings.append({"rule": "R7", "severity": "critical", "title": "Wrong veg / non-veg mark",
            "detail": f"Product should be marked '{listing['veg_mark_correct']}' but is marked '{listing['veg_mark']}'.",
            "fix": f"Correct the mark to '{listing['veg_mark_correct']}'."})

    # R8 INFO: too few images
    if listing["images"] < 2:
        findings.append({"rule": "R8", "severity": "info", "title": "Too few images",
            "detail": f"Only {listing['images']} image. Most marketplaces recommend at least 3.",
            "fix": "Add more product images."})

    score = max(0, 100 - sum(SEV_PENALTY[f["severity"]] for f in findings))
    order = {"critical": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda f: order[f["severity"]])
    return findings, score


def status_of(findings):
    if any(f["severity"] == "critical" for f in findings):
        return "critical"
    if any(f["severity"] == "warning" for f in findings):
        return "warning"
    return "pass"
