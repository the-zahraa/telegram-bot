import logging
import os
from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler
from supabase import create_client, Client
import random
import requests

# Set up logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Get sensitive data from environment variables
API_TOKEN = os.getenv("API_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
TATUM_API_KEY = os.getenv("TATUM_API_KEY")

# Validate environment variables
if not all([API_TOKEN, SUPABASE_URL, SUPABASE_KEY, TATUM_API_KEY]):
    logger.error("Missing API_TOKEN, SUPABASE_URL, SUPABASE_KEY, or TATUM_API_KEY in .env file")
    raise ValueError("Missing required environment variables")

# Connect to Supabase
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    response = supabase.table("users").select("user_id").limit(1).execute()
    logger.info("Successfully connected to Supabase")
except Exception as e:
    logger.error(f"Failed to connect to Supabase: {e}")
    raise

# Tatum API base URL (testnet)
TATUM_BASE_URL = "https://api.tatum.io/v3"

# Helper function to generate a deposit address using Tatum
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

        # Generate a wallet
        headers = {
            "x-api-key": TATUM_API_KEY,
            "Content-Type": "application/json"
        }

        # For Solana, use the chain-specific endpoint
        if chain == "solana":
            url = f"{TATUM_BASE_URL}/{chain}/wallet"
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            wallet_data = response.json()
            address = wallet_data.get("address")
            if not address:
                logger.error(f"No address found in wallet response for {crypto}")
                return None
            return address

        # For Ethereum, Litecoin, and Bitcoin, derive an address from xpub
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
        return address_data["address"]
    except Exception as e:
        logger.error(f"Failed to generate deposit address for {crypto}: {e}")
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
            return False, "Unsupported cryptocurrency"

        # Simulate withdrawal (Tatum requires a funded wallet for real transactions)
        logger.info(f"Simulated withdrawal: {amount} {crypto} to {destination_address}")
        return True, "Withdrawal simulated successfully (testnet)"
    except Exception as e:
        logger.error(f"Failed to process withdrawal for {crypto}: {e}")
        return False, str(e)

async def start(update, context):
    try:
        user_id = update.effective_user.id
        response = supabase.table("users").select("*").eq("user_id", user_id).execute()
        user = response.data[0] if response.data else None
        if not user:
            supabase.table("users").insert({
                "user_id": user_id,
                "balances": {
                    "SOL": 10.0,
                    "LTC": 10.0,
                    "BTC": 0.001,  # Small initial balance for BTC (testnet)
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
        logger.error(f"Database error in /start: {e}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Error accessing the database. Please try again later."
        )

async def help_command(update, context):
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Available commands:\n/start - Register or welcome back\n/help - Show this message\n/roll <crypto> <amount> - Roll dice with a bet (e.g., /roll SOL 1)\n/deposit <crypto> - Get deposit address (e.g., /deposit SOL)\n/withdraw <crypto> <amount> <address> - Withdraw funds (e.g., /withdraw SOL 0.1 <address>)\n/balance - Check your balances"
    )

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
        logger.error(f"Database error in /balance: {e}")
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
        logger.error(f"Database error in /roll: {e}")
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
        logger.error(f"Error in /deposit: {e}")
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
        logger.error(f"Error in /withdraw: {e}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="An error occurred while processing the withdrawal. Please try again later."
        )

async def error_handler(update, context):
    logger.error(f"Update {update} caused error: {context.error}")
    if update:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="An error occurred. Please try again later."
        )

def main():
    try:
        application = Application.builder().token(API_TOKEN).build()
        application.add_handler(CommandHandler('start', start))
        application.add_handler(CommandHandler('help', help_command))
        application.add_handler(CommandHandler('balance', balance))
        application.add_handler(CommandHandler('roll', roll))
        application.add_handler(CommandHandler('deposit', deposit))
        application.add_handler(CommandHandler('withdraw', withdraw))
        application.add_error_handler(error_handler)
        logger.info("Starting Telegram bot...")
        application.run_polling(allowed_updates=["message", "callback_query"])
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        raise

if __name__ == '__main__':
    main()