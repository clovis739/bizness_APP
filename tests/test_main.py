

from fastapi.testclient import TestClient
from main import app

# This creates a fake browser to test our app
client = TestClient(app)

def test_server_is_awake():
    """Test Case 1: Is the server running?"""
    response = client.get("/")
    assert response.status_code == 200
    assert "✅" in response.json()["message"]

def test_google_auth_url():
    """Test Case 2: Does the Google Auth endpoint work?"""
    response = client.get("/api/v1/communication/auth/google/url")
    assert response.status_code == 200
    assert "url" in response.json()