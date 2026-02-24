import pickle
import os

intensity_model = None
calorie_model = None

def load_models():
    global intensity_model, calorie_model
    
    if intensity_model is None:
        model_path = os.path.join(os.path.dirname(__file__), "intensity_model.pkl")
        with open(model_path, "rb") as f:
            intensity_model = pickle.load(f)

    if calorie_model is None:
        model_path = os.path.join(os.path.dirname(__file__), "calorie_model.pkl")
        with open(model_path, "rb") as f:
            calorie_model = pickle.load(f)