


import os
import requests
import json
from fastapi import APIRouter, HTTPException
from app.redis_client import redis_db
from dotenv import load_dotenv

load_dotenv()
# You will need to get this from Google Cloud Platform
GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY") 

router = APIRouter(
    prefix="/api/v1/market",
    tags=["Market Intelligence"]
)

@router.get("/rising-businesses")
def get_rising_businesses(city: str = "Douala", industry: str = "startup"):
    """
    Fetches real businesses from Google Maps, filters for highly rated ones, 
    and caches the results for 24 hours to save API costs.
    """
    cache_key = f"market_radar_{city.lower()}_{industry.lower()}"

    # 1. Check Redis Cache First (Super Fast & Free)
    if redis_db:
        cached_data = redis_db.get(cache_key)
        if cached_data:
            return {"status": "Success", "source": "cache", "data": json.loads(cached_data)}

    # 2. If not in cache, call Google Places API
    if not GOOGLE_PLACES_API_KEY:
        raise HTTPException(status_code=500, detail="Google API Key missing.")

    # We use Google's "Text Search" endpoint
    query = f"top {industry} businesses in {city} Cameroon"
    url = f"https://maps.googleapis.com/maps/api/place/textsearch/json?query={query}&key={GOOGLE_PLACES_API_KEY}"

    try:
        response = requests.get(url)
        data = response.json()

        if data.get("status") != "OK":
            raise HTTPException(status_code=500, detail="Failed to fetch from Google.")

        # 3. Clean and Filter the Data
        rising_businesses = []
        for place in data.get("results", []):
            # We only want businesses with a rating of 4.0+ and at least 5 reviews
            rating = place.get("rating", 0)
            user_ratings_total = place.get("user_ratings_total", 0)
            
            if rating >= 4.0 and user_ratings_total >= 5:
                business = {
                    "name": place.get("name"),
                    "address": place.get("formatted_address"),
                    "rating": rating,
                    "total_reviews": user_ratings_total,
                    "status": place.get("business_status", "OPERATIONAL"),
                    # Google provides photos, but you have to make a separate API call to render them.
                    # We will just pass the reference ID for now.
                    "photo_reference": place.get("photos", [{}])[0].get("photo_reference") if place.get("photos") else None
                }
                rising_businesses.append(business)

        # Sort them by rating (Highest first)
        rising_businesses = sorted(rising_businesses, key=lambda x: x['rating'], reverse=True)

        # Limit to the top 10 to keep the UI clean
        top_10 = rising_businesses[:10]

        # 4. Save to Redis Cache for 24 hours (86400 seconds)
        if redis_db:
            redis_db.setex(cache_key, 86400, json.dumps(top_10))

        return {"status": "Success", "source": "google_api", "data": top_10}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))