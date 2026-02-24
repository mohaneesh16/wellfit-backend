import pandas as pd
from app.db import SessionLocal
from app.models import Food

print("Loading CSV files...")

food_df = pd.read_csv("data/food.csv", usecols=["fdc_id", "description"])
food_nutrient_df = pd.read_csv("data/food_nutrient.csv", usecols=["fdc_id", "nutrient_id", "amount"])

# Load Indian foods dataset
try:
    indian_df = pd.read_csv("data/indian_foods_500.csv")
    print("Indian foods CSV loaded.")
except Exception as e:
    indian_df = None
    print("Indian foods CSV not found.")

# Nutrient IDs (USDA Standard)
CALORIES_ID = 1008
PROTEIN_ID = 1003
FAT_ID = 1004
CARB_ID = 1005

print("Filtering only required nutrients...")

filtered_nutrients = food_nutrient_df[
    food_nutrient_df["nutrient_id"].isin(
        [CALORIES_ID, PROTEIN_ID, FAT_ID, CARB_ID]
    )
]

print("Grouping nutrients...")

pivot = filtered_nutrients.pivot_table(
    index="fdc_id",
    columns="nutrient_id",
    values="amount",
    aggfunc="sum"
).reset_index()

pivot.columns.name = None

db = SessionLocal()

print("Importing foods into database...")

for _, row in pivot.iterrows():
    fdc_id = row["fdc_id"]

    food_info = food_df[food_df["fdc_id"] == fdc_id]
    if food_info.empty:
        continue

    name = food_info.iloc[0]["description"]

    calories = row.get(CALORIES_ID, 0)
    protein = row.get(PROTEIN_ID, 0)
    fats = row.get(FAT_ID, 0)
    carbs = row.get(CARB_ID, 0)

    if calories and calories > 0:
        existing = db.query(Food).filter_by(fdc_id=int(fdc_id)).first()

        if not existing:
            new_food = Food(
                fdc_id=int(fdc_id),
                name=name,
                calories=float(calories),
                protein=float(protein) if protein else 0,
                carbs=float(carbs) if carbs else 0,
                fats=float(fats) if fats else 0
            )
            db.add(new_food)

# Commit USDA foods first
db.commit()

# -------------------------------------------------
# Import Indian foods into database
# -------------------------------------------------
if indian_df is not None:
    print("Importing Indian foods into database...")

    indian_fdc_start = 9000000

    for index, row in indian_df.iterrows():
        new_id = indian_fdc_start + index

        new_food = Food(
            fdc_id=new_id,
            name=row["food_name"],
            calories=float(row["calories_per_100g"]),
            protein=float(row["protein_g"]),
            carbs=float(row["carbs_g"]),
            fats=float(row["fats_g"])
        )

        db.add(new_food)

    db.commit()
    print("Indian foods imported successfully.")