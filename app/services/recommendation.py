def recommend_meal(intensity, calories_burned, goal):
    if goal.lower() == "muscle gain":
        if intensity == "High":
            return "Grilled Chicken with Brown Rice and Vegetables"
        elif intensity == "Medium":
            return "Paneer Wrap with Whole Wheat Roti"
        else:
            return "Protein Smoothie with Banana"

    elif goal.lower() == "weight loss":
        if intensity == "High":
            return "Grilled Fish with Salad"
        elif intensity == "Medium":
            return "Vegetable Stir Fry"
        else:
            return "Fruit Bowl with Nuts"

    else:
        return "Balanced Meal with Protein, Carbs and Vegetables"