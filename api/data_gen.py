"""SwapIQ data layer: a platform-scale synthetic grocery catalog.

Every product carries an ingredient list. Allergens and diet tags are DERIVED
from ingredients, never hand-assigned, so the knowledge graph reasoning is
honest: if the ingredient data is wrong, the graph is wrong, exactly as in
production where this comes from FSSAI-mandated labels.
"""

import random

# Ingredient -> allergen group. The ground truth the graph reasons over.
INGREDIENT_ALLERGENS = {
    # tree nuts
    "almonds": "tree_nuts", "cashews": "tree_nuts", "hazelnuts": "tree_nuts",
    "walnuts": "tree_nuts", "pistachios": "tree_nuts", "pine_nuts": "tree_nuts",
    # peanuts
    "peanuts": "peanuts",
    # dairy
    "milk_solids": "dairy", "cream": "dairy", "butter": "dairy", "cheese": "dairy",
    "yogurt_cultures": "dairy", "ghee": "dairy", "khoa": "dairy", "condensed_milk": "dairy",
    "whey": "dairy", "casein": "dairy", "milk_powder": "dairy", "paneer": "dairy",
    # gluten
    "wheat_flour": "gluten", "barley_malt": "gluten", "semolina": "gluten",
    "maida": "gluten", "rye": "gluten",
    # soy
    "soybeans": "soy", "soy_lecithin": "soy", "soy_sauce_base": "soy",
    # eggs
    "eggs": "eggs", "egg_whites": "eggs",
    # sesame
    "sesame": "sesame", "sesame_seeds": "sesame",
    # mustard
    "mustard": "mustard",
}

# Animal-derived: makes a product non-vegan.
NON_VEGAN = {"milk_solids", "cream", "butter", "cheese", "yogurt_cultures", "eggs",
             "egg_whites", "honey", "paneer", "ghee", "khoa", "condensed_milk",
             "whey", "casein", "milk_powder"}
NON_VEGETARIAN = set()  # catalog is vegetarian + eggs; kept for extensibility

GLUTEN_INGREDIENTS = {"wheat_flour", "barley_malt", "semolina", "maida", "rye"}

# (name, category, base_ingredients, base_price)
PRODUCT_TEMPLATES = [
    # ---- Plant milk (the hero category) ----
    ("Almond Milk Unsweetened", "plant_milk", ["water", "almonds", "sea_salt"], 289),
    ("Oat Milk Barista", "plant_milk", ["water", "oats", "sea_salt"], 259),
    ("Oat Milk Original", "plant_milk", ["water", "oats"], 239),
    ("Soy Milk Natural", "plant_milk", ["water", "soybeans"], 199),
    ("Cashew Milk Creamy", "plant_milk", ["water", "cashews", "sea_salt"], 310),
    ("Coconut Milk Beverage", "plant_milk", ["water", "coconut"], 220),
    ("Rice Milk Light", "plant_milk", ["water", "rice"], 210),
    # ---- Dairy milk ----
    ("Toned Milk", "dairy_milk", ["milk_solids", "water"], 60),
    ("Full Cream Milk", "dairy_milk", ["milk_solids", "cream"], 72),
    ("Slim Milk", "dairy_milk", ["milk_solids", "water"], 62),
    ("Buffalo Milk", "dairy_milk", ["milk_solids", "cream"], 80),
    ("Lactose Free Milk", "dairy_milk", ["milk_solids", "water"], 90),
    # ---- Yogurt ----
    ("Greek Yogurt Plain", "yogurt", ["milk_solids", "yogurt_cultures"], 120),
    ("Coconut Yogurt Vegan", "yogurt", ["coconut", "yogurt_cultures_vegan"], 180),
    ("Fruit Yogurt Mango", "yogurt", ["milk_solids", "yogurt_cultures", "mango", "sugar"], 45),
    ("Curd Fresh", "yogurt", ["milk_solids", "yogurt_cultures"], 40),
    ("Probiotic Lassi", "yogurt", ["milk_solids", "yogurt_cultures", "sugar"], 35),
    # ---- Paneer, tofu ----
    ("Paneer Fresh Block", "dairy_alternatives", ["paneer"], 95),
    ("Tofu Firm", "dairy_alternatives", ["soybeans", "water"], 85),
    ("Malai Paneer", "dairy_alternatives", ["paneer", "cream"], 110),
    # ---- Cheese ----
    ("Cheddar Cheese Slices", "cheese", ["milk_solids", "cheese"], 140),
    ("Mozzarella Block", "cheese", ["milk_solids", "cheese"], 260),
    ("Processed Cheese Cubes", "cheese", ["milk_solids", "cheese"], 120),
    ("Vegan Cheese Slices", "cheese", ["coconut_oil", "starch"], 240),
    # ---- Bread ----
    ("Whole Wheat Bread", "bread", ["wheat_flour", "yeast", "sugar"], 45),
    ("Multigrain Bread", "bread", ["wheat_flour", "oats", "seeds", "yeast"], 55),
    ("Gluten Free Bread", "bread", ["rice", "tapioca_starch", "yeast"], 150),
    ("Sourdough Loaf", "bread", ["wheat_flour", "yeast"], 120),
    ("Milk Bread", "bread", ["wheat_flour", "milk_solids", "butter", "yeast"], 50),
    ("Pav Buns", "bread", ["maida", "yeast", "sugar"], 35),
    # ---- Pasta ----
    ("Durum Penne Pasta", "pasta", ["semolina"], 110),
    ("Gluten Free Penne", "pasta", ["rice", "corn"], 190),
    ("Whole Wheat Spaghetti", "pasta", ["wheat_flour"], 125),
    ("Macaroni Elbow", "pasta", ["semolina"], 85),
    # ---- Noodles ----
    ("Instant Noodles Masala", "noodles", ["maida", "palm_oil", "spices"], 14),
    ("Hakka Noodles", "noodles", ["maida"], 55),
    ("Rice Noodles", "noodles", ["rice"], 95),
    ("Egg Noodles", "noodles", ["maida", "egg_whites"], 65),
    # ---- Spreads ----
    ("Peanut Butter Crunchy", "spreads", ["peanuts", "sugar", "salt"], 250),
    ("Almond Butter Natural", "spreads", ["almonds"], 480),
    ("Hazelnut Cocoa Spread", "spreads", ["hazelnuts", "cocoa", "sugar", "milk_solids"], 350),
    ("Sesame Tahini", "spreads", ["sesame_seeds"], 320),
    ("Mixed Fruit Jam", "spreads", ["fruit", "sugar", "pectin"], 140),
    ("Sunflower Seed Butter", "spreads", ["sunflower_seeds"], 360),
    # ---- Snacks ----
    ("Salted Potato Chips", "snacks", ["potato", "vegetable_oil", "salt"], 30),
    ("Nachos Cheese", "snacks", ["corn", "vegetable_oil", "cheese"], 50),
    ("Roasted Makhana", "snacks", ["foxnuts", "vegetable_oil", "salt"], 99),
    ("Trail Mix Nutty", "snacks", ["almonds", "cashews", "raisins"], 220),
    ("Banana Chips", "snacks", ["banana", "coconut_oil", "salt"], 60),
    ("Sesame Bar", "snacks", ["sesame_seeds", "jaggery"], 40),
    ("Bhujia Sev", "snacks", ["besan", "vegetable_oil", "spices"], 55),
    ("Popcorn Butter", "snacks", ["corn", "butter", "salt"], 45),
    # ---- Biscuits ----
    ("Marie Light Biscuits", "biscuits", ["wheat_flour", "sugar", "vegetable_oil"], 30),
    ("Chocolate Chip Cookies", "biscuits", ["wheat_flour", "butter", "sugar", "cocoa"], 90),
    ("Oat Digestive Biscuits", "biscuits", ["oats", "wheat_flour", "sugar"], 55),
    ("Gluten Free Cookies", "biscuits", ["rice", "butter", "sugar"], 160),
    ("Cream Sandwich Biscuits", "biscuits", ["maida", "sugar", "palm_oil"], 25),
    # ---- Chocolate ----
    ("Milk Chocolate Bar", "chocolate", ["cocoa", "milk_solids", "sugar"], 80),
    ("Dark Chocolate 70%", "chocolate", ["cocoa", "sugar"], 150),
    ("Hazelnut Chocolate", "chocolate", ["cocoa", "hazelnuts", "milk_solids", "sugar"], 120),
    ("Vegan Dark Chocolate", "chocolate", ["cocoa", "coconut_sugar"], 210),
    ("Almond Chocolate Bar", "chocolate", ["cocoa", "almonds", "milk_solids", "sugar"], 130),
    # ---- Staples ----
    ("Whole Wheat Atta 5kg", "staples", ["wheat_flour"], 260),
    ("Basmati Rice 1kg", "staples", ["rice"], 180),
    ("Sunflower Oil 1L", "staples", ["sunflower_oil"], 145),
    ("Cold Pressed Coconut Oil", "staples", ["coconut_oil"], 320),
    ("Mustard Oil 1L", "staples", ["mustard"], 175),
    ("Iodised Salt 1kg", "staples", ["salt"], 28),
    ("Sugar 1kg", "staples", ["sugar"], 55),
    # ---- Pulses & dal ----
    ("Toor Dal 1kg", "pulses_dal", ["pigeon_peas"], 160),
    ("Moong Dal 1kg", "pulses_dal", ["mung_beans"], 150),
    ("Chana Dal 1kg", "pulses_dal", ["chickpeas"], 120),
    ("Rajma 1kg", "pulses_dal", ["kidney_beans"], 170),
    ("Kabuli Chana 1kg", "pulses_dal", ["chickpeas"], 140),
    ("Soya Chunks", "pulses_dal", ["soybeans"], 90),
    # ---- Tea & coffee ----
    ("Green Tea 25 Bags", "tea_coffee", ["green_tea"], 175),
    ("Black Tea Leaf 500g", "tea_coffee", ["black_tea"], 220),
    ("Instant Coffee 100g", "tea_coffee", ["coffee"], 290),
    ("Filter Coffee 500g", "tea_coffee", ["coffee", "chicory"], 260),
    ("Masala Chai Premix", "tea_coffee", ["black_tea", "milk_powder", "sugar", "spices"], 150),
    # ---- Breakfast ----
    ("Corn Flakes 475g", "breakfast", ["corn", "sugar", "barley_malt"], 195),
    ("Fruit & Nut Muesli", "breakfast", ["oats", "almonds", "raisins", "wheat_flour"], 320),
    ("Rolled Oats 1kg", "breakfast", ["oats"], 180),
    ("Chocolate Cereal", "breakfast", ["wheat_flour", "cocoa", "sugar"], 210),
    ("Poha Flattened Rice", "breakfast", ["rice"], 65),
    # ---- Sauces & condiments ----
    ("Tomato Ketchup 1kg", "sauces", ["tomato", "sugar", "vinegar"], 120),
    ("Veg Mayonnaise", "sauces", ["vegetable_oil", "vinegar", "mustard"], 99),
    ("Egg Mayonnaise", "sauces", ["egg_whites", "vegetable_oil", "vinegar"], 110),
    ("Soy Sauce", "sauces", ["soy_sauce_base", "wheat_flour", "salt"], 85),
    ("Green Chilli Sauce", "sauces", ["green_chilli", "vinegar", "garlic"], 70),
    ("Mustard Sauce", "sauces", ["mustard", "vinegar"], 130),
    # ---- Frozen ----
    ("Frozen Green Peas 1kg", "frozen", ["green_peas"], 130),
    ("Frozen Sweet Corn", "frozen", ["corn"], 110),
    ("Veg Nuggets Frozen", "frozen", ["maida", "vegetables", "spices"], 180),
    ("French Fries Frozen", "frozen", ["potato", "vegetable_oil"], 150),
    ("Frozen Paratha 5pc", "frozen", ["wheat_flour", "vegetable_oil"], 120),
    # ---- Dry fruits ----
    ("Almonds 500g", "dry_fruits", ["almonds"], 480),
    ("Cashews 500g", "dry_fruits", ["cashews"], 520),
    ("Walnuts 250g", "dry_fruits", ["walnuts"], 420),
    ("Pistachios 250g", "dry_fruits", ["pistachios"], 560),
    ("Raisins 500g", "dry_fruits", ["grapes"], 220),
    ("Dates Seedless 500g", "dry_fruits", ["dates"], 190),
    ("Mixed Dry Fruits", "dry_fruits", ["almonds", "cashews", "raisins", "pistachios"], 650),
    # ---- Fruits & vegetables ----
    ("Onion 1kg", "fruits_veg", ["onion"], 40),
    ("Tomato 1kg", "fruits_veg", ["tomato"], 45),
    ("Potato 1kg", "fruits_veg", ["potato"], 38),
    ("Banana 1 Dozen", "fruits_veg", ["banana"], 60),
    ("Apple Shimla 1kg", "fruits_veg", ["apple"], 180),
    ("Spinach Bunch", "fruits_veg", ["spinach"], 30),
    ("Cauliflower 1pc", "fruits_veg", ["cauliflower"], 40),
    ("Ginger 250g", "fruits_veg", ["ginger"], 35),
    ("Green Chilli 250g", "fruits_veg", ["green_chilli"], 20),
    # ---- Eggs ----
    ("Farm Eggs 6pc", "eggs", ["eggs"], 60),
    ("Brown Eggs 6pc", "eggs", ["eggs"], 80),
    ("Egg Whites Liquid", "eggs", ["egg_whites"], 120),
    # ---- Beverages ----
    ("Orange Juice 1L", "beverages", ["orange", "water"], 130),
    ("Cold Coffee Can", "beverages", ["coffee", "milk_solids", "sugar"], 60),
    ("Cola 750ml", "beverages", ["water", "sugar", "caffeine"], 45),
    ("Lemon Soda 750ml", "beverages", ["water", "lemon", "sugar"], 40),
    ("Coconut Water 1L", "beverages", ["coconut_water"], 95),
    ("Mango Smoothie", "beverages", ["mango", "milk_solids", "sugar"], 75),
    # ---- Health & nutrition ----
    ("Whey Protein 1kg", "health", ["whey", "cocoa", "sugar"], 1800),
    ("Plant Protein 1kg", "health", ["soybeans", "pea_protein", "cocoa"], 1600),
    ("Peanut Protein Bar", "health", ["peanuts", "sugar", "whey"], 60),
    ("Almond Energy Bar", "health", ["almonds", "dates", "oats"], 70),
    ("Multivitamin Tablets", "health", ["vitamins"], 350),
    # ---- Baby ----
    ("Baby Cereal Wheat", "baby", ["wheat_flour", "milk_powder", "sugar"], 280),
    ("Baby Cereal Rice", "baby", ["rice", "milk_powder"], 260),
    ("Infant Formula", "baby", ["milk_powder", "vegetable_oil"], 640),
]

BRANDS = ["FreshFarm", "Nature's Own", "UrbanCart", "GoodRoots", "DailyBest",
          "Kisan Pride", "Everyday", "Farmly", "PurePick", "Harvest Co",
          "Namaste", "GreenLeaf"]

# Brand-level certifications. Real certification is a producer attribute, not
# purely derivable from ingredients, so these live on the brand, not the SKU.
ORGANIC_BRANDS = {"GreenLeaf", "Harvest Co", "PurePick"}
HALAL_CERTIFIED_BRANDS = {"Namaste", "Kisan Pride", "Everyday", "FreshFarm"}

# Ingredients that make a listing ineligible for a Jain-friendly mark
# (no root vegetables, no egg). Derived from ingredients, like allergens.
JAIN_EXCLUDED_INGREDIENTS = {"onion", "garlic", "eggs", "egg_whites", "honey"}

# What each category is typically bought FOR. Substitution should preserve
# purpose, not just aisle: barista oat milk froths for coffee, plain oat milk
# doesn't serve the same job as well.
CATEGORY_USE_CASES = {
    "plant_milk": ["cereal", "coffee", "cooking"], "dairy_milk": ["cereal", "coffee", "cooking"],
    "yogurt": ["breakfast", "snacking"], "dairy_alternatives": ["cooking", "snacking"],
    "cheese": ["sandwich", "snacking", "cooking"], "bread": ["sandwich", "toast"],
    "pasta": ["dinner"], "noodles": ["dinner", "quick_meal"],
    "spreads": ["breakfast", "snacking"], "snacks": ["snacking"],
    "biscuits": ["snacking", "tea_time"], "chocolate": ["snacking", "gifting"],
    "staples": ["cooking"], "pulses_dal": ["cooking"], "tea_coffee": ["beverage"],
    "breakfast": ["breakfast"], "sauces": ["cooking"], "frozen": ["quick_meal"],
    "dry_fruits": ["snacking", "gifting"], "fruits_veg": ["cooking"],
    "eggs": ["breakfast", "cooking"], "beverages": ["refreshment"],
    "health": ["fitness"], "baby": ["baby_feeding"],
}

# Baseline nutrition per 100g/100ml by category: (calories, sugar_g, protein_g).
# Jittered and adjusted per SKU below so it is honest, not decorative.
CATEGORY_NUTRITION = {
    "plant_milk": (45, 3, 1.0), "dairy_milk": (60, 5, 3.2), "yogurt": (65, 6, 4.0),
    "dairy_alternatives": (110, 1, 10.0), "cheese": (350, 1, 20.0), "bread": (265, 4, 9.0),
    "pasta": (350, 2, 12.0), "noodles": (380, 3, 8.0), "spreads": (550, 15, 10.0),
    "snacks": (500, 3, 7.0), "biscuits": (460, 20, 6.0), "chocolate": (530, 45, 6.0),
    "staples": (350, 0, 8.0), "pulses_dal": (340, 2, 22.0), "tea_coffee": (2, 0, 0.0),
    "breakfast": (380, 15, 8.0), "sauces": (120, 15, 2.0), "frozen": (150, 3, 4.0),
    "dry_fruits": (580, 25, 15.0), "fruits_veg": (50, 5, 2.0), "eggs": (155, 1, 13.0),
    "beverages": (40, 10, 0.0), "health": (400, 10, 30.0), "baby": (400, 10, 10.0),
}

HIGH_PROTEIN_INGREDIENTS = {"whey", "soybeans", "paneer", "pigeon_peas", "mung_beans",
                            "chickpeas", "kidney_beans", "pea_protein", "eggs", "egg_whites"}


def _derive(ingredients):
    allergens = sorted({INGREDIENT_ALLERGENS[i] for i in ingredients if i in INGREDIENT_ALLERGENS})
    tags = []
    if not any(i in NON_VEGAN for i in ingredients):
        tags.append("vegan")
    if not any(i in NON_VEGETARIAN for i in ingredients):
        tags.append("vegetarian")
    if not any(i in GLUTEN_INGREDIENTS for i in ingredients):
        tags.append("gluten_free")
    return allergens, tags


def _stable_hash(key):
    h = 0
    for ch in key:
        h = (h * 31 + ord(ch)) % 1_000_003
    return h


def _use_cases_for(base_name, category):
    uses = list(CATEGORY_USE_CASES.get(category, ["general"]))
    if "Barista" in base_name:
        return ["coffee"]
    if "Original" in base_name and category == "plant_milk":
        return ["cereal", "cooking"]
    return uses


def _nutrition_for(product_id, category, ingredients):
    cal, sugar, protein = CATEGORY_NUTRITION.get(category, (200, 5, 5))
    h = _stable_hash(product_id)
    cal = round(cal * (0.9 + (h % 21) / 100))
    sugar = round(sugar * (0.85 + (h % 17) / 60), 1)
    protein = protein
    if "sugar" in ingredients or "condensed_milk" in ingredients or "jaggery" in ingredients:
        sugar = round(sugar * 1.4 + 2, 1)
    if any(i in HIGH_PROTEIN_INGREDIENTS for i in ingredients):
        protein = round(protein * 1.3 + 2, 1)
    return {"calories": cal, "sugar_g": sugar, "protein_g": protein}


def _certifications_for(product_id, brand, ingredients):
    certs = []
    if not any(i in JAIN_EXCLUDED_INGREDIENTS for i in ingredients):
        certs.append("jain_friendly")
    if brand in HALAL_CERTIFIED_BRANDS:
        certs.append("halal")
    if brand in ORGANIC_BRANDS or _stable_hash(product_id) % 17 == 0:
        certs.append("organic")
    return certs


STORES = ["HSR Layout DS-12", "Koramangala DS-04", "Indiranagar DS-07"]


def generate_store_stock(catalog, seed=7):
    """Per-store, per-SKU stock level. A product can be safe and 'in the
    catalog' while genuinely absent from the specific store fulfilling this
    order, a second, non-safety reason a swap can fail."""
    rng = random.Random(seed)
    stock = {}
    for store in STORES:
        levels = {}
        for p in catalog:
            r = rng.random()
            levels[p["id"]] = "high" if r > 0.35 else ("low" if r > 0.14 else "out")
        stock[store] = levels
    return stock


def generate_catalog(seed=42):
    """Each template gets several brand variants with price spread. ~450 SKUs."""
    rng = random.Random(seed)
    products = []
    pid = 0
    for name, category, ingredients, base_price in PRODUCT_TEMPLATES:
        n_variants = min(rng.choice([3, 4, 4, 5]), len(BRANDS))
        brands = rng.sample(BRANDS, n_variants)
        for brand in brands:
            pid += 1
            product_id = f"P{pid:03d}"
            price = round(base_price * rng.uniform(0.85, 1.25))
            allergens, tags = _derive(ingredients)
            cost_ratio = 0.55 + (_stable_hash(product_id) % 26) / 100
            cost_price = round(price * cost_ratio)
            products.append({
                "id": product_id,
                "name": f"{brand} {name}",
                "base_name": name,
                "brand": brand,
                "category": category,
                "price": price,
                "ingredients": list(ingredients),
                "allergens": allergens,
                "diet_tags": tags,
                "in_stock": True,
                "use_cases": _use_cases_for(name, category),
                "nutrition": _nutrition_for(product_id, category, ingredients),
                "certifications": _certifications_for(product_id, brand, ingredients),
                "cost_price": cost_price,
                "margin_pct": round((price - cost_price) / price * 100, 1),
                "clearance": _stable_hash(product_id) % 13 == 0,
            })
    by_cat = {}
    for p in products:
        by_cat.setdefault(p["category"], []).append(p)
    for cat_products in by_cat.values():
        prices = sorted(p["price"] for p in cat_products)
        lo = prices[len(prices) // 3]
        hi = prices[(2 * len(prices)) // 3]
        for p in cat_products:
            p["price_tier"] = "budget" if p["price"] <= lo else ("premium" if p["price"] > hi else "mid")
    return products


def generate_shoppers():
    return [
        {"id": "S1", "name": "Sneha (nut allergy, vegan)",
         "avoids_allergens": ["tree_nuts", "peanuts"], "diet": ["vegan"], "budget_sensitive": False,
         "preferred_brand": "GreenLeaf"},
        {"id": "S2", "name": "Rahul (gluten free)",
         "avoids_allergens": ["gluten"], "diet": [], "budget_sensitive": False,
         "preferred_brand": "PurePick"},
        {"id": "S3", "name": "Priya (budget shopper, no constraints)",
         "avoids_allergens": [], "diet": [], "budget_sensitive": True,
         "preferred_brand": "Everyday"},
        {"id": "S4", "name": "Aditya (egg + sesame allergy)",
         "avoids_allergens": ["eggs", "sesame"], "diet": [], "budget_sensitive": False,
         "preferred_brand": "DailyBest"},
    ]


if __name__ == "__main__":
    catalog = generate_catalog()
    cats = sorted({p["category"] for p in catalog})
    print(f"{len(catalog)} products across {len(cats)} categories")
    print("categories:", ", ".join(cats))
