from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app import models, schemas
from app.db import SessionLocal, engine
# from app.ml.predictor import predict_intensity, predict_calories
from pydantic import BaseModel
from app.services.recommendation import recommend_meal
from fastapi.middleware.cors import CORSMiddleware
from datetime import date
from datetime import timedelta
from dotenv import load_dotenv
from openai import OpenAI
import json
from app.auth import hash_password, verify_password, create_access_token, get_current_user
from fastapi.security import OAuth2PasswordRequestForm
from app.routers import users
from app.routers import meals
from sklearn.linear_model import LinearRegression
import numpy as np
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from fastapi.responses import RedirectResponse
import os
import pytz


models.Base.metadata.create_all(bind=engine)

try:
    load_dotenv(dotenv_path=".env", override=False)
except Exception as e:
    print("WARNING: .env file could not be loaded:", str(e))
api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    print("WARNING: OPENAI_API_KEY not found. AI meal-plan feature will be disabled.")
    client = None
else:
    client = OpenAI(api_key=api_key)

# OpenAI client initialized securely using environment variable
class AnalyzeWorkout(BaseModel):
    weight: float
    sets: int
    reps: int
    heart_rate: int
    duration: int

# ---- Daily Meal Plan Request Model ----
class DailyMealPlanRequest(BaseModel):
    diet_type: str  # veg / nonveg / mixed

app = FastAPI(title="AI Health App ")
# Root route
@app.get("/")
def root():
    return {"message": "WELLFIT Backend Running"}

# Include routers
app.include_router(users.router)
app.include_router(meals.router, prefix="/meals")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/status")
def status():
    return {"message": "Module 1 is running successfully"}


@app.post("/user")
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = models.User(**user.dict())
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


@app.post("/workout")
def add_workout(
    workout: schemas.WorkoutCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    db_workout = models.Workout(
        user_id=current_user.id,
        exercise=workout.exercise,
        duration=workout.duration,
        calories=workout.calories
    )

    db.add(db_workout)
    db.commit()
    db.refresh(db_workout)

    return {"message": "Workout saved"}


# New endpoint: Workout history
@app.get("/workout/history")
def workout_history(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    workouts = db.query(models.Workout).filter(
        models.Workout.user_id == current_user.id
    ).all()

    return [
    {
        "id": w.id,
        "exercise": w.exercise,
        "duration": w.duration,
        "calories": w.calories
    }
    for w in workouts
    ]



@app.post("/meal")
def add_meal(meal: schemas.MealCreate, db: Session = Depends(get_db)):
    db_meal = models.Meal(**meal.dict())
    db.add(db_meal)
    db.commit()
    return {"message": "Meal saved"}


@app.post("/wearable")
def add_wearable(data: schemas.WearableCreate, db: Session = Depends(get_db)):
    db_data = models.WearableData(**data.dict())
    db.add(db_data)
    db.commit()
    return {"message": "Wearable data saved"}

@app.post("/analyze/workout")
def analyze_workout(data: AnalyzeWorkout, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    user = current_user

    if not user:
        return {"error": "No user found. Please create a user first."}

    goal = user.goal
    # Temporary fallback logic (ML disabled)
    intensity = "Moderate"
    calories = data.duration * 5  # simple estimation
    meal = recommend_meal(intensity, calories, goal)

    analysis = models.WorkoutAnalysis(
        user_id=user.id,
        intensity=intensity,
        calories=float(calories),
        recommended_meal=meal
    )
    db.add(analysis)
    db.commit()
    return {
        "predicted_intensity": intensity,
        "estimated_calories": round(float(calories), 2),
        "recommended_meal": meal,
        "goal_used": goal
    }
@app.get("/analysis/history")
def get_analysis_history(db: Session = Depends(get_db)):
    records = db.query(models.WorkoutAnalysis).all()

    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "intensity": r.intensity,
            "calories": r.calories,
            "recommended_meal": r.recommended_meal,
            "created_at": r.created_at
        }
        for r in records
    ]
@app.get("/analysis/summary")
def performance_summary(db: Session = Depends(get_db)):

    records = db.query(models.WorkoutAnalysis).all()

    if not records:
        return {"message": "No workout analysis data available"}

    total_sessions = len(records)
    avg_calories = sum(r.calories for r in records) / total_sessions

    high_intensity_count = sum(1 for r in records if r.intensity == "High")

    return {
        "total_sessions": total_sessions,
        "average_calories_burned": round(avg_calories, 2),
        "high_intensity_sessions": high_intensity_count
    }



@app.get("/dashboard")
def dashboard_summary(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    user_id = current_user.id

    today = date.today()
    from datetime import datetime
    start_of_day = datetime.combine(today, datetime.min.time())

    from datetime import datetime
    start_of_day = datetime.combine(today, datetime.min.time())
    end_of_day = start_of_day + timedelta(days=1)

    meals = db.query(models.Meal).filter(
        models.Meal.user_id == user_id,
        models.Meal.created_at >= start_of_day,
        models.Meal.created_at < end_of_day
    ).all()

    calories_consumed = sum(m.calories or 0 for m in meals)

    workouts = db.query(models.WorkoutAnalysis).filter(
        models.WorkoutAnalysis.user_id == user_id,
        models.WorkoutAnalysis.created_at >= start_of_day
    ).all()

    calories_burned = sum(w.calories for w in workouts)

    wearable = db.query(models.WearableData).filter(
        models.WearableData.user_id == user_id,
        models.WearableData.date == today
    ).all()

    steps = sum(w.steps for w in wearable)
    avg_heart_rate = (
        sum(w.heart_rate for w in wearable) / len(wearable)
        if wearable else 0
    )

    # ---- Persist Daily Summary for historical tracking ----
    net_calories = calories_consumed - calories_burned

    existing = db.query(models.DailySummary).filter(
        models.DailySummary.user_id == user_id,
        models.DailySummary.date == today
    ).first()

    if existing:
        existing.calories_consumed = calories_consumed
        existing.calories_burned = calories_burned
        existing.net_calories = net_calories
    else:
        new_summary = models.DailySummary(
            user_id=user_id,
            date=today,
            calories_consumed=calories_consumed,
            calories_burned=calories_burned,
            net_calories=net_calories
        )
        db.add(new_summary)

    db.commit()
    # ---- End persistence logic ----

    google_steps = None
    google_calories = None
    google_avg_heart_rate = None

    if current_user.google_access_token:
        try:
            google_data = fetch_google_fit_summary(current_user)
            google_steps = google_data.get("google_steps_today") or google_data.get("google_steps") or 0
            google_calories = google_data.get("google_calories_today") or google_data.get("google_calories") or 0
            google_avg_heart_rate = google_data.get("google_avg_heart_rate") or 0
        except Exception as e:
            print("GOOGLE FETCH ERROR:", str(e))
            google_steps = 0
            google_calories = 0
            google_avg_heart_rate = 0


    return {
        "calories_consumed": calories_consumed,
        "calories_burned": calories_burned,
        "net_calories": calories_consumed - calories_burned,
        "local_steps": steps,
        "google_steps": google_steps,
        "google_calories": google_calories,
        "google_avg_heart_rate": google_avg_heart_rate,
        "avg_heart_rate": round(avg_heart_rate, 2)
    }

# New endpoint: daily macro summary
@app.get("/macros/daily-summary")
def daily_macro_summary(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    user_id = current_user.id
    today = date.today()

    from datetime import datetime
    start_of_day = datetime.combine(today, datetime.min.time())
    end_of_day = start_of_day + timedelta(days=1)

    meals = db.query(models.Meal).filter(
        models.Meal.user_id == user_id,
        models.Meal.created_at >= start_of_day,
        models.Meal.created_at < end_of_day
    ).all()

    if not meals:
        return {
            "calories": 0,
            "protein": 0,
            "carbs": 0,
            "fats": 0,
            "message": "No meals logged today"
        }

    total_calories = sum(getattr(m, "calories", 0) or 0 for m in meals)
    total_protein = sum(getattr(m, "protein", 0) or 0 for m in meals)
    total_carbs = sum(getattr(m, "carbs", 0) or 0 for m in meals)
    total_fats = sum(getattr(m, "fats", 0) or 0 for m in meals)

    # Optional: include daily target comparison
    target_record = db.query(models.DailyTarget).filter(
        models.DailyTarget.user_id == user_id
    ).order_by(models.DailyTarget.id.desc()).first()

    target_calories = target_record.target_calories if target_record else 0

    return {
        "calories": round(total_calories, 2),
        "protein": round(total_protein, 2),
        "carbs": round(total_carbs, 2),
        "fats": round(total_fats, 2),
        "calorie_target": round(target_calories, 2),
        "remaining_calories": round(target_calories - total_calories, 2) if target_calories else None
    }
@app.post("/calculate/target")
def calculate_target(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    user_id = current_user.id

    user = db.query(models.User).filter(models.User.id == user_id).first()

    if not user:
        return {"error": "User not found"}

    # Simple BMR formula (Mifflin-St Jeor simplified)
    weight = user.weight
    height = user.height
    age = user.age

    if user.gender == "male":
        bmr = (10 * weight) + (6.25 * height) - (5 * age) + 5
    else:
        bmr = (10 * weight) + (6.25 * height) - (5 * age) - 161

    # Activity multiplier (basic assumption)
    activity_factor = 1.4
    maintenance_calories = bmr * activity_factor

    # Goal adjustment
    if user.goal == "weight_loss":
        target = maintenance_calories - 500
    elif user.goal == "muscle_gain":
        target = maintenance_calories + 400
    else:
        target = maintenance_calories

    daily_target = models.DailyTarget(
        user_id=user.id,
        target_calories=target
    )

    db.add(daily_target)
    db.commit()

    return {
        "goal": user.goal,
        "daily_calorie_target": round(target, 2)
    }

@app.get("/weekly/progress")
def weekly_progress(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    user_id = current_user.id

    today = date.today()
    week_ago = today - timedelta(days=7)

    # Get latest daily target
    target_record = db.query(models.DailyTarget).filter(
        models.DailyTarget.user_id == user_id
    ).order_by(models.DailyTarget.id.desc()).first()

    if not target_record:
        return {"error": "No daily target found"}

    weekly_target = target_record.target_calories * 7

    # Meals in last 7 days
    from datetime import datetime
    start_week = datetime.combine(week_ago, datetime.min.time())

    meals = db.query(models.Meal).filter(
        models.Meal.user_id == user_id,
        models.Meal.created_at >= start_week
    ).all()

    actual_consumed = sum(m.calories or 0 for m in meals)

    # Workout analysis in last 7 days
    workouts = db.query(models.WorkoutAnalysis).filter(
        models.WorkoutAnalysis.user_id == user_id,
        models.WorkoutAnalysis.created_at >= week_ago
    ).all()

    actual_burned = sum(w.calories for w in workouts)

    # Adherence %
    if weekly_target == 0:
        adherence = 0
    else:
        adherence = (actual_consumed / weekly_target) * 100

    return {
        "weekly_target": round(weekly_target, 2),
        "actual_consumed": round(actual_consumed, 2),
        "actual_burned": round(actual_burned, 2),
        "adherence_percentage": round(adherence, 2)
    }
@app.get("/insights")
def generate_insights(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    user_id = current_user.id

    records = db.query(models.WorkoutAnalysis).filter(
        models.WorkoutAnalysis.user_id == user_id
    ).all()

    if not records:
        return {"insight": "No workout data available yet."}

    avg_calories = sum(r.calories for r in records) / len(records)
    high_sessions = sum(1 for r in records if r.intensity == "High")

    if avg_calories < 200:
        message = "Your workouts are low impact. Consider increasing duration or intensity."
    elif high_sessions > 3:
        message = "Great consistency with high intensity sessions. Ensure proper recovery."
    else:
        message = "You are maintaining moderate performance. Keep pushing gradually."

    return {
        "average_calories": round(avg_calories, 2),
        "high_intensity_sessions": high_sessions,
        "insight": message
    }

@app.get("/meal-plan")
def generate_meal_plan(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    user_id = current_user.id
    today = date.today()
    if client is None:
        return {"error": "AI service unavailable. OPENAI_API_KEY not configured."}

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return {"error": "User not found"}

    from datetime import datetime
    start_of_day = datetime.combine(today, datetime.min.time())
    end_of_day = start_of_day + timedelta(days=1)

    meals = db.query(models.Meal).filter(
        models.Meal.user_id == user_id,
        models.Meal.created_at >= start_of_day,
        models.Meal.created_at < end_of_day
    ).all()

    calories_consumed = sum(m.calories or 0 for m in meals)
    protein_consumed = sum(m.protein or 0 for m in meals)
    carbs_consumed = sum(m.carbs or 0 for m in meals)
    fats_consumed = sum(m.fats or 0 for m in meals)

    workouts = db.query(models.WorkoutAnalysis).filter(
        models.WorkoutAnalysis.user_id == user_id
    ).all()

    calories_burned = sum(w.calories for w in workouts)

    net_calories = calories_consumed - calories_burned

    target_record = db.query(models.DailyTarget).filter(
        models.DailyTarget.user_id == user_id
    ).order_by(models.DailyTarget.id.desc()).first()

    if not target_record:
        return {"error": "No daily target found"}

    daily_target = target_record.target_calories
    remaining_calories = daily_target - net_calories

    if remaining_calories <= 0:
        return {"message": "Daily calorie target reached"}

    # Macro targets
    weight = user.weight
    protein_target = weight * 1.8
    carb_target = daily_target * 0.5 / 4
    fat_target = daily_target * 0.25 / 9

    remaining_protein = protein_target - protein_consumed
    remaining_carbs = carb_target - carbs_consumed
    remaining_fats = fat_target - fats_consumed

    prompt = f"""
You are an elite AI sports nutritionist.

User goal: {user.goal}
Remaining Calories: {round(remaining_calories,2)}
Remaining Protein: {round(remaining_protein,2)} g
Remaining Carbs: {round(remaining_carbs,2)} g
Remaining Fats: {round(remaining_fats,2)} g

Generate ONE optimized meal.

Rules:
- Stay within remaining calories
- Respect macro needs
- Realistic food
- Include macro breakdown
- No markdown
- Return RAW JSON only

Format:
{{
  "meal_name": "",
  "calories": 0,
  "protein": 0,
  "carbs": 0,
  "fats": 0,
  "best_time_to_consume": "",
  "reason": ""
}}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Return ONLY raw JSON."},
                {"role": "user", "content": prompt}
            ]
        )

        ai_output = response.choices[0].message.content.strip()

        if ai_output.startswith("```"):
            ai_output = ai_output.replace("```json", "").replace("```", "").strip()

        parsed = json.loads(ai_output)

    except Exception as e:
        # Fallback safety
        parsed = {
            "meal_name": "Balanced Protein Meal",
            "calories": min(remaining_calories, 500),
            "protein": 30,
            "carbs": 50,
            "fats": 15,
            "best_time_to_consume": "Dinner",
            "reason": "Fallback recommendation due to AI parsing issue."
        }
        # Save AI meal into DB
        ai_meal = models.Meal(
            user_id=user_id,
            meal_name=parsed["meal_name"],
            calories=parsed["calories"],
            protein=parsed["protein"],
            carbs=parsed["carbs"],
            fats=parsed["fats"]
        )

        db.add(ai_meal)
        db.commit()
        db.refresh(ai_meal)

    return {
        "goal": user.goal,
        "remaining_calories": round(remaining_calories,2),
        "calories_consumed": calories_consumed,
        "calories_burned": calories_burned,
        "net_calories": net_calories,
        "recommended_meal": parsed
    }

# ---- New Daily Meal Plan Endpoint ----
@app.post("/daily-meal-plan")
def generate_daily_meal_plan(
    request: DailyMealPlanRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    if client is None:
        return {"error": "AI service unavailable. OPENAI_API_KEY not configured."}

    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    if not user:
        return {"error": "User not found"}

    diet_type = request.diet_type.lower()

    target_record = db.query(models.DailyTarget).filter(
        models.DailyTarget.user_id == user.id
    ).order_by(models.DailyTarget.id.desc()).first()

    if not target_record:
        return {"error": "No daily target found"}

    daily_target = target_record.target_calories

    prompt = f"""
You are an elite sports nutritionist.

User goal: {user.goal}
Daily calorie target: {round(daily_target,2)}
Diet preference: {diet_type}

Generate a FULL DAY MEAL PLAN with:
- Breakfast
- Brunch
- Lunch
- Evening Snacks
- Dinner

Rules:
- Strictly follow diet preference
- Veg = vegetarian only
- Nonveg = may include chicken, egg, fish
- Mixed = both allowed
- Realistic Indian-style meals
- Balanced macros
- Return RAW JSON only

Format:
{{
  "breakfast": {{ "meal_name": "", "calories": 0, "protein": 0, "carbs": 0, "fats": 0 }},
  "brunch": {{ "meal_name": "", "calories": 0, "protein": 0, "carbs": 0, "fats": 0 }},
  "lunch": {{ "meal_name": "", "calories": 0, "protein": 0, "carbs": 0, "fats": 0 }},
  "evening_snacks": {{ "meal_name": "", "calories": 0, "protein": 0, "carbs": 0, "fats": 0 }},
  "dinner": {{ "meal_name": "", "calories": 0, "protein": 0, "carbs": 0, "fats": 0 }}
}}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Return ONLY raw JSON."},
                {"role": "user", "content": prompt}
            ]
        )

        ai_output = response.choices[0].message.content.strip()

        if ai_output.startswith("```"):
            ai_output = ai_output.replace("```json", "").replace("```", "").strip()

        parsed = json.loads(ai_output)

        return parsed

    except Exception as e:
        return {"error": str(e)}
@app.get("/users")
def get_users(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    return db.query(models.User).all()

@app.get("/meal/history")
def meal_history(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    user_id = current_user.id
    meals = db.query(models.Meal).filter(
        models.Meal.user_id == user_id
    ).all()

    return meals


# New endpoint: Delete a meal by ID
@app.delete("/meal/{meal_id}")
def delete_meal(
    meal_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    meal = db.query(models.Meal).filter(
        models.Meal.id == meal_id,
        models.Meal.user_id == current_user.id
    ).first()

    if not meal:
        raise HTTPException(status_code=404, detail="Meal not found")

    db.delete(meal)
    db.commit()

    return {"message": "Meal removed successfully"}

@app.get("/weekly/prediction")
def predict_weekly_trend(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    user_id = current_user.id

    # Get last 7 days net calories
    weekly_data = db.query(models.DailySummary).filter(
        models.DailySummary.user_id == user_id
    ).order_by(models.DailySummary.date.asc()).limit(14).all()

    if len(weekly_data) < 5:
        return {"error": "Not enough data for prediction"}

    # Prepare data
    X = np.array(range(len(weekly_data))).reshape(-1, 1)
    y = np.array([d.net_calories for d in weekly_data])

    # Train model
    model = LinearRegression()
    model.fit(X, y)

    # Predict next 7 days
    future_days = np.array(range(len(weekly_data), len(weekly_data) + 7)).reshape(-1, 1)
    predictions = model.predict(future_days)

    return {
        "predicted_next_7_days": predictions.tolist()
    }

@app.get("/ai-meals")
def get_ai_meals(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    user_id = current_user.id
    meals = db.query(models.Meal).filter(
    models.Meal.user_id == user_id
    ).all()

    return meals

@app.get("/performance-score")
def performance_score(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    user_id = current_user.id

    meals = db.query(models.Meal).filter(
        models.Meal.user_id == user_id
    ).all()

    workouts = db.query(models.WorkoutAnalysis).filter(
        models.WorkoutAnalysis.user_id == user_id
    ).all()

    if not meals:
        return {"score": 0}

    avg_calories = sum(m.calories or 0 for m in meals) / len(meals)
    workout_count = len(workouts)

    score = min(100, (avg_calories / 2000) * 50 + workout_count * 5)

    return {
        "nutrition_score": round(score, 2),
        "total_workouts": workout_count
    }

@app.get("/system-info")
def system_info():
    return {
        "project": "WellFit AI",
        "engine": "GenAI Powered Personalized Nutrition & Fitness System",
        "ai_model": "gpt-4o-mini",
        "features": [
            "Dynamic Meal Recommendation",
            "Macro Optimization",
            "Workout Analysis",
            "Performance Tracking",
            "Wearable Integration Ready"
        ]
    }


# Food search endpoint
@app.get("/foods/search")
def search_foods(
    q: str = Query(..., min_length=2),
    limit: int = 20,
    db: Session = Depends(get_db)
):
    foods = (
        db.query(models.Food)
        .filter(models.Food.name.ilike(f"%{q}%"))
        .limit(limit)
        .all()
    )

    return [
        {
            "id": food.id,
            "fdc_id": food.fdc_id,
            "name": food.name,
            "calories_per_100g": food.calories,
            "protein_per_100g": food.protein,
            "carbs_per_100g": food.carbs,
            "fats_per_100g": food.fats
        }
        for food in foods
    ]

# Add meal by food id endpoint
@app.post("/meals/add-by-food-id")
def add_meal_by_food_id(
    food_id: int,
    grams: float,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    user_id = current_user.id

    food = db.query(models.Food).filter(models.Food.id == food_id).first()

    if not food:
        raise HTTPException(status_code=404, detail="Food not found")

    factor = grams / 100

    calories = (food.calories or 0) * factor
    protein = (food.protein or 0) * factor
    carbs = (food.carbs or 0) * factor
    fats = (food.fats or 0) * factor

    new_meal = models.Meal(
        user_id=user_id,
        meal_name=food.name,
        calories=calories,
        protein=protein,
        carbs=carbs,
        fats=fats
        )

    db.add(new_meal)
    db.commit()
    db.refresh(new_meal)

    return {
        "message": "Meal added successfully",
        "food": food.name,
        "grams": grams,
        "calories": round(calories, 2)
    }
@app.post("/register")
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):

    existing = db.query(models.User).filter(models.User.email == user.email).first()
    if existing:
        return {"error": "Email already registered"}

    new_user = models.User(
        name=user.name,
        email=user.email,
        hashed_password=hash_password(user.password),
        age=user.age,
        gender=user.gender,
        height=user.height,
        weight=user.weight,
        goal=user.goal
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {"message": "User registered successfully"}

@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):

    user = db.query(models.User).filter(models.User.email == form_data.username).first()

    if not user:
        raise HTTPException(status_code=401, detail="Invalid email")

    if not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid password")

    token = create_access_token(user.id)

    return {
        "access_token": token,
        "token_type": "bearer"
    }
@app.get("/weekly/history")
def weekly_history(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    user_id = current_user.id

    today = date.today()
    week_ago = today - timedelta(days=7)

    records = db.query(models.DailySummary).filter(
        models.DailySummary.user_id == user_id,
        models.DailySummary.date >= week_ago
    ).order_by(models.DailySummary.date.asc()).all()

    return [
        {
            "date": r.date,
            "net_calories": r.net_calories
        }
        for r in records
    ]

GOOGLE_CLIENT_SECRETS_FILE = "client_secret.json"

GOOGLE_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/fitness.activity.read",
    "https://www.googleapis.com/auth/fitness.heart_rate.read",
    "https://www.googleapis.com/auth/fitness.body.read"
]

GOOGLE_REDIRECT_URI = "http://localhost:8000/auth/google/callback"

@app.get("/auth/google/login")
def google_login(current_user = Depends(get_current_user)):

    flow = Flow.from_client_secrets_file(
        GOOGLE_CLIENT_SECRETS_FILE,
        scopes=GOOGLE_SCOPES,
        redirect_uri=GOOGLE_REDIRECT_URI
    )

    # Store user id inside state
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        state=str(current_user.id)
    )

    return {"auth_url": authorization_url}

@app.get("/auth/google/callback")
def google_callback(
    code: str,
    state: str,
    db: Session = Depends(get_db)
):
    try:
        flow = Flow.from_client_secrets_file(
            GOOGLE_CLIENT_SECRETS_FILE,
            scopes=GOOGLE_SCOPES,
            redirect_uri=GOOGLE_REDIRECT_URI
        )

        flow.fetch_token(code=code)
        credentials = flow.credentials

        user_id = int(state)

        user = db.query(models.User).filter(models.User.id == user_id).first()

        if not user:
            return {"error": "User not found"}

        user.google_access_token = credentials.token
        user.google_refresh_token = credentials.refresh_token
        user.google_token_uri = credentials.token_uri
        user.google_client_id = credentials.client_id
        user.google_client_secret = credentials.client_secret

        db.commit()

        return {"message": "Google Fit connected successfully"}

    except Exception as e:
        return {"error": str(e)}

@app.get("/test/google-fit")
def test_google_fit(token: str):
    creds = Credentials(token=token)
    service = build("fitness", "v1", credentials=creds)

    datasets = service.users().dataSources().list(userId="me").execute()
    return datasets


# Google Fit summary fetch utility (top-level)
def fetch_google_fit_summary(user):
    creds = Credentials(
    token=user.google_access_token,
    refresh_token=user.google_refresh_token,
    token_uri=user.google_token_uri,
    client_id=user.google_client_id,
    client_secret=user.google_client_secret
)

    # If token expired, refresh automatically
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    service = build("fitness", "v1", credentials=creds)

    from datetime import datetime, timedelta

    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_time = int(start_of_day.timestamp() * 1000)
    end_time = int(now.timestamp() * 1000)

    body = {
    "aggregateBy": [
        {"dataTypeName": "com.google.step_count.delta"},
        {"dataTypeName": "com.google.calories.expended"},
        {"dataTypeName": "com.google.heart_rate.bpm"}
    ],
    "bucketByTime": {
        "durationMillis": 86400000
    },
    "startTimeMillis": start_time,
    "endTimeMillis": end_time
}

    result = service.users().dataset().aggregate(
        userId="me",
        body=body
    ).execute()

    total_steps = 0
    total_calories = 0
    heart_rates = []


    for bucket in result.get("bucket", []):
        for dataset in bucket.get("dataset", []):
            data_source_id = dataset.get("dataSourceId", "")

            for point in dataset.get("point", []):
                data_type = point.get("dataTypeName", "")

                for value in point.get("value", []):

                    # Steps
                    if "step_count" in data_source_id or data_type == "com.google.step_count.delta":
                        total_steps += value.get("intVal", 0)

                    # Calories
                    elif "calories" in data_source_id or data_type == "com.google.calories.expended":
                        total_calories += value.get("fpVal", 0)

                    # Heart Rate
                    elif "heart_rate" in data_source_id or data_type == "com.google.heart_rate.bpm":
                        if value.get("fpVal") is not None:
                            heart_rates.append(value.get("fpVal"))
    if not heart_rates:
        data_sources = service.users().dataSources().list(userId="me").execute()

        for ds in data_sources.get("dataSource", []):
            data_type = ds.get("dataType", {}).get("name", "")
            if "heart_rate" in data_type:
                data_source_id = ds.get("dataStreamId")

                dataset = service.users().dataSources().datasets().get(
                    userId="me",
                    dataSourceId=data_source_id,
                    datasetId=f"{start_time}-{end_time}"
                ).execute()

                for point in dataset.get("point", []):
                    for value in point.get("value", []):
                        if value.get("fpVal") is not None:
                            heart_rates.append(value.get("fpVal"))

    avg_heart_rate = sum(heart_rates) / len(heart_rates) if heart_rates else 0

    return {
        "google_steps_today": total_steps,
        "google_calories_today": round(total_calories, 2),
        "google_avg_heart_rate": round(avg_heart_rate, 2)
    }