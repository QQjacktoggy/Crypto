import argparse
import sys
import logging
import ccxt
import os
from dotenv import load_dotenv

# Set up basic logging for the verification script
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("EnvVerifier")

def verify_environment(use_testnet):
    load_dotenv()

    api_key = os.getenv('API_KEY', '')
    api_secret = os.getenv('API_SECRET', '')

    logger.info("--- Starting Environment Verification ---")

    if not api_key or not api_secret:
        logger.error("API_KEY or API_SECRET is missing in the environment variables.")
        logger.info("Please make sure you have created a .env file with API_KEY and API_SECRET.")
        sys.exit(1)
    else:
        logger.info("✅ API Key and Secret found in environment variables.")

    mode_str = "Testnet" if use_testnet else "Live (Mainnet)"
    logger.info(f"Connecting to Binance Futures - {mode_str}...")

    try:
        exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future'  # Ensure we are testing Futures
            }
        })

        if use_testnet:
            exchange.set_sandbox_mode(True)

    except Exception as e:
        logger.error(f"Failed to initialize CCXT client: {e}")
        sys.exit(1)

    logger.info("Testing connection by loading markets...")
    try:
        markets = exchange.load_markets()
        if markets:
            logger.info(f"✅ Successfully loaded {len(markets)} markets.")
        else:
            logger.warning("Markets loaded but returned empty.")
    except Exception as e:
        logger.error(f"❌ Failed to load markets. Connection error: {e}")
        sys.exit(1)

    logger.info("Testing authentication by fetching account balance...")
    try:
        balance = exchange.fetch_balance()
        usdt_balance = balance.get('USDT', {}).get('free', 0.0)
        logger.info(f"✅ Successfully authenticated! Current USDT free balance: {usdt_balance}")
        logger.info("Note: If the balance is 0, ensure you have transferred funds to your Futures account.")
    except ccxt.AuthenticationError as e:
        logger.error(f"❌ Authentication failed. Please check your API Key and Secret. Details: {e}")
        sys.exit(1)
    except ccxt.ExchangeError as e:
        logger.error(f"❌ Exchange error. Your API key might not have Futures trading enabled or IP is restricted. Details: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Failed to fetch balance: {e}")
        sys.exit(1)

    logger.info("--- Environment Verification Completed Successfully ---")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify Binance API connection and credentials")
    parser.add_argument('--testnet', action='store_true', help="Verify using Binance Testnet instead of Binance Mainnet")
    args = parser.parse_args()

    verify_environment(args.testnet)
