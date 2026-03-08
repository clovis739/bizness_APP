

# app/limiter.py
from slowapi import Limiter
from slowapi.util import get_remote_address

# ==========================================
# RATE LIMITER CONFIGURATION
# ==========================================
# We initialize the Limiter here. 
# 'get_remote_address' tells SlowAPI to track users by their IP Address.
limiter = Limiter(key_func=get_remote_address)