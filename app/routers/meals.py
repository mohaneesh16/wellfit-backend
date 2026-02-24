from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db import get_db
from app import models
from app.auth import get_current_user
from pydantic import BaseModel

router = APIRouter()

@router.post("/")
def add_meal(
    name: str,
    quantity: float,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    food = db.query(models.Food).filter(
        models.Food.name == name.lower()
    ).first()

    if not food:
        raise HTTPException(status_code=404, detail="Food not found")

    calories = (food.calories_per_100g / 100) * quantity

    meal = models.Meal(
        user_id=current_user.id,
        meal_name=food.name,
        calories=calories
    )

    db.add(meal)
    db.commit()
    db.refresh(meal)

    return {
        "message": "Meal added",
        "calories": calories
    }


class QuickMealRequest(BaseModel):
    name: str
    quantity: float

@router.post("/quick")
def add_quick_meal(
    meal: QuickMealRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    new_meal = models.Meal(
        user_id=current_user.id,
        meal_name=meal.name,
        calories=0
    )

    db.add(new_meal)
    db.commit()
    db.refresh(new_meal)

    return {
        "message": "Quick meal added",
        "name": meal.name,
        "quantity": meal.quantity
    }