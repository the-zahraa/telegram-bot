import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, request
from supabase import create_client

app = Flask(__name__)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
log_file = "/tmp/app.log"
handler = RotatingFileHandler(log_file, maxBytes=1000000, backupCount=1)
handler.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Environment variables
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
if not all([SUPABASE_URL, SUPABASE_KEY]):
    logger.error("Missing Supabase environment variables")
    raise ValueError("Missing Supabase environment variables")

# Connect to Supabase
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
response = supabase.table("users").select("user_id").limit(1).execute()
logger.info("Successfully connected to Supabase")
logger.info("Assuming transactions table exists (manually created)")

@app.route('/health')
def health():
    return {"status": "healthy"}, 200

@app.route('/test-supabase')
def test_supabase():
    try:
        response = supabase.table("users").select("user_id").limit(1).execute()
        return {"status": "success", "data": response.data}, 200
    except Exception as e:
        logger.error(f"Supabase test failed: {str(e)}", exc_info=True)
        return {"status": "error", "message": str(e)}, 500

@app.route('/telegram', methods=['POST'])
def telegram_webhook():
    return {"status": "success", "message": "Webhook placeholder"}, 200