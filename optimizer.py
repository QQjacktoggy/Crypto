import os
import sys
import copy
import pandas as pd
import itertools
import logging

# Ensure the parent directory is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import src components
from src.config import config
from src.engine_backtest import BacktestEngine

logging.basicConfig(level=logging.WARNING, format='%(message)s')

def run_simulation(base_capital, tier_margin_pct, leverage, tp_margin_roi, sl_global_cap_pct, rsi_long, rsi_short, bbands_std=2):
    # Temporarily override config parameters
    original_capital = config.BASE_CAPITAL
    original_tier_margin_pct = config.TIER_MARGIN_PCT
    original_leverage = config.LEVERAGE
    original_tp_margin_roi = config.TP_MARGIN_ROI
    original_sl_global_cap_pct = config.SL_GLOBAL_CAP_PCT
    original_rsi_long = config.RSI_LONG_ENTRY
    original_rsi_short = config.RSI_SHORT_ENTRY

    try:
        config.BASE_CAPITAL = base_capital
        config.TIER_MARGIN_PCT = tier_margin_pct
        config.LEVERAGE = leverage
        config.TP_MARGIN_ROI = tp_margin_roi
        config.SL_GLOBAL_CAP_PCT = sl_global_cap_pct
        config.RSI_LONG_ENTRY = rsi_long
        config.RSI_SHORT_ENTRY = rsi_short

        # We need to recreate the engine so it uses the new configs
        engine = BacktestEngine(days=365)

        import logging
        logger = logging.getLogger("src.engine_backtest")
        logger.setLevel(logging.CRITICAL)

        engine.run()

        logger.setLevel(logging.INFO)

        closed_trades = [t for t in engine.trades if t['type'] == 'close']
        wins = [t for t in closed_trades if t['pnl'] > 0]

        win_rate = (len(wins) / len(closed_trades)) * 100 if closed_trades else 0
        total_pnl = sum(t['pnl'] for t in closed_trades)

        return {
            "tier_margin_pct": tier_margin_pct,
            "leverage": leverage,
            "tp_margin_roi": tp_margin_roi,
            "sl_cap": sl_global_cap_pct,
            "rsi": f"{rsi_long}/{rsi_short}",
            "net_pnl": total_pnl,
            "mdd_pct": engine.max_drawdown * 100,
            "win_rate": win_rate,
            "trades": len(closed_trades)
        }

    finally:
        # Restore configs
        config.BASE_CAPITAL = original_capital
        config.TIER_MARGIN_PCT = original_tier_margin_pct
        config.LEVERAGE = original_leverage
        config.TP_MARGIN_ROI = original_tp_margin_roi
        config.SL_GLOBAL_CAP_PCT = original_sl_global_cap_pct
        config.RSI_LONG_ENTRY = original_rsi_long
        config.RSI_SHORT_ENTRY = original_rsi_short

def main():
    print("Starting parameter optimization for 6-month (180 days) target of 450U Net Profit...")
    base_capital = 150.0

    # Grid search parameters
    # TIER_MARGIN_PCT: Current is 0.066. We can try 0.08, 0.10, 0.12
    tier_margin_pcts = [0.08, 0.10, 0.12]
    # LEVERAGE: Current is 5. We can try 5, 8, 10
    leverages = [5, 8, 10]
    # TP_MARGIN_ROI: Current is 0.15. We can try 0.15, 0.20, 0.25
    tp_margin_rois = [0.15, 0.20, 0.25]
    # SL_GLOBAL_CAP_PCT: Current is -0.08. We can try -0.08, -0.10, -0.15
    sl_global_caps = [-0.10, -0.15, -0.20]
    # RSI ENTRY: Current is 25/75. We can try 25/75, 30/70
    rsi_entries = [(25, 75), (30, 70)]

    results = []

    # Pre-calculate data frames instead of letting engine read from csv every time
    # This optimization skips the I/O for each combination
    from src.engine_backtest import BacktestEngine
    import ccxt
    dummy_engine = BacktestEngine(days=180)

    # We load it manually here to pass to the engine later or just let the engine use cache.
    # The caching in engine_backtest.py uses pd.read_csv which should be fast enough,
    # but we can reduce combinations to run it faster.

    # 365 Days Grid search parameters
    # Focusing on safer margin % and tighter global caps to survive 1-year swings
    tier_margin_pcts = [0.03]
    leverages = [4]
    tp_margin_rois = [0.10, 0.15]
    sl_global_caps = [-0.10, -0.15]
    rsi_entries = [(25, 75)]

    # Calculate total combinations
    total_combs = len(tier_margin_pcts) * len(leverages) * len(tp_margin_rois) * len(sl_global_caps) * len(rsi_entries)
    print(f"Total combinations to test: {total_combs}")

    count = 0
    for tm_pct, lev, tp_roi, sl_cap, rsi in itertools.product(tier_margin_pcts, leverages, tp_margin_rois, sl_global_caps, rsi_entries):
        count += 1
        print(f"[{count}/{total_combs}] Testing TM_PCT={tm_pct}, LEV={lev}, TP={tp_roi}, SL={sl_cap}, RSI={rsi[0]}/{rsi[1]}...")

        res = run_simulation(base_capital, tm_pct, lev, tp_roi, sl_cap, rsi[0], rsi[1])
        results.append(res)

        # Write constantly to see progress
        pd.DataFrame(results).to_csv("optimization_results_partial.csv", index=False)

    df_results = pd.DataFrame(results)
    df_results = df_results.sort_values(by="net_pnl", ascending=False)

    print("\n--- OPTIMIZATION RESULTS ---")
    print(df_results.head(15).to_string(index=False))

    df_results.to_csv("optimization_results.csv", index=False)
    print("\nFull results saved to optimization_results.csv")

if __name__ == "__main__":
    main()
