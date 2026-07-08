"""SwapIQ data layer: generates a realistic synthetic grocery catalog and demo shoppers.

Every product carries ingredients. Allergens and diet tags are DERIVED from
ingredients, never hand-assigned, so the knowledge graph reasoning is honest.
"""

import random

# Ingredient -> allergen group. This is the ground truth the graph reasons over.
INGREDIENT_ALLERGENS = {
    "almonds": "tree_nuts",
    "cashews": "tree_nuts",
    "hazelnuts": "tree_nuts",
    "peanuts": "peanuts",
    "milk_solids": "dairy",
    "cream": "dairy",
    "butter": "dairy",
    "cheese": "dairy",
    "yogurt_cultures": "dairy",
    "wheat_flour": "gluten",
    "barley_malt": "gluten",
    "semolina": "gluten",
    "soybeans": "soy",
    "soy_lecithin": "soy",
    "eggs": "eggs",
}

# Ingredients that make a product non-vegan (animal-derived).
NON_VEGAN = {"milk_solids", "cream", "butter", "cheese", "yogurt_cultures", "eggs", "honey", "paneer"}
NON_VEGETARIAN = set()  # catalog is vegetarian; kept for extensibility

GLUTEN_INGREDIENTS = {"wheat_flour", "barley_malt", "semolina"}

# (name, category, base_ingredients, base_price)
PRODUCT_TEMPLATES = [
    # Plant milks: the hero category for the demo
    ("Almond Milk Unsweetened", "plant_milk", ["water", "almonds", "sea_salt"], 289),
    ("Oat Milk Barista", "plant_milk", ["water", "oats", "sea_salt"], 259),
    ("Oat Milk Original", "plant_milk", ["water", "oats"], 239),
    ("Soy Milk Natural", "plant_milk", ["water", "soybeans"], 199),
    ("Cashew Milk Creamy", "plant_milk", ["water", "cashews", "sea_salt"], 310),
    ("Coconut Milk Beverage", "plant_milk", ["water", "coconut"], 220),
    ("Rice Milk Light", "plant_milk", ["water", "rice"], 210),
    # Dairy
    ("Toned Milk", "dairy_milk", ["milk_solids", "water"], 60),
    ("Full Cream Milk", "dairy_milk", ["milk_solids", "cream"], 72),
    ("Slim Milk", "dairy_milk", ["milk_solids", "water"], 62),
    ("Greek Yogurt Plain", "yogurt", ["milk_solids", "yogurt_cultures"], 120),
    ("Coconut Yogurt Vegan", "yogurt", ["coconut", "yogurt_cultures_vegan"], 180),
    ("Fruit Yogurt Mango", "yogurt", ["milk_solids", "yogurt_cultures", "mango", "sugar"], 45),
    ("Paneer Fresh Block", "dairy_alternatives", ["paneer"], 95),
    ("Tofu Firm", "dairy_alternatives", ["soybeans", "water"], 85),
    # Breads
    ("Whole Wheat Bread", "bread", ["wheat_flour", "yeast", "sugar"], 45),
    ("Multigrain Bread", "bread", ["wheat_flour", "oats", "seeds", "yeast"], 55),
    ("Gluten Free Bread", "bread", ["rice", "tapioca_starch", "yeast"], 150),
    ("Sourdough Loaf", "bread", ["wheat_flour", "yeast"], 120),
    ("Milk Bread", "bread", ["wheat_flour", "milk_solids", "butter", "yeast"], 50),
    # Pasta and noodles
    ("Durum Penne Pasta", "pasta", ["semolina"], 110),
    ("Gluten Free Penne", "pasta", ["rice", "corn"], 190),
    ("Whole Wheat Spaghetti", "pasta", ["wheat_flour"], 125),
    ("Instant Noodles Masala", "pasta", ["wheat_flour", "palm_oil", "spices"], 14),
    # Spreads
    ("Peanut Butter Crunchy", "spreads", ["peanuts", "sugar", "salt"], 250),
    ("Almond Butter Natural", "spreads", ["almonds"], 480),
    ("Hazelnut Cocoa Spread", "spreads", ["hazelnuts", "cocoa", "sugar", "milk_solids"], 350),
    ("Sesame Tahini", "spreads", ["sesame"], 320),
    ("Mixed Fruit Jam", "spreads", ["fruit", "sugar", "pectin"], 140),
    # Snacks
    ("Salted Potato Chips", "snacks", ["potato", "vegetable_oil", "salt"], 30),
    ("Nachos Cheese", "snacks", ["corn", "vegetable_oil", "cheese"], 50),
    ("Roasted Makhana", "snacks", ["foxnuts", "vegetable_oil", "salt"], 99),
    ("Trail Mix Nutty", "snacks", ["almonds", "cashews", "raisins"], 220),
    ("Banana Chips", "snacks", ["banana", "coconut_oil", "salt"], 60),
    # Biscuits
    ("Marie Light Biscuits", "biscuits", ["wheat_flour", "sugar", "vegetable_oil"], 30),
    ("Chocolate Chip Cookies", "biscuits", ["wheat_flour", "butter", "sugar", "cocoa"], 90),
    ("Oat Digestive Biscuits", "biscuits", ["oats", "wheat_flour", "sugar"], 55),
    ("Gluten Free Cookies", "biscuits", ["rice", "butter", "sugar"], 160),
    # Chocolate
    ("Milk Chocolate Bar", "chocolate", ["cocoa", "milk_solids", "sugar"], 80),
    ("Dark Chocolate 70%", "chocolate", ["cocoa", "sugar"], 150),
    ("Hazelnut Chocolate", "chocolate", ["cocoa", "hazelnuts", "milk_solids", "sugar"], 120),
    ("Vegan Dark Chocolate", "chocolate", ["cocoa", "coconut_sugar"], 210),
    # Staples
    ("Whole Wheat Atta 5kg", "staples", ["wheat_flour"], 260),
    ("Basmati Rice 1kg", "staples", ["rice"], 180),
    ("Sunflower Oil 1L", "staples", ["sunflower_oil"], 145),
    ("Cold Pressed Coconut Oil", "staples", ["coconut_oil"], 320),
    # Beverages
    ("Orange Juice 1L", "beverages", ["orange", "water"], 130),
    ("Cold Coffee Can", "beverages", ["coffee", "milk_solids", "sugar"], 60),
    ("Green Tea 25 Bags", "beverages", ["green_tea"], 175),
    ("Cola 750ml", "beverages", ["water", "sugar", "caffeine"], 45),
]

BRANDS = ["FreshFarm", "Nature's Own", "UrbanCart", "GoodRoots", "DailyBest"]


def _derive(ingredients):
    """Derive allergens and diet tags from the ingredient list."""
    allergens = sorted({INGREDIENT_ALLERGENS[i] for i in ingredients if i in INGREDIENT_ALLERGENS})
    tags = []
    if not any(i in NON_VEGAN for i in ingredients):
        tags.append("vegan")
    if not any(i in NON_VEGETARIAN for i in ingredients):
        tags.append("vegetarian")
    if not any(i in GLUTEN_INGREDIENTS for i in ingredients):
        tags.append("gluten_free")
    return allergens, tags


def generate_catalog(seed=42):
    """~200 SKUs: each template gets several brand variants with price spread."""
    rng = random.Random(seed)
    products = []
    pid = 0
    for name, category, ingredients, base_price in PRODUCT_TEMPLATES:
        n_variants = rng.choice([3, 4, 4, 5])
        brands = rng.sample(BRANDS, n_variants)
        for brand in brands:
            pid += 1
            price = round(base_price * rng.uniform(0.85, 1.25))
            allergens, tags = _derive(ingredients)
            products.append({
                "id": f"P{pid:03d}",
                "name": f"{brand} {name}",
                "base_name": name,
                "brand": brand,
                "category": category,
                "price": price,
                "ingredients": list(ingredients),
                "allergens": allergens,
                "diet_tags": tags,
                "in_stock": True,
            })
    # Price tiers within each category: budget / mid / premium by terciles
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
    """Demo personas. Constraints drive the graph filtering."""
    return [
        {
            "id": "S1",
            "name": "Sneha (nut allergy, vegan)",
            "avoids_allergens": ["tree_nuts", "peanuts"],
            "diet": ["vegan"],
            "budget_sensitive": False,
        },
        {
            "id": "S2",
            "name": "Rahul (gluten free)",
            "avoids_allergens": ["gluten"],
            "diet": [],
            "budget_sensitive": False,
        },
        {
            "id": "S3",
            "name": "Priya (budget shopper, no constraints)",
            "avoids_allergens": [],
            "diet": [],
            "budget_sensitive": True,
        },
    ]


if __name__ == "__main__":
    catalog = generate_catalog()
    print(f"{len(catalog)} products generated")
    print(catalog[0])
