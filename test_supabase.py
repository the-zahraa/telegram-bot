from supabase import create_client, Client
from dotenv import load_dotenv
import os

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    response = supabase.table("users").select("user_id").limit(1).execute()
    print("Connected successfully!")
    print("Users table data:", response.data)
    # Insert a test user
    supabase.table("users").insert({
        "user_id": 12345,
        "balances": {"SOL": 10.0, "LTC": 10.0, "TON": 10.0, "ETH": 10.0}
    }).execute()
    print("Inserted test user")
    response = supabase.table("users").select("*").eq("user_id", 12345).execute()
    print("Test user data:", response.data)
except Exception as e:
    print("Connection failed:", e)