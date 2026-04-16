"""
optimize_phase3_loss_reduction.py - Targeted loss reduction sweep

Goal:
  Start from the best smoother profile (Conservative-5x-structural, +21.63 USDT/year,
  5 losing months) and apply targeted mechanisms to cut bad-month losses further.

Techniques tested:
  1. ATR spike entry block (new feature) — skip new entries when current ATR > N× median
  2. Very strict Momentum-gated DCA (only DCA when market is truly quiet)
  3. Tighter monthly circuit-breaker to cap the worst month (2026-01)
  4. Combinations of the above
"""

import logging
import os
import sys
from datetime import datetime

import pandas as pd

logging.getLogger().setLevel(logging.CRITICAL)

from src.engine_backtest import BacktestEngine
from src.config import config

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ──────────────────────────────────────────────────────────────────────────────
# Base: Conservative-5x-structural (best from phase3 repair sweep)
# ──────────────────────────────────────────────────────────────────────────────
BASE = {
    'DYNAMIC_TPSL': True, 'ATR_TP_MULT': 3.0, 'ATR_SL_MULT': 1.4,
    'ATR_TP_MIN_ROI': 0.12, 'ATR_TP_MAX_ROI': 0.45, 'ATR_SL_MIN_ROI': -0.14, 'ATR_SL_MAX_ROI': -0.50,
    'LEVERAGE': 5, 'TIER_MARGIN_PCT': 0.085, 'SIGNAL_MODE': 'classic',
    'RSI_LONG_ENTRY': 32, 'RSI_SHORT_ENTRY': 68,
    'BB_ENTRY_BUFFER_PCT': 0.008, 'VOLUME_FILTER_MULT': 0.42,
    'VOLATILITY_ADAPTIVE_ENTRY': True, 'ATR_VOL_LOOKBACK': 120,
    'HIGH_VOL_THRESHOLD': 1.25, 'LOW_VOL_THRESHOLD': 0.85,
    'RSI_LONG_ENTRY_HIGH_VOL': 28, 'RSI_LONG_ENTRY_LOW_VOL': 39,
    'RSI_SHORT_ENTRY_HIGH_VOL': 72, 'RSI_SHORT_ENTRY_LOW_VOL': 61,
    'DYNAMIC_TIER_DEVIATIONS': True, 'TIER_2_ATR_DEV_MULT': 1.2, 'TIER_3_ATR_DEV_MULT': 1.9, 'MIN_TIER_DEV_PCT': 0.0030,
    'MOMENTUM_GATED_DCA': True, 'TIER_2_MAX_ATR_RATIO': 2.0, 'TIER_3_MAX_ATR_RATIO': 1.7,
    'TIER_2_LONG_RSI_MAX': 40, 'TIER_2_SHORT_RSI_MIN': 60, 'TIER_3_LONG_RSI_RECOVERY': 35, 'TIER_3_SHORT_RSI_RECOVERY': 65,
    'ENABLE_MONTHLY_CIRCUIT_BREAKER': True, 'MONTHLY_LOSS_LIMIT_PCT': -0.30, 'MAX_CONSECUTIVE_LOSSES': 5,
    'TRAILING_TP_ACTIVATE_ROI': 0.12, 'TRAILING_TP_CALLBACK_ROI': 0.04,
    'TIER_2_DEV_PCT': 0.010, 'TIER_3_DEV_PCT': 0.018, 'SL_GLOBAL_CAP_PCT': -0.08,
    'TP_MARGIN_ROI': 0.18, 'SL_MARGIN_ROI': -0.45,
    'ENABLE_ATR_SPIKE_BLOCK': False, 'ATR_SPIKE_BLOCK_THRESHOLD': 2.0,
}


PARAM_SETS = [
    {'label': 'Base-conservative-5x', **BASE},
    {
        'label': 'Base+spike-block-2.0',
        **BASE,
        'ENABLE_ATR_SPIKE_BLOCK': True, 'ATR_SPIKE_BLOCK_THRESHOLD': 2.0,
    },
    {
        'label': 'Base+spike-block-1.8',
        **BASE,
        'ENABLE_ATR_SPIKE_BLOCK': True, 'ATR_SPIKE_BLOCK_THRESHOLD': 1.8,
    },
    {
        'label': 'Base+spike-block-1.6',
        **BASE,
        'ENABLE_ATR_SPIKE_BLOCK': True, 'ATR_SPIKE_BLOCK_THRESHOLD': 1.6,
    },
    {
        # Strict DCA gating — only DCA when ATR is very close to normal
        'label': 'Base+strict-DCA-gate',
        **BASE,
        'TIER_2_MAX_ATR_RATIO': 1.4, 'TIER_3_MAX_ATR_RATIO': 1.2,
        'TIER_2_LONG_RSI_MAX': 37, 'TIER_2_SHORT_RSI_MIN': 63,
        'TIER_3_LONG_RSI_RECOVERY': 33, 'TIER_3_SHORT_RSI_RECOVERY': 67,
    },
    {
        # Tighter monthly circuit breaker to cap 2026-01
        'label': 'Base+breaker-0.18',
        **BASE,
        'MONTHLY_LOSS_LIMIT_PCT': -0.18,
    },
    {
        # Spike block + strict DCA
        'label': 'Base+spike-1.8+strict-DCA',
        **BASE,
        'ENABLE_ATR_SPIKE_BLOCK': True, 'ATR_SPIKE_BLOCK_THRESHOLD': 1.8,
        'TIER_2_MAX_ATR_RATIO': 1.4, 'TIER_3_MAX_ATR_RATIO': 1.2,
        'TIER_2_LONG_RSI_MAX': 37, 'TIER_2_SHORT_RSI_MIN': 63,
        'TIER_3_LONG_RSI_RECOVERY': 33, 'TIER_3_SHORT_RSI_RECOVERY': 67,
    },
    {
        # Spike block + tighter breaker
        'label': 'Base+spike-1.8+breaker-0.20',
        **BASE,
        'ENABLE_ATR_SPIKE_BLOCK': True, 'ATR_SPIKE_BLOCK_THRESHOLD': 1.8,
        'MONTHLY_LOSS_LIMIT_PCT': -0.20,
    },
    {
        # Full combination: spike block + strict DCA + tighter breaker
        'label': 'Full-combo-spike-1.8',
        **BASE,
        'ENABLE_ATR_SPIKE_BLOCK': True, 'ATR_SPIKE_BLOCK_THRESHOLD': 1.8,
        'TIER_2_MAX_ATR_RATIO': 1.4, 'TIER_3_MAX_ATR_RATIO': 1.2,
        'TIER_2_LONG_RSI_MAX': 37, 'TIER_2_SHORT_RSI_MIN': 63,
        'TIER_3_LONG_RSI_RECOVERY': 33, 'TIER_3_SHORT_RSI_RECOVERY': 67,
        'MONTHLY_LOSS_LIMIT_PCT': -0.22, 'MAX_CONSECUTIVE_LOSSES': 4,
    },
    {
        # Full combination with tighter spike block threshold
        'label': 'Full-combo-spike-1.6',
        **BASE,
        'ENABLE_ATR_SPIKE_BLOCK': True, 'ATR_SPIKE_BLOCK_THRESHOLD': 1.6,
        'TIER_2_MAX_ATR_RATIO': 1.3, 'TIER_3_MAX_ATR_RATIO': 1.1,
        'TIER_2_LONG_RSI_MAX': 37, 'TIER_2_SHORT_RSI_MIN': 63,
        'TIER_3_LONG_RSI_RECOVERY': 33, 'TIER_3_SHORT_RSI_RECOVERY': 67,
        'MONTHLY_LOSS_LIMIT_PCT': -0.20, 'MAX_CONSECUTIVE_LOSSES': 4,
        # Tighten ATR TP/SL for faster exits in volatile periods
        'ATR_SL_MULT': 1.3, 'ATR_SL_MIN_ROI': -0.12,
    },
]


def run_single_iteration(iteration_num, params, days=365):
    try:
        full_params = {
            'EMA_FAST': config.EMA_FAST,
            'EMA_SLOW': config.EMA_SLOW,
            'MACD_FAST': config.MACD_FAST,
            'MACD_SLOW': config.MACD_SLOW,
            'MACD_SIGNAL': config.MACD_SIGNAL,
            'TREND_SMA_LENGTH': config.TREND_SMA_LENGTH,
            'FUNDING_RATE': config.FUNDING_RATE,
            'FUNDING_INTERVAL_HOURS': config.FUNDING_INTERVAL_HOURS,
            'FEE_RATE': config.FEE_RATE,
            'COMPOUND_MODE': config.COMPOUND_MODE,
            'BASE_CAPITAL': config.BASE_CAPITAL,
            'MAX_ACTIVE_TRADES': config.MAX_ACTIVE_TRADES,
            'COOLDOWN_CANDLES': config.COOLDOWN_CANDLES,
            'MONTHLY_LOSS_LIMIT_PCT': config.MONTHLY_LOSS_LIMIT_PCT,
        }
        full_params.update(params)

        engine = BacktestEngine(days=days, param_overrides=full_params)
        if not engine.run():
            raise RuntimeError(f"No historical data available for {days}d window")

        closed_trades = [t for t in engine.trades if t['type'] == 'close']
        total_pnl = sum(t['pnl'] for t in closed_trades)

        monthly_data = engine.get_monthly_pnl_report()
        monthly_losses = [m for m in monthly_data if m['net_pnl'] < 0]
        worst_month = min((m['net_pnl'] for m in monthly_data), default=0)
        worst_loss_sum = sum(m['net_pnl'] for m in monthly_losses)

        losing_month_symbols = []
        if closed_trades and monthly_losses:
            df = pd.DataFrame(closed_trades)
            df['time'] = pd.to_datetime(df['time'])
            df['month'] = df['time'].dt.to_period('M')
            by_symbol = df.groupby(['month', 'symbol']).agg(
                trades=('pnl', 'size'),
                wins=('pnl', lambda s: (s > 0).sum()),
                losses=('pnl', lambda s: (s <= 0).sum()),
                pnl=('pnl', 'sum'),
            ).reset_index()
            losing_month_set = {m['month'] for m in monthly_losses}
            losing_month_symbols = by_symbol[
                by_symbol['month'].astype(str).isin(losing_month_set)
            ].sort_values(['month', 'pnl']).to_dict('records')

        return {
            'iteration': iteration_num,
            'label': params['label'],
            'params': params,
            'final_balance': engine.current_balance,
            'total_pnl': total_pnl,
            'total_trades': len(closed_trades),
            'win_rate': (sum(1 for t in closed_trades if t['pnl'] > 0) / len(closed_trades) * 100) if closed_trades else 0,
            'max_drawdown': engine.max_drawdown * 100,
            'monthly_data': monthly_data,
            'losing_months': monthly_losses,
            'losing_month_count': len(monthly_losses),
            'worst_month': worst_month,
            'worst_loss_sum': worst_loss_sum,
            'losing_month_symbols': losing_month_symbols,
        }
    except Exception as e:
        return {
            'iteration': iteration_num,
            'label': params['label'],
            'params': params,
            'error': str(e),
            'final_balance': 0,
            'total_pnl': 0,
            'total_trades': 0,
            'win_rate': 0,
            'max_drawdown': 100,
            'monthly_data': [],
            'losing_months': [],
            'losing_month_count': 0,
            'worst_month': 0,
            'worst_loss_sum': 0,
            'losing_month_symbols': [],
        }


def save_results(results, filename=None):
    if filename is None:
        filename = os.path.join(BASE_DIR, "optimization_phase3_loss_reduction.txt")
    with open(filename, "w", encoding="utf-8") as f:
        f.write("Phase 3 Targeted Loss Reduction Report\n")
        f.write(f"Generated: {datetime.now():%Y-%m-%d %H:%M:%S}\n")
        f.write("Goal: reduce bad-month losses relative to Conservative-5x base (+21.63 USDT/year)\n")
        f.write("New feature: ENABLE_ATR_SPIKE_BLOCK blocks new entries when ATR > N× median\n")
        f.write("=" * 72 + "\n\n")
        for result in results:
            f.write(f"Iteration #{result['iteration']} | {result['label']}\n")
            if 'error' in result:
                f.write(f"  ERROR: {result['error']}\n\n")
                continue
            params = result['params']
            f.write(
                f"  PnL={result['total_pnl']:+.2f} | Final={result['final_balance']:.2f} | "
                f"WR={result['win_rate']:.1f}% | DD={result['max_drawdown']:.1f}% | "
                f"Trades={result['total_trades']} | LosingMonths={result['losing_month_count']} | "
                f"WorstMonth={result['worst_month']:+.2f} | SumLoss={result['worst_loss_sum']:+.2f}\n"
            )
            f.write(
                f"  SpikeBlock={params.get('ENABLE_ATR_SPIKE_BLOCK', False)} "
                f"Threshold={params.get('ATR_SPIKE_BLOCK_THRESHOLD', '-')} "
                f"T2-ATR-max={params.get('TIER_2_MAX_ATR_RATIO', '-')} "
                f"T3-ATR-max={params.get('TIER_3_MAX_ATR_RATIO', '-')} "
                f"Breaker={params.get('MONTHLY_LOSS_LIMIT_PCT', '-')}\n"
            )
            if result['losing_months']:
                loss_summary = ", ".join(
                    f"{m['month']}({m['net_pnl']:+.2f})" for m in result['losing_months']
                )
                f.write(f"  Losing months: {loss_summary}\n")
            f.write("\n")


def main():
    print("=" * 72)
    print("🎯 PHASE 3 TARGETED LOSS REDUCTION SWEEP")
    print("=" * 72)
    print(f"Initial Capital: {config.BASE_CAPITAL} USDT")
    print("Base: Conservative-5x-structural (+21.63 USDT/year, 5 losing months)")
    print("Focus: ATR spike block + strict DCA gating + tighter monthly breaker")
    print("=" * 72)

    all_results = []
    total = len(PARAM_SETS)
    for i, params in enumerate(PARAM_SETS, start=1):
        sys.stdout.write(f"\r⏳ Running iteration {i}/{total}...")
        sys.stdout.flush()
        result = run_single_iteration(i, params)
        all_results.append(result)
        if 'error' in result:
            sys.stdout.write(f"\r❌ Iteration {i}/{total} | ERROR: {result['error']}\n")
        else:
            sys.stdout.write(
                f"\r✅ Iteration {i}/{total} | PnL: {result['total_pnl']:+.2f} | "
                f"LosingMonths: {result['losing_month_count']} | WorstMonth: {result['worst_month']:+.2f}\n"
            )

    valid = [r for r in all_results if 'error' not in r]
    # Primary sort: highest PnL while also having few losing months
    valid.sort(key=lambda r: (r['total_pnl'], -r['losing_month_count'], -r['worst_month']), reverse=True)

    if valid:
        print("\n" + "=" * 72)
        print("🏆 LOSS REDUCTION RANKING (by PnL, then fewest losing months)")
        print("=" * 72)
        for rank, result in enumerate(valid, start=1):
            marker = " ⭐ BEST" if rank == 1 else ""
            print(
                f"#{rank} Iter {result['iteration']} [{result['label']}]{marker} | "
                f"PnL {result['total_pnl']:+.2f} | LosingMonths {result['losing_month_count']} | "
                f"WorstMonth {result['worst_month']:+.2f} | SumLoss {result['worst_loss_sum']:+.2f} | "
                f"DD {result['max_drawdown']:.1f}%"
            )

    save_results(all_results)
    output_file = os.path.join(BASE_DIR, "optimization_phase3_loss_reduction.txt")
    print(f"\n📄 Results saved to: {output_file}")


if __name__ == "__main__":
    main()
