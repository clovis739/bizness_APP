

import os
import joblib
import pandas as pd
from fastapi import HTTPException

# ==========================================
# MACHINE LEARNING SERVICE
# ==========================================
# This file is responsible for loading the saved AI models from disk
# and running predictions on new business data.

# 1. Define absolute paths to our saved models
# Using os.path ensures this works perfectly on both Windows and Linux servers
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODELS_DIR = os.path.join(BASE_DIR, "models")

SURVIVAL_MODEL_PATH = os.path.join(MODELS_DIR, "sme_survival_catboost_v1.pkl")
PROFIT_MODEL_PATH = os.path.join(MODELS_DIR, "sme_profit_xgboost_v1.pkl")
FEATURES_PATH = os.path.join(MODELS_DIR, "training_features_v1.pkl")

# 2. Global variables to hold the models in memory
# We load them once when the server starts so we don't waste time reloading them for every user
survival_model = None
profit_model = None
expected_features = None

def load_models():
    """
    Loads the CatBoost model, XGBoost model, and the feature list into memory.
    This function should be called when the FastAPI server boots up.
    """
    global survival_model, profit_model, expected_features
    try:
        print(" Waking up the AI Models...")
        survival_model = joblib.load(SURVIVAL_MODEL_PATH)
        profit_model = joblib.load(PROFIT_MODEL_PATH)
        expected_features = joblib.load(FEATURES_PATH)
        print("✅ AI Models successfully loaded into memory!")
    except Exception as e:
        print(f"❌ Critical Error loading models: {e}")
        # TODO: Add alerting here in the future (e.g., send an email to the Admin if models fail to load)

def run_predictions(business_data: dict) -> dict:
    """
    Takes raw business data from the frontend, engineers the required features,
    and returns the survival probability and projected profit.
    """
    if survival_model is None or profit_model is None:
        raise HTTPException(status_code=500, detail="AI Models are currently offline.")

    try:
        # STEP A: Recreate the Feature Engineering from our Jupyter Notebook
        # The AI expects these exact mathematical combinations!
        
        # 1. Total Overhead Burden
        overhead = business_data['transport_cost_percentage'] + business_data['energy_cost_percentage']
        
        # 2. Capital Per Employee (Safety check to prevent dividing by zero)
        employees = max(1, business_data['employees']) 
        capital_per_emp = business_data['startup_capital_cfa'] / employees
        
        # 3. Risk to Experience Ratio 
        # TODO: In the future, fetch the exact Sector Risk Baseline from a database table.
        # For now, we will assign a mock baseline based on the sector (e.g., Informal = higher baseline risk).
        sector_risk_baseline = 0.7 if business_data['sector'].lower() == 'informal' else 0.4
        risk_ratio = sector_risk_baseline / (business_data['years_of_experience'] + 1)

        # STEP B: Construct the exact dictionary the model expects
        # We must map our backend database names to the column names the model was trained on
        model_input = {
            'Region': business_data['region'],
            'Sector': business_data['sector'],
            'Industry': business_data['industry'],
            'Startup_Capital_CFA': business_data['startup_capital_cfa'],
            'Employees': business_data['employees'],
            'Years_of_Experience': business_data['years_of_experience'],
            'Transport_Cost_Percentage': business_data['transport_cost_percentage'],
            'Energy_Cost_Percentage': business_data['energy_cost_percentage'],
            
            # Add our custom engineered features
            'Total_Overhead_Burden': overhead,
            'Capital_Per_Employee': capital_per_emp,
            'Risk_to_Experience_Ratio': risk_ratio,
            
            # TODO: Add any other missing default columns that the training dataset had.
            # E.g., Business_Age_Years. Since this is a new business registering, Age is 0.
            'Business_Age_Years': 0, 
            'Access_to_Financing': 'No' # Defaulting to No for new startups unless specified
        }

        # Convert the dictionary into a Pandas DataFrame (1 row of data)
        df_input = pd.DataFrame([model_input])

        # Ensure all expected columns are present (fill missing ones with 0 or Unknown to prevent crashes)
        for col in expected_features:
            if col not in df_input.columns:
                df_input[col] = 0  

        # Order the columns EXACTLY as the model expects them
        df_input = df_input[expected_features]

        # STEP C: Run the Survival Model (CatBoost)
        # We use predict_proba()[0][1] to get the exact percentage of survival, rather than just a 0 or 1
        survival_prob = survival_model.predict_proba(df_input)[0][1]
        
        # Apply our custom 60% Strict Advisor Threshold
        risk_level = "Safe (High Survival Chance)" if survival_prob >= 0.60 else "High Risk of Failure"

        # STEP D: Run the Profit Forecast Model (XGBoost)
        # XGBoost returns a list of predictions, we grab the first one [0]
        projected_profit = float(profit_model.predict(df_input)[0])

        # STEP E: Return the comprehensive report
        return {
            "survival_probability": round(survival_prob, 4), # e.g., 0.6543
            "risk_level": risk_level,
            "projected_profit_cfa": round(projected_profit, 2)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction Engine Error: {str(e)}")