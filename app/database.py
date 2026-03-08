

import os
from dotenv import load_dotenv
from supabase import create_client, Client

# 1. Load the hidden environment variables from the .env file
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Safety check to ensure the keys are actually loaded
if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Supabase credentials are missing in the .env file!")

# 2. Initialize and export the Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)



print(" Database connection initialized.")


def log_audit_action(actor_id: str, actor_type: str, action_type: str, description: str):
    """
    Utility function to record system events in the Audit Log.
    Fire-and-forget: it shouldn't crash the main app if logging fails.
    """
    try:
        log_data = {
            "actor_id": actor_id,
            "actor_type": actor_type,
            "action_type": action_type,
            "description": description
        }
        supabase.table("audit_log").insert(log_data).execute()
        print(f"📝 AUDIT LOG: {actor_type} performed {action_type}")
    except Exception as e:
        print(f"⚠️ Warning: Failed to write to audit log: {e}")
