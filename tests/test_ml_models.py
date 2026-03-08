

import pytest
from app.services.ml_service import run_predictions, load_models

# 1. SETUP: This fixture ensures the models wake up before the tests run
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
    
    # Run the models
    result = run_predictions(mock_business_data)
    
    # Assertions (If any of these are False, the test fails and warns us!)
    assert "survival_probability" in result
    assert "projected_profit_cfa" in result
    assert "risk_level" in result
    
    # Ensure probabilities are mathematically valid (between 0% and 100%)
    assert 0.0 <= result["survival_probability"] <= 1.0
    
    # Ensure profit is a number (float or int)
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
    
    # We expect the AI to flag this as High Risk based on our 60% threshold
    assert result["risk_level"] == "High Risk of Failure"
    assert result["survival_probability"] < 0.60