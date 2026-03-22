import pytest
from app.services.ml_service import run_predictions, load_models

# 1. SETUP: Wake up the ML models
@pytest.fixture(autouse=True)
def setup_test_environment():
    print("\nLoading models for testing...")
    load_models()

# 2. TEST CASE 1: Standard SME Profile
def test_ml_prediction_standard_business():
    """Test if the AI correctly analyzes a standard Retail business."""
    mock_business_data = {
        "region": "Littoral",
        "sector": "Formal",
        "industry": "Retail",
        "startup_capital_cfa": 5000000,
        "employees": 5,
        "years_of_experience": 4,
        "transport_cost_percentage": 10.0,
        "energy_cost_percentage": 5.0
    }
    
    result = run_predictions(mock_business_data)
    
    assert "survival_probability" in result
    assert "projected_profit_cfa" in result
    assert "risk_level" in result
    assert 0.0 <= result["survival_probability"] <= 1.0
    assert isinstance(result["projected_profit_cfa"], (float, int))

# 3. TEST CASE 2: High-Risk SME Profile
def test_ml_prediction_high_risk_business():
    """Test if the AI correctly flags a business with dangerous overhead costs."""
    high_risk_data = {
        "region": "North West",
        "sector": "Informal",
        "industry": "Agriculture",
        "startup_capital_cfa": 500000, # Very low capital
        "employees": 10,               # Too many employees for the capital
        "years_of_experience": 0,      # No experience
        "transport_cost_percentage": 45.0, # Dangerously high overhead
        "energy_cost_percentage": 30.0     # Dangerously high overhead
    }
    
    result = run_predictions(high_risk_data)
    
    # We expect the AI to flag this as High Risk
    assert result["risk_level"] == "High Risk of Failure"
    assert result["survival_probability"] < 0.60

# 4. TEST CASE 3: Edge Case (Missing or Extreme Data)
def test_ml_prediction_extreme_data():
    """Test if the models survive bizarre inputs (like 0 capital)."""
    extreme_data = {
        "region": "Littoral",
        "sector": "Informal",
        "industry": "Technology",
        "startup_capital_cfa": 0, 
        "employees": 0,               
        "years_of_experience": 0,      
        "transport_cost_percentage": 0.0, 
        "energy_cost_percentage": 0.0     
    }
    
    # The goal here is just to make sure it doesn't throw a Python Exception/Crash
    result = run_predictions(extreme_data)
    assert result["survival_probability"] is not None