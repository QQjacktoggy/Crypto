import argparse
import sys
import logging
from src.engine_live import LiveEngine
from src.engine_backtest import BacktestEngine

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description="Crypto Quant Bot - Multi-Tier DCA Strategy")
    parser.add_argument('--mode', type=str, required=True, choices=['live', 'backtest'],
                        help="Execution mode: 'live' or 'backtest'")
    parser.add_argument('--symbol', type=str, default='BTC/USDT',
                        help="Symbol to backtest (only used in backtest mode)")
    parser.add_argument('--days', type=int, default=365,
                        help="Number of days to backtest (only used in backtest mode)")
    parser.add_argument('--testnet', action='store_true',
                        help="Use testnet for live mode")

    args = parser.parse_args()

    if args.mode == 'live':
        logger.info("Initializing Live Trading Engine...")
        engine = LiveEngine(use_testnet=args.testnet)
        try:
            engine.start(poll_interval=60)
        except KeyboardInterrupt:
            logger.info("Live engine stopped by user.")
            sys.exit(0)
    elif args.mode == 'backtest':
        logger.info(f"Initializing Backtest Engine for {args.symbol} over {args.days} days...")
        engine = BacktestEngine(symbol=args.symbol, days=args.days)
        engine.run()

if __name__ == "__main__":
    main()
