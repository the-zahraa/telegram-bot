import logging
import os
from flask import Flask, request
from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler
from telegram import Update
from supabase import create_client, Client
import random
import requests
import asyncio
from logging.handlers import RotatingFileHandler
import hmac
import hashlib
import json

# Set up logging with rotation
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Use /tmp for log file in Vercel
log_file = "/tmp/app.log"
handler = RotatingFileHandler(log_file, maxBytes=1000000, backupCount=1)
handler.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)

# Add console handler for Vercel logs
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Initialize Flask app
app = Flask(__name__)

# Load environment variables
load_dotenv()

# Get sensitive data from environment variables
API_TOKEN = os.getenv("API_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
TATUM_API_KEY = os.getenv("TATUM_API_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # e.g., https://your-vercel-app.vercel.app/tatum

# Validate environment variables
if not all([API_TOKEN, SUPABASE_URL, SUPABASE_KEY, TATUM_API_KEY, WEBHOOK_URL]):
    logger.error("Missing required environment variables")
    raise ValueError("Missing required environment variables")

# Connect to Supabase
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    response = supabase.table("users").select("user_id").limit(1).execute()
    logger.info("Successfully connected to Supabase")
except Exception as e:
    logger.error(f"Failed to connect to Supabase: {str(e)}", exc_info=True)
    raise

# Skip transactions table creation since it's manually created
logger.info("Assuming transactions table exists (manually created)")

# Tatum API base URL (testnet)
TATUM_BASE_URL = "https://api.tatum.io/v3"

# Initialize Telegram bot
try:
    application = Application.builder().token(API_TOKEN).build()
    logger.info("Telegram bot initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize Telegram bot: {str(e)}", exc_info=True)
    raise

# Helper function to verify Tatum webhook signature
def verify_tatum_signature(payload, signature):
    try:
        computed_signature = hmac.new(
            TATUM_API_KEY.encode('utf-8'),
            json.dumps(payload, separators=(',', ':')).encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(computed_signature, signature)
    except Exception as e:
        logger.error(f"Error verifying Tatum signature: {str(e)}", exc_info=True)
        return False

# Helper function to create Tatum webhook subscription for an address
def create_tatum_subscription(address, crypto):
    try:
        chain_map = {
            "SOL": "solana",
            "ETH": "ethereum",
            "LTC": "litecoin",
            "BTC": "bitcoin"
        }
        chain = chain_map.get(crypto)
        if not chain:
            logger.error(f"Unsupported crypto for subscription: {crypto}")
            return False

        headers = {
            "x-api-key": TATUM_API_KEY,
            "Content-Type": "application/json"
        }
        payload = {
            "type": "ADDRESS_TRANSACTION",
            "attr": {
                "address": address,
                "chain": chain,
                "url": WEBHOOK_URL
            }
        }
        response = requests.post(f"{TATUM_BASE_URL}/subscription", json=payload, headers=headers)
        response.raise_for_status()
        logger.info(f"Created Tatum subscription for {crypto} address: {address}")
        return True
    except Exception as e:
        logger.error(f"Failed to create Tatum subscription for {address}: {str(e)}", exc_info=True)
        return False

# Modified generate_deposit_address to include webhook subscription
def generate_deposit_address(crypto):
    try:
        chain_map = {
            "SOL": "solana",
            "ETH": "ethereum",
            "LTC": "litecoin",
            "BTC": "bitcoin"
        }
        chain = chain_map.get(crypto)
        if not chain:
            logger.error(f"Unsupported crypto: {crypto}")
            return None

        headers = {
            "x-api-key": TATUM_API_KEY,
            "Content-Type": "application/json"
        }

        if chain == "solana":
            url = f"{TATUM_BASE_URL}/{chain}/wallet"
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            wallet_data = response.json()
            address = wallet_data.get("address")
            if not address:
                logger.error(f"No address found in wallet response for {crypto}")
                return None
            create_tatum_subscription(address, crypto)
            return address

        url = f"{TATUM_BASE_URL}/{chain}/wallet"
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        wallet_data = response.json()
        xpub = wallet_data.get("xpub")
        if not xpub:
            logger.error(f"No xpub found in wallet response for {crypto}")
            return None

        address_url = f"{TATUM_BASE_URL}/{chain}/address/{xpub}/0"
        address_response = requests.get(address_url, headers=headers)
        address_response.raise_for_status()
        address_data = address_response.json()
        address = address_data["address"]
        create_tatum_subscription(address, crypto)
        return address
    except Exception as e:
        logger.error(f"Failed to generate deposit address for {crypto}: {str(e)}", exc_info=True)
        return None

# Helper function to process a withdrawal (simulated for testnet)
def process_withdrawal(crypto, amount, destination_address):
    try:
        chain_map = {
            "SOL": "solana",
            "ETH": "ethereum",
            "LTC": "litecoin",
            "BTC": "bitcoin"
        }
        chain = chain_map.get(crypto)
        if not chain:
            logger.error(f"Unsupported cryptocurrency: {crypto}")
            return False, "Unsupported cryptocurrency"

        logger.info(f"Simulated withdrawal: {amount} {crypto} to {destination_address}")
        return True, "Withdrawal simulated successfully (testnet)"
    except Exception as e:
        logger.error(f"Failed to process withdrawal for {crypto}: {str(e)}", exc_info=True)
        return False, str(e)

# Command handlers
async def start(update, context):
    try:
        user_id = update.effective_user.id
        logger.info(f"Received /start command from user {user_id}")
        response = supabase.table("users").select("*").eq("user_id", user_id).execute()
        user = response.data[0] if response.data else None
        if not user:
            supabase.table("users").insert({
                "user_id": user_id,
                "balances": {
                    "SOL": 10.0,
                    "LTC": 10.0,
                    "BTC": 0.001,
                    "ETH": 10.0
                },
                "deposit_addresses": {}
            }).execute()
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Welcome to the Casino Bot! You've been registered with 10 units of SOL, LTC, ETH, and 0.001 BTC. Use /help to see available commands."
            )
            logger.info(f"Registered new user: {user_id}")
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Welcome back! Use /help to see available commands."
            )
            logger.info(f"User {user_id} returned")
    except Exception as e:
        logger.error(f"Error in /start command for user {user_id}: {str(e)}", exc_info=True)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Error accessing the database. Please try again later."
        )

async def help_command(update, context):
    try:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Available commands:\n/start - Register or welcome back\n/help - Show this message\n/roll <crypto> <amount> - Roll dice with a bet (e.g., /roll SOL 1)\n/deposit <crypto> - Get deposit address (e.g., /deposit SOL)\n/withdraw <crypto> <amount> <address> - Withdraw funds (e.g., /withdraw SOL 0.1 <address>)\n/balance - Check your balances"
        )
    except Exception as e:
        logger.error(f"Error in /help command: {str(e)}", exc_info=True)

async def balance(update, context):
    try:
        user_id = update.effective_user.id
        response = supabase.table("users").select("balances").eq("user_id", user_id).execute()
        user = response.data[0] if response.data else None
        if not user:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="You’re not registered. Use /start first."
            )
            return

        balances = user['balances']
        balance_text = "Your balances:\n" + "\n".join(f"{crypto}: {amount}" for crypto, amount in balances.items())
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=balance_text
        )
    except Exception as e:
        logger.error(f"Error in /balance command: {str(e)}", exc_info=True)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Error accessing the database. Please try again later."
        )

async def roll(update, context):
    try:
        user_id = update.effective_user.id
        args = context.args

        if len(args) != 2:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Usage: /roll <crypto> <amount>\nExample: /roll SOL 0.1"
            )
            return

        crypto, amount_str = args[0].upper(), args[1]
        valid_cryptos = ['SOL', 'LTC', 'BTC', 'ETH']

        if crypto not in valid_cryptos:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"Invalid cryptocurrency. Use one of: {', '.join(valid_cryptos)}"
            )
            return

        try:
            bet_amount = float(amount_str)
            if bet_amount <= 0:
                raise ValueError
        except ValueError:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Amount must be a positive number (e.g., 0.1)"
            )
            return

        response = supabase.table("users").select("balances").eq("user_id", user_id).execute()
        user = response.data[0] if response.data else None
        if not user:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="You’re not registered. Use /start first."
            )
            return

        current_balance = user['balances'].get(crypto, 0.0)
        if current_balance < bet_amount:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"Insufficient {crypto} balance. Your balance: {current_balance}"
            )
            return

        dice1 = random.randint(1, 6)
        dice2 = random.randint(1, 6)
        total = dice1 + dice2

        if total >= 7:
            winnings = bet_amount * 2
            new_balance = current_balance + bet_amount
            result = f"🎲 You rolled {dice1} + {dice2} = {total}\nYou won! +{winnings} {crypto}"
        else:
            new_balance = current_balance - bet_amount
            result = f"🎲 You rolled {dice1} + {dice2} = {total}\nYou lost! -{bet_amount} {crypto}"

        updated_balances = user['balances'].copy()
        updated_balances[crypto] = new_balance
        supabase.table("users").update({"balances": updated_balances}).eq("user_id", user_id).execute()
        logger.info(f"User {user_id} rolled dice, new {crypto} balance: {new_balance}")

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"{result}\nNew {crypto} balance: {new_balance}"
        )
    except Exception as e:
        logger.error(f"Error in /roll command: {str(e)}", exc_info=True)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Error accessing the database. Please try again later."
        )

async def deposit(update, context):
    try:
        user_id = update.effective_user.id
        args = context.args

        if len(args) != 1:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Usage: /deposit <crypto>\nExample: /deposit SOL"
            )
            return

        crypto = args[0].upper()
        valid_cryptos = ['SOL', 'LTC', 'BTC', 'ETH']

        if crypto not in valid_cryptos:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"Invalid cryptocurrency. Use one of: {', '.join(valid_cryptos)}"
            )
            return

        response = supabase.table("users").select("deposit_addresses").eq("user_id", user_id).execute()
        user = response.data[0] if response.data else None
        if not user:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="You’re not registered. Use /start first."
            )
            return

        deposit_addresses = user['deposit_addresses'] or {}
        if crypto in deposit_addresses:
            address = deposit_addresses[crypto]
        else:
            address = generate_deposit_address(crypto)
            if not address:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"Failed to generate a deposit address for {crypto}. Please try again later."
                )
                return

            deposit_addresses[crypto] = address
            supabase.table("users").update({"deposit_addresses": deposit_addresses}).eq("user_id", user_id).execute()
            logger.info(f"Generated deposit address for user {user_id}: {crypto} - {address}")

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Your {crypto} deposit address (testnet):\n{address}\nSend {crypto} to this address to deposit funds."
        )
    except Exception as e:
        logger.error(f"Error in /deposit command: {str(e)}", exc_info=True)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="An error occurred while generating the deposit address. Please try again later."
        )

async def withdraw(update, context):
    try:
        user_id = update.effective_user.id
        args = context.args

        if len(args) != 3:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Usage: /withdraw <crypto> <amount> <address>\nExample: /withdraw SOL 0.1 <your-address>"
            )
            return

        crypto, amount_str, destination_address = args[0].upper(), args[1], args[2]
        valid_cryptos = ['SOL', 'LTC', 'BTC', 'ETH']

        if crypto not in valid_cryptos:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"Invalid cryptocurrency. Use one of: {', '.join(valid_cryptos)}"
            )
            return

        try:
            amount = float(amount_str)
            if amount <= 0:
                raise ValueError
        except ValueError:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Amount must be a positive number (e.g., 0.1)"
            )
            return

        response = supabase.table("users").select("balances").eq("user_id", user_id).execute()
        user = response.data[0] if response.data else None
        if not user:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="You’re not registered. Use /start first."
            )
            return

        current_balance = user['balances'].get(crypto, 0.0)
        if current_balance < amount:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"Insufficient {crypto} balance. Your balance: {current_balance}"
            )
            return

        success, message = process_withdrawal(crypto, amount, destination_address)
        if not success:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"Withdrawal failed: {message}"
            )
            return

        new_balance = current_balance - amount
        updated_balances = user['balances'].copy()
        updated_balances[crypto] = new_balance
        supabase.table("users").update({"balances": updated_balances}).eq("user_id", user_id).execute()
        logger.info(f"User {user_id} withdrew {amount} {crypto}, new balance: {new_balance}")

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Successfully withdrew {amount} {crypto} to {destination_address}\nNew {crypto} balance: {new_balance}"
        )
    except Exception as e:
        logger.error(f"Error in /withdraw command: {str(e)}", exc_info=True)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="An error occurred while processing the withdrawal. Please try again later."
        )

# Health check route
@app.route('/health')
def health():
    return {"status": "healthy"}, 200

# Test Supabase connection route
@app.route('/test-supabase')
def test_supabase():
    try:
        response = supabase.table("users").select("user_id").limit(1).execute()
        return {"status": "success", "data": response.data}, 200
    except Exception as e:
        logger.error(f"Supabase test failed: {str(e)}", exc_info=True)
        return {"status": "error", "message": str(e)}, 500

# Webhook route for Telegram updates
@app.route('/telegram', methods=['POST'])
def telegram_webhook():
    try:
        update_data = request.get_json()
        if not update_data:
            logger.warning("Received empty update from Telegram")
            return {"status": "error", "message": "Empty update"}, 400

        logger.info(f"Received Telegram update: {update_data}")
        update = Update.de_json(update_data, application.bot)
        if not update:
            logger.warning("Failed to parse Telegram update")
            return {"status": "error", "message": "Invalid update"}, 400

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(application.process_update(update))
        finally:
            loop.close()

        return {"status": "success"}, 200
    except Exception as e:
        logger.error(f"Error in Telegram webhook: {str(e)}", exc_info=True)
        return {"status": "error", "message": str(e)}, 500

# Webhook route for Tatum deposit monitoring
@app.route('/tatum', methods=['POST'])
def tatum_webhook():
    try:
        signature = request.headers.get('x-signature')
        payload = request.get_json()
        if not signature or not payload:
            logger.warning("Missing signature or payload in Tatum webhook")
            return {"status": "error", "message": "Invalid request"}, 400

        if not verify_tatum_signature(payload, signature):
            logger.warning("Invalid Tatum webhook signature")
            return {"status": "error", "message": "Invalid signature"}, 403

        address = payload.get('address')
        amount = float(payload.get('amount', 0))
        currency = payload.get('currency', '').upper()
        tx_id = payload.get('txId')
        confirmations = int(payload.get('confirmations', 0))

        currency_map = {
            "SOLANA": "SOL",
            "ETHEREUM": "ETH",
            "LITECOIN": "LTC",
            "BITCOIN": "BTC"
        }
        crypto = currency_map.get(currency)
        if not crypto:
            logger.warning(f"Unsupported currency in Tatum webhook: {currency}")
            return {"status": "error", "message": "Unsupported currency"}, 400

        confirmation_thresholds = {
            "SOL": 1,
            "ETH": 12,
            "LTC": 6,
            "BTC": 6
        }
        if confirmations < confirmation_thresholds.get(crypto, 1):
            logger.info(f"Transaction {tx_id} for {crypto} has {confirmations} confirmations, waiting for {confirmation_thresholds[crypto]}")
            return {"status": "success", "message": "Waiting for confirmations"}, 200

        response = supabase.table("transactions").select("id").eq("tx_id", tx_id).execute()
        if response.data:
            logger.info(f"Transaction {tx_id} already processed")
            return {"status": "success", "message": "Transaction already processed"}, 200

        response = supabase.table("users").select("user_id, balances").match({"deposit_addresses->>" + crypto: address}).execute()
        user = response.data[0] if response.data else None
        if not user:
            logger.warning(f"No user found for deposit address: {address}")
            return {"status": "error", "message": "User not found"}, 404

        new_balances = user['balances'].copy()
        new_balances[crypto] = new_balances.get(crypto, 0.0) + amount
        supabase.table("users").update({"balances": new_balances}).eq("user_id", user['user_id']).execute()

        supabase.table("transactions").insert({
            "user_id": user['user_id'],
            "type": "deposit",
            "crypto": crypto,
            "amount": amount,
            "address": address,
            "tx_id": tx_id,
            "confirmations": confirmations
        }).execute()

        logger.info(f"Deposited {amount} {crypto} for user {user['user_id']} (tx: {tx_id})")

        # Run async send_message in a synchronous context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(
                application.bot.send_message(
                    chat_id=user['user_id'],
                    text=f"Deposit confirmed: {amount} {crypto} received!\nNew {crypto} balance: {new_balances[crypto]}"
                )
            )
        finally:
            loop.close()

        return {"status": "success"}, 200
    except Exception as e:
        logger.error(f"Error in Tatum webhook: {str(e)}", exc_info=True)
        return {"status": "error", "message": str(e)}, 500

# Set up command handlers
application.add_handler(CommandHandler('start', start))
application.add_handler(CommandHandler('help', help_command))
application.add_handler(CommandHandler('balance', balance))
application.add_handler(CommandHandler('roll', roll))
application.add_handler(CommandHandler('deposit', deposit))
application.add_handler(CommandHandler('withdraw', withdraw))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))