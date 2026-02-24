from app.database import SessionLocal
from app import models

def seed_foods():
    db = SessionLocal()

    foods = [
        models.Food(name="rice", calories_per_100g=130),
        models.Food(name="chicken", calories_per_100g=165),
        models.Food(name="egg", calories_per_100g=155),
        models.Food(name="banana", calories_per_100g=89),
        models.Food(name="apple", calories_per_100g=52),
        models.Food(name="milk", calories_per_100g=42),
        models.Food(name="bread", calories_per_100g=265),
        models.Food(name="dal", calories_per_100g=116),
    ]

    for food in foods:
        if not db.query(models.Food).filter(models.Food.name == food.name).first():
            db.add(food)

    db.commit()
    db.close()

if __name__ == "__main__":
    seed_foods()