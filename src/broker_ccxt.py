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
            'options': {
                'defaultType': 'future'  # Force Binance USDT-M Futures
            }
        })
        if use_testnet:
            self.exchange.set_sandbox_mode(True)

        # Cache for market details to handle precision
        self.markets = None

    def set_leverage_and_margin(self, symbol):
        """
        Sets the leverage and margin mode for the symbol on Binance Futures.
        """
        try:
            self.exchange.set_leverage(config.LEVERAGE, symbol)
            self.exchange.set_margin_mode(config.MARGIN_MODE, symbol)
            logger.info(f"Successfully set {config.LEVERAGE}x leverage and {config.MARGIN_MODE} margin for {symbol}.")
        except Exception as e:
            # Often throws exception if leverage/margin mode is already set, which is fine
            logger.debug(f"Note while setting leverage/margin for {symbol}: {e}")

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

    def execute_futures_order(self, symbol: str, margin_usdt: float, side: str, positionSide: str):
        """
        Executes a futures market order.
        margin_usdt: The actual USDT collateral you want to use.
        side: 'buy' or 'sell'
        positionSide: 'LONG' or 'SHORT' (for hedge mode) or usually defaults in one-way mode.
        Since we are in one-way mode for simplicity, we just use side='buy' (to open long/close short)
        and side='sell' (to open short/close long).
        """
        # Ensure leverage is configured on the exchange for this symbol
        self.set_leverage_and_margin(symbol)

        price = self.get_ticker(symbol)
        if not price: return None

        if self.markets is None:
            self.load_markets()

        market = self.markets.get(symbol)
        if not market:
            logger.error(f"Market {symbol} not found.")
            return None

        # Calculate position size: Margin * Leverage
        position_value_usdt = margin_usdt * config.LEVERAGE
        amount = position_value_usdt / price

        # Convert to exchange precision
        amount_precision = self.exchange.amount_to_precision(symbol, amount)
        amount = float(amount_precision)

        try:
            order = self.exchange.create_order(
                symbol=symbol,
                type='market',
                side=side,
                amount=amount
            )

            # The notional value of the trade
            notional_value = amount * price
            fee = notional_value * config.FEE_RATE

            return {
                'order_id': order.get('id'),
                'symbol': symbol,
                'amount': amount,
                'price': price,
                'notional_value': notional_value,
                'margin_used': notional_value / config.LEVERAGE,
                'fee_usdt': fee,
                'status': order.get('status', 'closed')
            }
        except Exception as e:
            logger.error(f"Error executing {side} order for {symbol}: {e}")
            return None

    def execute_close_futures_position(self, symbol: str, amount: float, side: str):
        """
        Closes an existing futures position.
        side: 'buy' to close a short, 'sell' to close a long.
        """
        if self.markets is None:
            self.load_markets()

        amount_precision = self.exchange.amount_to_precision(symbol, amount)
        amount = float(amount_precision)

        try:
            order = self.exchange.create_order(
                symbol=symbol,
                type='market',
                side=side,
                amount=amount,
                params={'reduceOnly': True} # Safe-guard to prevent opening opposite position
            )
            price = self.get_ticker(symbol)
            notional_value = amount * price
            fee = notional_value * config.FEE_RATE
            return {
                'order_id': order.get('id'),
                'symbol': symbol,
                'amount': amount,
                'price': price,
                'notional_value': notional_value,
                'fee_usdt': fee,
                'status': order.get('status', 'closed')
            }
        except Exception as e:
            logger.error(f"Error closing position for {symbol}: {e}")
            return None
