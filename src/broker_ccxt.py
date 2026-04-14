import ccxt
import time
import logging
from src.config import config

logger = logging.getLogger(__name__)

class Broker:
    def __init__(self, use_testnet=False):
        exchange_class = getattr(ccxt, config.EXCHANGE_ID)
        self.exchange = exchange_class({
            'apiKey': config.API_KEY,
            'secret': config.API_SECRET,
            'enableRateLimit': True,
        })
        if use_testnet:
            self.exchange.set_sandbox_mode(True)

        # Cache for market details to handle precision
        self.markets = None

    def load_markets(self):
        try:
            self.markets = self.exchange.load_markets()
            return self.markets
        except Exception as e:
            logger.error(f"Error loading markets: {e}")
            return None

    def get_balance(self, currency='USDT'):
        try:
            balance = self.exchange.fetch_balance()
            return balance.get(currency, {}).get('free', 0.0)
        except Exception as e:
            logger.error(f"Error fetching balance: {e}")
            return 0.0

    def get_ticker(self, symbol):
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return ticker['last']
        except ccxt.RateLimitExceeded:
            logger.warning("Rate limit exceeded, sleeping for 2 seconds.")
            time.sleep(2)
            return self.get_ticker(symbol)
        except Exception as e:
            logger.error(f"Error fetching ticker for {symbol}: {e}")
            return None

    def fetch_ohlcv(self, symbol, timeframe=config.TIMEFRAME, limit=100):
        try:
            return self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        except Exception as e:
            logger.error(f"Error fetching OHLCV for {symbol}: {e}")
            return []

    def create_market_buy_order(self, symbol, amount_usdt):
        """
        Calculates the quantity of base currency to buy using amount_usdt.
        """
        price = self.get_ticker(symbol)
        if not price:
            return None

        if self.markets is None:
            self.load_markets()

        market = self.markets.get(symbol)
        if not market:
            logger.error(f"Market {symbol} not found.")
            return None

        # Calculate amount to buy
        amount = amount_usdt / price

        # Convert to exchange precision
        amount = self.exchange.amount_to_precision(symbol, amount)
        amount = float(amount)

        try:
            order = self.exchange.create_order(
                symbol=symbol,
                type='market',
                side='buy',
                amount=amount
            )
            # Estimate fee (this is a rough estimate since actual fee is charged in base currency usually)
            fee = amount_usdt * config.FEE_RATE
            return {
                'order_id': order.get('id'),
                'symbol': symbol,
                'amount': amount,
                'price': price,
                'cost_usdt': amount * price,
                'fee_usdt': fee,
                'status': order.get('status', 'closed')
            }
        except Exception as e:
            logger.error(f"Error executing buy order for {symbol}: {e}")
            return None

    def create_market_sell_order(self, symbol, amount):
        """
        Sells a specific amount of the base currency.
        """
        if self.markets is None:
            self.load_markets()

        amount = self.exchange.amount_to_precision(symbol, amount)
        amount = float(amount)

        try:
            order = self.exchange.create_order(
                symbol=symbol,
                type='market',
                side='sell',
                amount=amount
            )
            price = self.get_ticker(symbol)
            cost_usdt = amount * price
            fee = cost_usdt * config.FEE_RATE
            return {
                'order_id': order.get('id'),
                'symbol': symbol,
                'amount': amount,
                'price': price,
                'cost_usdt': cost_usdt,
                'fee_usdt': fee,
                'status': order.get('status', 'closed')
            }
        except Exception as e:
            logger.error(f"Error executing sell order for {symbol}: {e}")
            return None
