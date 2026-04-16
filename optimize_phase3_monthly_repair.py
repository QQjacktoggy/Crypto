"""
optimize_phase3_monthly_repair.py - Phase 3 monthly loss analysis and repair

Goal:
1. Start from the current phase-3 best setup.
2. Identify which months and symbols drive the losses.
3. Try month-focused hardening variants using features that already exist in the engine.
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


PHASE3_BASELINE = {
    'DYNAMIC_TPSL': True, 'ATR_TP_MULT': 3.0, 'ATR_SL_MULT': 1.4,
    'ATR_TP_MIN_ROI': 0.12, 'ATR_TP_MAX_ROI': 0.45, 'ATR_SL_MIN_ROI': -0.14, 'ATR_SL_MAX_ROI': -0.50,
    'LEVERAGE': 7, 'TIER_MARGIN_PCT': 0.090, 'SIGNAL_MODE': 'classic',
    'RSI_LONG_ENTRY': 33, 'RSI_SHORT_ENTRY': 67, 'BB_ENTRY_BUFFER_PCT': 0.006, 'VOLUME_FILTER_MULT': 0.45,
    'DYNAMIC_TIER_DEVIATIONS': True, 'TIER_2_ATR_DEV_MULT': 1.1, 'TIER_3_ATR_DEV_MULT': 1.8, 'MIN_TIER_DEV_PCT': 0.0025,
    'ENABLE_MONTHLY_CIRCUIT_BREAKER': True, 'MONTHLY_LOSS_LIMIT_PCT': -0.35, 'MAX_CONSECUTIVE_LOSSES': 5,
    'TRAILING_TP_ACTIVATE_ROI': 0.15, 'TRAILING_TP_CALLBACK_ROI': 0.05,
    'TIER_2_DEV_PCT': 0.008, 'TIER_3_DEV_PCT': 0.015, 'SL_GLOBAL_CAP_PCT': -0.12,
    'TP_MARGIN_ROI': 0.20, 'SL_MARGIN_ROI': -0.55,
}


PARAM_SETS = [
    {'label': 'Control', **PHASE3_BASELINE},
    {
        'label': 'VolAdapt+DCAgate-moderate',
        **PHASE3_BASELINE,
        'VOLATILITY_ADAPTIVE_ENTRY': True, 'ATR_VOL_LOOKBACK': 96, 'HIGH_VOL_THRESHOLD': 1.20, 'LOW_VOL_THRESHOLD': 0.85,
        'RSI_LONG_ENTRY_HIGH_VOL': 30, 'RSI_LONG_ENTRY_LOW_VOL': 38, 'RSI_SHORT_ENTRY_HIGH_VOL': 70, 'RSI_SHORT_ENTRY_LOW_VOL': 62,
        'MOMENTUM_GATED_DCA': True, 'TIER_2_MAX_ATR_RATIO': 1.85, 'TIER_3_MAX_ATR_RATIO': 1.55,
        'TIER_2_LONG_RSI_MAX': 39, 'TIER_2_SHORT_RSI_MIN': 61, 'TIER_3_LONG_RSI_RECOVERY': 34, 'TIER_3_SHORT_RSI_RECOVERY': 66,
    },
    {
        'label': 'VolAdapt+DCAgate+tighter-breaker',
        **PHASE3_BASELINE,
        'VOLATILITY_ADAPTIVE_ENTRY': True, 'ATR_VOL_LOOKBACK': 96, 'HIGH_VOL_THRESHOLD': 1.20, 'LOW_VOL_THRESHOLD': 0.85,
        'RSI_LONG_ENTRY_HIGH_VOL': 30, 'RSI_LONG_ENTRY_LOW_VOL': 38, 'RSI_SHORT_ENTRY_HIGH_VOL': 70, 'RSI_SHORT_ENTRY_LOW_VOL': 62,
        'MOMENTUM_GATED_DCA': True, 'TIER_2_MAX_ATR_RATIO': 1.80, 'TIER_3_MAX_ATR_RATIO': 1.50,
        'TIER_2_LONG_RSI_MAX': 39, 'TIER_2_SHORT_RSI_MIN': 61, 'TIER_3_LONG_RSI_RECOVERY': 34, 'TIER_3_SHORT_RSI_RECOVERY': 66,
        'MONTHLY_LOSS_LIMIT_PCT': -0.25, 'MAX_CONSECUTIVE_LOSSES': 4,
    },
    {
        'label': 'VolAdapt+DCAgate+risk-trim',
        **PHASE3_BASELINE,
        'VOLATILITY_ADAPTIVE_ENTRY': True, 'ATR_VOL_LOOKBACK': 120, 'HIGH_VOL_THRESHOLD': 1.25, 'LOW_VOL_THRESHOLD': 0.90,
        'RSI_LONG_ENTRY_HIGH_VOL': 29, 'RSI_LONG_ENTRY_LOW_VOL': 39, 'RSI_SHORT_ENTRY_HIGH_VOL': 71, 'RSI_SHORT_ENTRY_LOW_VOL': 61,
        'MOMENTUM_GATED_DCA': True, 'TIER_2_MAX_ATR_RATIO': 1.75, 'TIER_3_MAX_ATR_RATIO': 1.45,
        'TIER_2_LONG_RSI_MAX': 39, 'TIER_2_SHORT_RSI_MIN': 61, 'TIER_3_LONG_RSI_RECOVERY': 34, 'TIER_3_SHORT_RSI_RECOVERY': 66,
        'TIER_MARGIN_PCT': 0.085, 'SL_GLOBAL_CAP_PCT': -0.10, 'MONTHLY_LOSS_LIMIT_PCT': -0.25, 'MAX_CONSECUTIVE_LOSSES': 4,
    },
    {
        'label': 'Control+tighter-breaker',
        **PHASE3_BASELINE,
        'MONTHLY_LOSS_LIMIT_PCT': -0.22, 'MAX_CONSECUTIVE_LOSSES': 4, 'SL_GLOBAL_CAP_PCT': -0.10,
    },
    {
        'label': 'Control+stricter-entry',
        **PHASE3_BASELINE,
        'RSI_LONG_ENTRY': 32, 'RSI_SHORT_ENTRY': 68, 'BB_ENTRY_BUFFER_PCT': 0.007, 'VOLUME_FILTER_MULT': 0.52,
        'MONTHLY_LOSS_LIMIT_PCT': -0.25, 'MAX_CONSECUTIVE_LOSSES': 4,
    },
    {
        'label': 'Control+momentum-dca',
        **PHASE3_BASELINE,
        'MOMENTUM_GATED_DCA': True, 'TIER_2_MAX_ATR_RATIO': 1.90, 'TIER_3_MAX_ATR_RATIO': 1.60,
        'TIER_2_LONG_RSI_MAX': 40, 'TIER_2_SHORT_RSI_MIN': 60, 'TIER_3_LONG_RSI_RECOVERY': 34, 'TIER_3_SHORT_RSI_RECOVERY': 66,
        'MONTHLY_LOSS_LIMIT_PCT': -0.28,
    },
    {
        'label': 'Control+voladapt',
        **PHASE3_BASELINE,
        'VOLATILITY_ADAPTIVE_ENTRY': True, 'ATR_VOL_LOOKBACK': 72, 'HIGH_VOL_THRESHOLD': 1.15, 'LOW_VOL_THRESHOLD': 0.80,
        'RSI_LONG_ENTRY_HIGH_VOL': 31, 'RSI_LONG_ENTRY_LOW_VOL': 40, 'RSI_SHORT_ENTRY_HIGH_VOL': 69, 'RSI_SHORT_ENTRY_LOW_VOL': 60,
        'MONTHLY_LOSS_LIMIT_PCT': -0.28, 'MAX_CONSECUTIVE_LOSSES': 4,
    },
    {
        'label': 'Conservative-5x-structural',
        **PHASE3_BASELINE,
        'LEVERAGE': 5, 'TIER_MARGIN_PCT': 0.085, 'RSI_LONG_ENTRY': 32, 'RSI_SHORT_ENTRY': 68,
        'BB_ENTRY_BUFFER_PCT': 0.008, 'VOLUME_FILTER_MULT': 0.42,
        'VOLATILITY_ADAPTIVE_ENTRY': True, 'ATR_VOL_LOOKBACK': 120, 'HIGH_VOL_THRESHOLD': 1.25, 'LOW_VOL_THRESHOLD': 0.85,
        'RSI_LONG_ENTRY_HIGH_VOL': 28, 'RSI_LONG_ENTRY_LOW_VOL': 39, 'RSI_SHORT_ENTRY_HIGH_VOL': 72, 'RSI_SHORT_ENTRY_LOW_VOL': 61,
        'MOMENTUM_GATED_DCA': True, 'TIER_2_MAX_ATR_RATIO': 2.0, 'TIER_3_MAX_ATR_RATIO': 1.7,
        'TIER_2_LONG_RSI_MAX': 40, 'TIER_2_SHORT_RSI_MIN': 60, 'TIER_3_LONG_RSI_RECOVERY': 35, 'TIER_3_SHORT_RSI_RECOVERY': 65,
        'SL_GLOBAL_CAP_PCT': -0.08, 'TP_MARGIN_ROI': 0.18, 'SL_MARGIN_ROI': -0.45, 'MONTHLY_LOSS_LIMIT_PCT': -0.30,
    },
    {
        'label': 'Balanced-6x-repair',
        **PHASE3_BASELINE,
        'LEVERAGE': 6, 'TIER_MARGIN_PCT': 0.085, 'RSI_LONG_ENTRY': 32, 'RSI_SHORT_ENTRY': 68,
        'BB_ENTRY_BUFFER_PCT': 0.007, 'VOLUME_FILTER_MULT': 0.48,
        'VOLATILITY_ADAPTIVE_ENTRY': True, 'ATR_VOL_LOOKBACK': 96, 'HIGH_VOL_THRESHOLD': 1.18, 'LOW_VOL_THRESHOLD': 0.85,
        'RSI_LONG_ENTRY_HIGH_VOL': 29, 'RSI_LONG_ENTRY_LOW_VOL': 39, 'RSI_SHORT_ENTRY_HIGH_VOL': 71, 'RSI_SHORT_ENTRY_LOW_VOL': 61,
        'MOMENTUM_GATED_DCA': True, 'TIER_2_MAX_ATR_RATIO': 1.85, 'TIER_3_MAX_ATR_RATIO': 1.55,
        'TIER_2_LONG_RSI_MAX': 39, 'TIER_2_SHORT_RSI_MIN': 61, 'TIER_3_LONG_RSI_RECOVERY': 34, 'TIER_3_SHORT_RSI_RECOVERY': 66,
        'SL_GLOBAL_CAP_PCT': -0.10, 'MONTHLY_LOSS_LIMIT_PCT': -0.25, 'MAX_CONSECUTIVE_LOSSES': 4,
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
            losing_month_symbols = by_symbol[by_symbol['month'].astype(str).isin(losing_month_set)].sort_values(
                ['month', 'pnl']
            ).to_dict('records')

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
            'losing_month_symbols': [],
        }


def save_results(results, filename=None):
    if filename is None:
        filename = os.path.join(BASE_DIR, "optimization_phase3_monthly_repair.txt")

    with open(filename, "w", encoding="utf-8") as f:
        f.write("Phase 3 Monthly Loss Repair Report\n")
        f.write(f"Generated: {datetime.now():%Y-%m-%d %H:%M:%S}\n")
        f.write(f"Goal: analyze phase-3 losing months and harden the strategy with existing engine features\n")
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
                f"WorstMonth={result['worst_month']:+.2f}\n"
            )
            f.write(
                f"  Lev={params['LEVERAGE']}x Margin={params['TIER_MARGIN_PCT']:.3f} "
                f"VolAdapt={params.get('VOLATILITY_ADAPTIVE_ENTRY', False)} "
                f"DCAgate={params.get('MOMENTUM_GATED_DCA', False)} "
                f"Breaker={params['MONTHLY_LOSS_LIMIT_PCT']:.2f} MaxLossStreak={params['MAX_CONSECUTIVE_LOSSES']}\n"
            )
            if result['losing_months']:
                loss_summary = ", ".join(
                    f"{m['month']}({m['net_pnl']:+.2f})" for m in result['losing_months']
                )
                f.write(f"  Losing months: {loss_summary}\n")
            f.write("\n")

        control = next((r for r in results if r.get('label') == 'Control' and 'error' not in r), None)
        if control:
            f.write("=" * 72 + "\n")
            f.write("Control losing months by symbol\n")
            f.write("=" * 72 + "\n")
            for row in control['losing_month_symbols']:
                f.write(
                    f"{row['month']} | {row['symbol']} | trades={row['trades']} | "
                    f"W/L={row['wins']}/{row['losses']} | pnl={row['pnl']:+.2f}\n"
                )


def main():
    print("=" * 72)
    print("🚀 PHASE 3 MONTHLY LOSS REPAIR OPTIMIZER (10 ITERATIONS)")
    print("=" * 72)
    print(f"Initial Capital: {config.BASE_CAPITAL} USDT")
    print("Focus: identify losing months and harden the phase-3 baseline")
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
    valid.sort(key=lambda r: (r['total_pnl'], -r['losing_month_count'], r['worst_month']), reverse=True)

    if valid:
        print("\n" + "=" * 72)
        print("🏆 PHASE 3 MONTHLY LOSS REPAIR RANKING")
        print("=" * 72)
        for rank, result in enumerate(valid, start=1):
            marker = " ⭐ BEST" if rank == 1 else ""
            print(
                f"#{rank} Iter {result['iteration']} {result['label']}{marker} | "
                f"PnL {result['total_pnl']:+.2f} | LosingMonths {result['losing_month_count']} | "
                f"WorstMonth {result['worst_month']:+.2f} | DD {result['max_drawdown']:.1f}%"
            )

    save_results(all_results)


if __name__ == "__main__":
    main()
