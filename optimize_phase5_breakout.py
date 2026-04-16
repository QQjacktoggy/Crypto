"""
optimize_phase5_breakout.py - Phase 5 breakout / trend-following optimizer

Focus:
1. Add regime-specific breakout entries in bull / bear phases
2. Keep neutral markets on the existing mean-reversion logic
3. Reuse the current profitable ATR TP/SL and DCA framework
"""

import logging
import os
import sys
from datetime import datetime

logging.getLogger().setLevel(logging.CRITICAL)

from src.engine_backtest import BacktestEngine
from src.config import config

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


PARAM_SETS = [
    {  # 1 control: round-3 best
        'DYNAMIC_TPSL': True, 'ATR_TP_MULT': 3.0, 'ATR_SL_MULT': 1.4,
        'ATR_TP_MIN_ROI': 0.12, 'ATR_TP_MAX_ROI': 0.45, 'ATR_SL_MIN_ROI': -0.14, 'ATR_SL_MAX_ROI': -0.50,
        'LEVERAGE': 7, 'TIER_MARGIN_PCT': 0.090, 'SIGNAL_MODE': 'classic',
        'RSI_LONG_ENTRY': 33, 'RSI_SHORT_ENTRY': 67, 'BB_ENTRY_BUFFER_PCT': 0.006, 'VOLUME_FILTER_MULT': 0.45,
        'DYNAMIC_TIER_DEVIATIONS': True, 'TIER_2_ATR_DEV_MULT': 1.1, 'TIER_3_ATR_DEV_MULT': 1.8, 'MIN_TIER_DEV_PCT': 0.0025,
        'ENABLE_MONTHLY_CIRCUIT_BREAKER': True, 'MONTHLY_LOSS_LIMIT_PCT': -0.35, 'MAX_CONSECUTIVE_LOSSES': 5,
        'TRAILING_TP_ACTIVATE_ROI': 0.15, 'TRAILING_TP_CALLBACK_ROI': 0.05,
        'TIER_2_DEV_PCT': 0.008, 'TIER_3_DEV_PCT': 0.015, 'SL_GLOBAL_CAP_PCT': -0.12,
        'TP_MARGIN_ROI': 0.20, 'SL_MARGIN_ROI': -0.55,
        'ENABLE_REGIME_BREAKOUT': False,
    },
    {  # 2
        'DYNAMIC_TPSL': True, 'ATR_TP_MULT': 3.0, 'ATR_SL_MULT': 1.4,
        'ATR_TP_MIN_ROI': 0.12, 'ATR_TP_MAX_ROI': 0.45, 'ATR_SL_MIN_ROI': -0.14, 'ATR_SL_MAX_ROI': -0.50,
        'LEVERAGE': 7, 'TIER_MARGIN_PCT': 0.090, 'SIGNAL_MODE': 'classic',
        'RSI_LONG_ENTRY': 33, 'RSI_SHORT_ENTRY': 67, 'BB_ENTRY_BUFFER_PCT': 0.006, 'VOLUME_FILTER_MULT': 0.45,
        'ENABLE_REGIME_BREAKOUT': True, 'BREAKOUT_BUFFER_PCT': 0.0015, 'BREAKOUT_VOLUME_MULT': 1.00,
        'BREAKOUT_LONG_RSI_MIN': 50, 'BREAKOUT_LONG_RSI_MAX': 82, 'BREAKOUT_SHORT_RSI_MIN': 18, 'BREAKOUT_SHORT_RSI_MAX': 50,
        'DYNAMIC_TIER_DEVIATIONS': True, 'TIER_2_ATR_DEV_MULT': 1.1, 'TIER_3_ATR_DEV_MULT': 1.8, 'MIN_TIER_DEV_PCT': 0.0025,
        'ENABLE_MONTHLY_CIRCUIT_BREAKER': True, 'MONTHLY_LOSS_LIMIT_PCT': -0.35, 'MAX_CONSECUTIVE_LOSSES': 5,
        'TRAILING_TP_ACTIVATE_ROI': 0.15, 'TRAILING_TP_CALLBACK_ROI': 0.05,
        'TIER_2_DEV_PCT': 0.008, 'TIER_3_DEV_PCT': 0.015, 'SL_GLOBAL_CAP_PCT': -0.12,
        'TP_MARGIN_ROI': 0.20, 'SL_MARGIN_ROI': -0.55,
    },
    {  # 3
        'DYNAMIC_TPSL': True, 'ATR_TP_MULT': 3.0, 'ATR_SL_MULT': 1.4,
        'ATR_TP_MIN_ROI': 0.12, 'ATR_TP_MAX_ROI': 0.45, 'ATR_SL_MIN_ROI': -0.14, 'ATR_SL_MAX_ROI': -0.50,
        'LEVERAGE': 7, 'TIER_MARGIN_PCT': 0.090, 'SIGNAL_MODE': 'classic',
        'RSI_LONG_ENTRY': 33, 'RSI_SHORT_ENTRY': 67, 'BB_ENTRY_BUFFER_PCT': 0.006, 'VOLUME_FILTER_MULT': 0.45,
        'ENABLE_REGIME_BREAKOUT': True, 'BREAKOUT_BUFFER_PCT': 0.0025, 'BREAKOUT_VOLUME_MULT': 1.10,
        'BREAKOUT_LONG_RSI_MIN': 52, 'BREAKOUT_LONG_RSI_MAX': 78, 'BREAKOUT_SHORT_RSI_MIN': 22, 'BREAKOUT_SHORT_RSI_MAX': 48,
        'DYNAMIC_TIER_DEVIATIONS': True, 'TIER_2_ATR_DEV_MULT': 1.1, 'TIER_3_ATR_DEV_MULT': 1.8, 'MIN_TIER_DEV_PCT': 0.0025,
        'ENABLE_MONTHLY_CIRCUIT_BREAKER': True, 'MONTHLY_LOSS_LIMIT_PCT': -0.35, 'MAX_CONSECUTIVE_LOSSES': 5,
        'TRAILING_TP_ACTIVATE_ROI': 0.15, 'TRAILING_TP_CALLBACK_ROI': 0.05,
        'TIER_2_DEV_PCT': 0.008, 'TIER_3_DEV_PCT': 0.015, 'SL_GLOBAL_CAP_PCT': -0.12,
        'TP_MARGIN_ROI': 0.20, 'SL_MARGIN_ROI': -0.55,
    },
    {  # 4
        'DYNAMIC_TPSL': True, 'ATR_TP_MULT': 3.0, 'ATR_SL_MULT': 1.4,
        'ATR_TP_MIN_ROI': 0.12, 'ATR_TP_MAX_ROI': 0.45, 'ATR_SL_MIN_ROI': -0.14, 'ATR_SL_MAX_ROI': -0.50,
        'LEVERAGE': 7, 'TIER_MARGIN_PCT': 0.090, 'SIGNAL_MODE': 'classic',
        'RSI_LONG_ENTRY': 33, 'RSI_SHORT_ENTRY': 67, 'BB_ENTRY_BUFFER_PCT': 0.006, 'VOLUME_FILTER_MULT': 0.45,
        'ENABLE_REGIME_BREAKOUT': True, 'BREAKOUT_BUFFER_PCT': 0.0040, 'BREAKOUT_VOLUME_MULT': 1.20,
        'BREAKOUT_LONG_RSI_MIN': 55, 'BREAKOUT_LONG_RSI_MAX': 80, 'BREAKOUT_SHORT_RSI_MIN': 20, 'BREAKOUT_SHORT_RSI_MAX': 45,
        'DYNAMIC_TIER_DEVIATIONS': True, 'TIER_2_ATR_DEV_MULT': 1.1, 'TIER_3_ATR_DEV_MULT': 1.8, 'MIN_TIER_DEV_PCT': 0.0025,
        'ENABLE_MONTHLY_CIRCUIT_BREAKER': True, 'MONTHLY_LOSS_LIMIT_PCT': -0.35, 'MAX_CONSECUTIVE_LOSSES': 5,
        'TRAILING_TP_ACTIVATE_ROI': 0.15, 'TRAILING_TP_CALLBACK_ROI': 0.05,
        'TIER_2_DEV_PCT': 0.008, 'TIER_3_DEV_PCT': 0.015, 'SL_GLOBAL_CAP_PCT': -0.12,
        'TP_MARGIN_ROI': 0.20, 'SL_MARGIN_ROI': -0.55,
    },
    {  # 5
        'DYNAMIC_TPSL': True, 'ATR_TP_MULT': 3.0, 'ATR_SL_MULT': 1.5,
        'ATR_TP_MIN_ROI': 0.12, 'ATR_TP_MAX_ROI': 0.45, 'ATR_SL_MIN_ROI': -0.15, 'ATR_SL_MAX_ROI': -0.50,
        'LEVERAGE': 5, 'TIER_MARGIN_PCT': 0.085, 'SIGNAL_MODE': 'classic',
        'RSI_LONG_ENTRY': 32, 'RSI_SHORT_ENTRY': 68, 'BB_ENTRY_BUFFER_PCT': 0.008, 'VOLUME_FILTER_MULT': 0.42,
        'ENABLE_REGIME_BREAKOUT': True, 'BREAKOUT_BUFFER_PCT': 0.0020, 'BREAKOUT_VOLUME_MULT': 1.05,
        'BREAKOUT_LONG_RSI_MIN': 50, 'BREAKOUT_LONG_RSI_MAX': 76, 'BREAKOUT_SHORT_RSI_MIN': 24, 'BREAKOUT_SHORT_RSI_MAX': 48,
        'DYNAMIC_TIER_DEVIATIONS': True, 'TIER_2_ATR_DEV_MULT': 1.2, 'TIER_3_ATR_DEV_MULT': 1.9, 'MIN_TIER_DEV_PCT': 0.0030,
        'ENABLE_MONTHLY_CIRCUIT_BREAKER': True, 'MONTHLY_LOSS_LIMIT_PCT': -0.30, 'MAX_CONSECUTIVE_LOSSES': 5,
        'TRAILING_TP_ACTIVATE_ROI': 0.12, 'TRAILING_TP_CALLBACK_ROI': 0.04,
        'TIER_2_DEV_PCT': 0.010, 'TIER_3_DEV_PCT': 0.018, 'SL_GLOBAL_CAP_PCT': -0.08,
        'TP_MARGIN_ROI': 0.18, 'SL_MARGIN_ROI': -0.45,
    },
    {  # 6
        'DYNAMIC_TPSL': True, 'ATR_TP_MULT': 3.0, 'ATR_SL_MULT': 1.4,
        'ATR_TP_MIN_ROI': 0.12, 'ATR_TP_MAX_ROI': 0.45, 'ATR_SL_MIN_ROI': -0.14, 'ATR_SL_MAX_ROI': -0.50,
        'LEVERAGE': 7, 'TIER_MARGIN_PCT': 0.085, 'SIGNAL_MODE': 'multi',
        'RSI_LONG_ENTRY': 34, 'RSI_SHORT_ENTRY': 66, 'BB_ENTRY_BUFFER_PCT': 0.006, 'VOLUME_FILTER_MULT': 0.45,
        'ENABLE_REGIME_BREAKOUT': True, 'BREAKOUT_BUFFER_PCT': 0.0020, 'BREAKOUT_VOLUME_MULT': 1.05,
        'BREAKOUT_LONG_RSI_MIN': 50, 'BREAKOUT_LONG_RSI_MAX': 80, 'BREAKOUT_SHORT_RSI_MIN': 20, 'BREAKOUT_SHORT_RSI_MAX': 50,
        'DYNAMIC_TIER_DEVIATIONS': True, 'TIER_2_ATR_DEV_MULT': 1.0, 'TIER_3_ATR_DEV_MULT': 1.7, 'MIN_TIER_DEV_PCT': 0.0025,
        'ENABLE_MONTHLY_CIRCUIT_BREAKER': True, 'MONTHLY_LOSS_LIMIT_PCT': -0.30, 'MAX_CONSECUTIVE_LOSSES': 5,
        'TRAILING_TP_ACTIVATE_ROI': 0.15, 'TRAILING_TP_CALLBACK_ROI': 0.05,
        'TIER_2_DEV_PCT': 0.008, 'TIER_3_DEV_PCT': 0.015, 'SL_GLOBAL_CAP_PCT': -0.10,
        'TP_MARGIN_ROI': 0.20, 'SL_MARGIN_ROI': -0.50,
    },
    {  # 7
        'DYNAMIC_TPSL': True, 'ATR_TP_MULT': 3.0, 'ATR_SL_MULT': 1.4,
        'ATR_TP_MIN_ROI': 0.12, 'ATR_TP_MAX_ROI': 0.45, 'ATR_SL_MIN_ROI': -0.14, 'ATR_SL_MAX_ROI': -0.50,
        'LEVERAGE': 7, 'TIER_MARGIN_PCT': 0.090, 'SIGNAL_MODE': 'classic',
        'RSI_LONG_ENTRY': 33, 'RSI_SHORT_ENTRY': 67, 'BB_ENTRY_BUFFER_PCT': 0.006, 'VOLUME_FILTER_MULT': 0.45,
        'ENABLE_REGIME_BREAKOUT': True, 'BREAKOUT_BUFFER_PCT': 0.0025, 'BREAKOUT_VOLUME_MULT': 1.15,
        'BREAKOUT_LONG_RSI_MIN': 54, 'BREAKOUT_LONG_RSI_MAX': 82, 'BREAKOUT_SHORT_RSI_MIN': 18, 'BREAKOUT_SHORT_RSI_MAX': 46,
        'VOLATILITY_ADAPTIVE_ENTRY': True, 'ATR_VOL_LOOKBACK': 96, 'HIGH_VOL_THRESHOLD': 1.20, 'LOW_VOL_THRESHOLD': 0.85,
        'RSI_LONG_ENTRY_HIGH_VOL': 30, 'RSI_LONG_ENTRY_LOW_VOL': 38, 'RSI_SHORT_ENTRY_HIGH_VOL': 70, 'RSI_SHORT_ENTRY_LOW_VOL': 62,
        'DYNAMIC_TIER_DEVIATIONS': True, 'TIER_2_ATR_DEV_MULT': 1.1, 'TIER_3_ATR_DEV_MULT': 1.8, 'MIN_TIER_DEV_PCT': 0.0025,
        'ENABLE_MONTHLY_CIRCUIT_BREAKER': True, 'MONTHLY_LOSS_LIMIT_PCT': -0.35, 'MAX_CONSECUTIVE_LOSSES': 5,
        'TRAILING_TP_ACTIVATE_ROI': 0.15, 'TRAILING_TP_CALLBACK_ROI': 0.05,
        'TIER_2_DEV_PCT': 0.008, 'TIER_3_DEV_PCT': 0.015, 'SL_GLOBAL_CAP_PCT': -0.12,
        'TP_MARGIN_ROI': 0.20, 'SL_MARGIN_ROI': -0.55,
    },
    {  # 8
        'DYNAMIC_TPSL': True, 'ATR_TP_MULT': 3.1, 'ATR_SL_MULT': 1.4,
        'ATR_TP_MIN_ROI': 0.12, 'ATR_TP_MAX_ROI': 0.48, 'ATR_SL_MIN_ROI': -0.14, 'ATR_SL_MAX_ROI': -0.52,
        'LEVERAGE': 7, 'TIER_MARGIN_PCT': 0.095, 'SIGNAL_MODE': 'classic',
        'RSI_LONG_ENTRY': 35, 'RSI_SHORT_ENTRY': 65, 'BB_ENTRY_BUFFER_PCT': 0.006, 'VOLUME_FILTER_MULT': 0.42,
        'ENABLE_REGIME_BREAKOUT': True, 'BREAKOUT_BUFFER_PCT': 0.0030, 'BREAKOUT_VOLUME_MULT': 1.25,
        'BREAKOUT_LONG_RSI_MIN': 55, 'BREAKOUT_LONG_RSI_MAX': 82, 'BREAKOUT_SHORT_RSI_MIN': 18, 'BREAKOUT_SHORT_RSI_MAX': 45,
        'DYNAMIC_TIER_DEVIATIONS': True, 'TIER_2_ATR_DEV_MULT': 1.0, 'TIER_3_ATR_DEV_MULT': 1.7, 'MIN_TIER_DEV_PCT': 0.0020,
        'ENABLE_MONTHLY_CIRCUIT_BREAKER': True, 'MONTHLY_LOSS_LIMIT_PCT': -0.35, 'MAX_CONSECUTIVE_LOSSES': 5,
        'TRAILING_TP_ACTIVATE_ROI': 0.16, 'TRAILING_TP_CALLBACK_ROI': 0.05,
        'TIER_2_DEV_PCT': 0.007, 'TIER_3_DEV_PCT': 0.014, 'SL_GLOBAL_CAP_PCT': -0.12,
        'TP_MARGIN_ROI': 0.22, 'SL_MARGIN_ROI': -0.55,
    },
    {  # 9
        'DYNAMIC_TPSL': True, 'ATR_TP_MULT': 2.8, 'ATR_SL_MULT': 1.3,
        'ATR_TP_MIN_ROI': 0.10, 'ATR_TP_MAX_ROI': 0.40, 'ATR_SL_MIN_ROI': -0.12, 'ATR_SL_MAX_ROI': -0.45,
        'LEVERAGE': 5, 'TIER_MARGIN_PCT': 0.075, 'SIGNAL_MODE': 'classic',
        'RSI_LONG_ENTRY': 35, 'RSI_SHORT_ENTRY': 65, 'BB_ENTRY_BUFFER_PCT': 0.008, 'VOLUME_FILTER_MULT': 0.40,
        'ENABLE_REGIME_BREAKOUT': True, 'BREAKOUT_BUFFER_PCT': 0.0010, 'BREAKOUT_VOLUME_MULT': 0.95,
        'BREAKOUT_LONG_RSI_MIN': 48, 'BREAKOUT_LONG_RSI_MAX': 74, 'BREAKOUT_SHORT_RSI_MIN': 24, 'BREAKOUT_SHORT_RSI_MAX': 50,
        'DYNAMIC_TIER_DEVIATIONS': True, 'TIER_2_ATR_DEV_MULT': 1.0, 'TIER_3_ATR_DEV_MULT': 1.6, 'MIN_TIER_DEV_PCT': 0.0025,
        'ENABLE_MONTHLY_CIRCUIT_BREAKER': True, 'MONTHLY_LOSS_LIMIT_PCT': -0.25, 'MAX_CONSECUTIVE_LOSSES': 4,
        'TRAILING_TP_ACTIVATE_ROI': 0.14, 'TRAILING_TP_CALLBACK_ROI': 0.04,
        'TIER_2_DEV_PCT': 0.007, 'TIER_3_DEV_PCT': 0.013, 'SL_GLOBAL_CAP_PCT': -0.10,
        'TP_MARGIN_ROI': 0.18, 'SL_MARGIN_ROI': -0.45,
    },
    {  # 10
        'DYNAMIC_TPSL': True, 'ATR_TP_MULT': 3.0, 'ATR_SL_MULT': 1.4,
        'ATR_TP_MIN_ROI': 0.12, 'ATR_TP_MAX_ROI': 0.45, 'ATR_SL_MIN_ROI': -0.14, 'ATR_SL_MAX_ROI': -0.50,
        'LEVERAGE': 7, 'TIER_MARGIN_PCT': 0.090, 'SIGNAL_MODE': 'classic',
        'RSI_LONG_ENTRY': 33, 'RSI_SHORT_ENTRY': 67, 'BB_ENTRY_BUFFER_PCT': 0.006, 'VOLUME_FILTER_MULT': 0.45,
        'ENABLE_REGIME_BREAKOUT': True, 'BREAKOUT_BUFFER_PCT': 0.0035, 'BREAKOUT_VOLUME_MULT': 1.30,
        'BREAKOUT_LONG_RSI_MIN': 56, 'BREAKOUT_LONG_RSI_MAX': 84, 'BREAKOUT_SHORT_RSI_MIN': 16, 'BREAKOUT_SHORT_RSI_MAX': 44,
        'DYNAMIC_TIER_DEVIATIONS': True, 'TIER_2_ATR_DEV_MULT': 1.1, 'TIER_3_ATR_DEV_MULT': 1.8, 'MIN_TIER_DEV_PCT': 0.0025,
        'ENABLE_MONTHLY_CIRCUIT_BREAKER': True, 'MONTHLY_LOSS_LIMIT_PCT': -0.35, 'MAX_CONSECUTIVE_LOSSES': 5,
        'TRAILING_TP_ACTIVATE_ROI': 0.17, 'TRAILING_TP_CALLBACK_ROI': 0.05,
        'TIER_2_DEV_PCT': 0.008, 'TIER_3_DEV_PCT': 0.015, 'SL_GLOBAL_CAP_PCT': -0.12,
        'TP_MARGIN_ROI': 0.22, 'SL_MARGIN_ROI': -0.55,
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
            'MACD_LONG_RSI_MAX': config.MACD_LONG_RSI_MAX,
            'MACD_SHORT_RSI_MIN': config.MACD_SHORT_RSI_MIN,
            'EMA_LONG_RSI_MAX': config.EMA_LONG_RSI_MAX,
            'EMA_SHORT_RSI_MIN': config.EMA_SHORT_RSI_MIN,
            'TREND_SMA_LENGTH': config.TREND_SMA_LENGTH,
            'FUNDING_RATE': config.FUNDING_RATE,
            'FUNDING_INTERVAL_HOURS': config.FUNDING_INTERVAL_HOURS,
            'FEE_RATE': config.FEE_RATE,
            'COMPOUND_MODE': config.COMPOUND_MODE,
            'BASE_CAPITAL': config.BASE_CAPITAL,
            'MAX_ACTIVE_TRADES': config.MAX_ACTIVE_TRADES,
            'COOLDOWN_CANDLES': config.COOLDOWN_CANDLES,
            'CONSECUTIVE_LOSS_COOLDOWN_MULT': config.CONSECUTIVE_LOSS_COOLDOWN_MULT,
            'MONTHLY_LOSS_LIMIT_PCT': config.MONTHLY_LOSS_LIMIT_PCT,
            'BREAKOUT_BUFFER_PCT': config.BREAKOUT_BUFFER_PCT,
            'BREAKOUT_VOLUME_MULT': config.BREAKOUT_VOLUME_MULT,
            'BREAKOUT_LONG_RSI_MIN': config.BREAKOUT_LONG_RSI_MIN,
            'BREAKOUT_LONG_RSI_MAX': config.BREAKOUT_LONG_RSI_MAX,
            'BREAKOUT_SHORT_RSI_MIN': config.BREAKOUT_SHORT_RSI_MIN,
            'BREAKOUT_SHORT_RSI_MAX': config.BREAKOUT_SHORT_RSI_MAX,
        }
        full_params.update(params)

        engine = BacktestEngine(days=days, param_overrides=full_params)
        engine.run()

        monthly_data = engine.get_monthly_pnl_report()
        closed_trades = [t for t in engine.trades if t['type'] == 'close']
        total_pnl = sum(t['pnl'] for t in closed_trades)

        result = {
            'iteration': iteration_num,
            'params': params,
            'initial_balance': engine.initial_balance,
            'final_balance': engine.current_balance,
            'total_pnl': total_pnl,
            'total_trades': len(closed_trades),
            'win_rate': (sum(1 for t in closed_trades if t['pnl'] > 0) / len(closed_trades) * 100) if closed_trades else 0,
            'max_drawdown': engine.max_drawdown * 100,
            'monthly_data': monthly_data,
        }

        if monthly_data:
            monthly_pnls = [m['net_pnl'] for m in monthly_data]
            result['avg_monthly_pnl'] = sum(monthly_pnls) / len(monthly_pnls)
            result['best_month'] = max(monthly_pnls)
            result['months_above_40'] = sum(1 for p in monthly_pnls if p >= 40)
        else:
            result['avg_monthly_pnl'] = 0
            result['best_month'] = 0
            result['months_above_40'] = 0

        return result
    except Exception as e:
        return {
            'iteration': iteration_num,
            'params': params,
            'error': str(e),
            'final_balance': 0,
            'total_pnl': 0,
            'total_trades': 0,
            'win_rate': 0,
            'max_drawdown': 100,
            'monthly_data': [],
            'avg_monthly_pnl': 0,
            'best_month': 0,
            'months_above_40': 0,
        }


def save_results(results, filename=None):
    if filename is None:
        filename = os.path.join(BASE_DIR, "optimization_phase5_breakout.txt")
    with open(filename, "w", encoding="utf-8") as f:
        f.write("Phase 5 Breakout Optimization Report\n")
        f.write(f"Generated: {datetime.now():%Y-%m-%d %H:%M:%S}\n")
        f.write(f"Goal: yearly profit >= 400 USDT on {config.BASE_CAPITAL} USDT capital\n")
        f.write("=" * 72 + "\n\n")
        for result in results:
            f.write(f"Iteration #{result['iteration']}\n")
            if 'error' in result:
                f.write(f"  ERROR: {result['error']}\n\n")
                continue
            params = result['params']
            f.write(
                f"  PnL={result['total_pnl']:+.2f} | Final={result['final_balance']:.2f} | "
                f"WR={result['win_rate']:.1f}% | DD={result['max_drawdown']:.1f}% | "
                f"Trades={result['total_trades']} | AvgM={result['avg_monthly_pnl']:+.2f} | BestM={result['best_month']:+.2f}\n"
            )
            f.write(
                f"  Breakout={params.get('ENABLE_REGIME_BREAKOUT', False)} "
                f"Buf={params.get('BREAKOUT_BUFFER_PCT', 0):.4f} "
                f"Vol={params.get('BREAKOUT_VOLUME_MULT', 0):.2f} "
                f"LongRSI={params.get('BREAKOUT_LONG_RSI_MIN', 0)}-{params.get('BREAKOUT_LONG_RSI_MAX', 0)} "
                f"ShortRSI={params.get('BREAKOUT_SHORT_RSI_MIN', 0)}-{params.get('BREAKOUT_SHORT_RSI_MAX', 0)}\n"
            )
            f.write(
                f"  Lev={params['LEVERAGE']}x Margin={params['TIER_MARGIN_PCT']:.3f} Mode={params['SIGNAL_MODE']} "
                f"BBbuf={params['BB_ENTRY_BUFFER_PCT']:.3f} VolFilter={params['VOLUME_FILTER_MULT']:.2f}\n\n"
            )


def main():
    print("=" * 72)
    print("🚀 PHASE 5 BREAKOUT / TREND FOLLOWING OPTIMIZER (10 ITERATIONS)")
    print("=" * 72)
    print(f"Initial Capital: {config.BASE_CAPITAL} USDT")
    print("Target: yearly profit >= 400 USDT")
    print("Axes: regime-specific breakout entries in bull / bear markets")
    print("=" * 72)

    all_results = []
    for i, params in enumerate(PARAM_SETS, start=1):
        sys.stdout.write(f"\r⏳ Running iteration {i}/10...")
        sys.stdout.flush()
        result = run_single_iteration(i, params)
        all_results.append(result)
        if 'error' in result:
            sys.stdout.write(f"\r❌ Iteration {i}/10 | ERROR: {result['error']}\n")
        else:
            sys.stdout.write(
                f"\r✅ Iteration {i}/10 | PnL: {result['total_pnl']:+.2f} | "
                f"WR: {result['win_rate']:.1f}% | DD: {result['max_drawdown']:.1f}% | "
                f"Trades: {result['total_trades']}\n"
            )

    valid = [r for r in all_results if 'error' not in r and r['total_trades'] > 0]
    if not valid:
        print("\n❌ No valid results.")
        save_results(all_results)
        return

    valid.sort(key=lambda r: r['total_pnl'], reverse=True)
    best = valid[0]

    print("\n" + "=" * 72)
    print("🏆 PHASE 5 RANKING BY TOTAL PNL")
    print("=" * 72)
    for rank, result in enumerate(valid, start=1):
        params = result['params']
        marker = " ⭐ BEST" if rank == 1 else ""
        print(
            f"#{rank} Iter {result['iteration']}{marker} | PnL {result['total_pnl']:+.2f} | "
            f"Final {result['final_balance']:.2f} | DD {result['max_drawdown']:.1f}% | "
            f"Trades {result['total_trades']} | Breakout {params.get('ENABLE_REGIME_BREAKOUT', False)} | "
            f"Buf {params.get('BREAKOUT_BUFFER_PCT', 0):.4f} | Vol {params.get('BREAKOUT_VOLUME_MULT', 0):.2f}"
        )

    print("\n" + "=" * 72)
    print(f"Best yearly PnL: {best['total_pnl']:+.2f} USDT")
    print(f"Target 400 USDT reached: {'YES' if best['total_pnl'] >= 400 else 'NO'}")
    print("=" * 72)

    save_results(all_results)


if __name__ == "__main__":
    main()
