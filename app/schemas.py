from pydantic import BaseModel
from typing import Optional
from enum import Enum

class GoalEnum(str, Enum):
    weight_loss = "weight_loss"
    muscle_gain = "muscle_gain"
    maintenance = "maintenance"

class UserCreate(BaseModel):
    name: str
    email: str
    password: str
    age: int
    gender: str
    height: float
    weight: float
    goal: GoalEnum

class WorkoutCreate(BaseModel):
    exercise: str
    duration: int
    calories: float


class MealCreate(BaseModel):
    meal_name: str
    calories: float
    protein: float
    carbs: float
    fats: float


class WearableCreate(BaseModel):
    user_id: int
    steps: int
    heart_rate: int
    sleep_hours: float

class AnalyzeWorkout(BaseModel):
    weight: float
    sets: int
    reps: int
    heart_rate: int
    duration: int