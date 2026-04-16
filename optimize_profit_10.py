"""
optimize_profit_10.py - Profit-focused 10-iteration optimizer

Round 3 goal:
1. Continue improving yearly profit on top of dynamic ATR TP/SL
2. Explore newly tunable dimensions that were previously hard-coded:
   - Bollinger entry buffer
   - Volume filter multiplier
   - Monthly circuit breaker
   - Dynamic ATR-driven DCA tier deviations
3. Check whether 400 USDT yearly profit is achievable with current strategy structure
"""

import logging
import sys
from datetime import datetime

logging.getLogger().setLevel(logging.CRITICAL)

from src.engine_backtest import BacktestEngine
from src.config import config


PARAM_SETS = [
    {  # 1
        'DYNAMIC_TPSL': True, 'ATR_TP_MULT': 3.0, 'ATR_SL_MULT': 1.5,
        'ATR_TP_MIN_ROI': 0.12, 'ATR_TP_MAX_ROI': 0.40, 'ATR_SL_MIN_ROI': -0.15, 'ATR_SL_MAX_ROI': -0.50,
        'LEVERAGE': 5, 'TIER_MARGIN_PCT': 0.055, 'SIGNAL_MODE': 'classic',
        'RSI_LONG_ENTRY': 30, 'RSI_SHORT_ENTRY': 70, 'BB_ENTRY_BUFFER_PCT': 0.003, 'VOLUME_FILTER_MULT': 0.55,
        'DYNAMIC_TIER_DEVIATIONS': True, 'TIER_2_ATR_DEV_MULT': 1.6, 'TIER_3_ATR_DEV_MULT': 2.8, 'MIN_TIER_DEV_PCT': 0.0035,
        'ENABLE_MONTHLY_CIRCUIT_BREAKER': False, 'MAX_CONSECUTIVE_LOSSES': 4,
        'TRAILING_TP_ACTIVATE_ROI': 0.12, 'TRAILING_TP_CALLBACK_ROI': 0.04,
        'TIER_2_DEV_PCT': 0.012, 'TIER_3_DEV_PCT': 0.025, 'SL_GLOBAL_CAP_PCT': -0.08,
        'TP_MARGIN_ROI': 0.18, 'SL_MARGIN_ROI': -0.50,
    },
    {  # 2
        'DYNAMIC_TPSL': True, 'ATR_TP_MULT': 3.2, 'ATR_SL_MULT': 1.5,
        'ATR_TP_MIN_ROI': 0.14, 'ATR_TP_MAX_ROI': 0.45, 'ATR_SL_MIN_ROI': -0.15, 'ATR_SL_MAX_ROI': -0.55,
        'LEVERAGE': 7, 'TIER_MARGIN_PCT': 0.070, 'SIGNAL_MODE': 'classic',
        'RSI_LONG_ENTRY': 32, 'RSI_SHORT_ENTRY': 68, 'BB_ENTRY_BUFFER_PCT': 0.005, 'VOLUME_FILTER_MULT': 0.50,
        'DYNAMIC_TIER_DEVIATIONS': True, 'TIER_2_ATR_DEV_MULT': 1.5, 'TIER_3_ATR_DEV_MULT': 2.5, 'MIN_TIER_DEV_PCT': 0.0030,
        'ENABLE_MONTHLY_CIRCUIT_BREAKER': False, 'MAX_CONSECUTIVE_LOSSES': 4,
        'TRAILING_TP_ACTIVATE_ROI': 0.15, 'TRAILING_TP_CALLBACK_ROI': 0.05,
        'TIER_2_DEV_PCT': 0.010, 'TIER_3_DEV_PCT': 0.020, 'SL_GLOBAL_CAP_PCT': -0.10,
        'TP_MARGIN_ROI': 0.20, 'SL_MARGIN_ROI': -0.55,
    },
    {  # 3
        'DYNAMIC_TPSL': True, 'ATR_TP_MULT': 3.5, 'ATR_SL_MULT': 1.6,
        'ATR_TP_MIN_ROI': 0.16, 'ATR_TP_MAX_ROI': 0.55, 'ATR_SL_MIN_ROI': -0.18, 'ATR_SL_MAX_ROI': -0.60,
        'LEVERAGE': 10, 'TIER_MARGIN_PCT': 0.100, 'SIGNAL_MODE': 'classic',
        'RSI_LONG_ENTRY': 34, 'RSI_SHORT_ENTRY': 66, 'BB_ENTRY_BUFFER_PCT': 0.008, 'VOLUME_FILTER_MULT': 0.40,
        'DYNAMIC_TIER_DEVIATIONS': True, 'TIER_2_ATR_DEV_MULT': 1.4, 'TIER_3_ATR_DEV_MULT': 2.2, 'MIN_TIER_DEV_PCT': 0.0025,
        'ENABLE_MONTHLY_CIRCUIT_BREAKER': False, 'MAX_CONSECUTIVE_LOSSES': 5,
        'TRAILING_TP_ACTIVATE_ROI': 0.18, 'TRAILING_TP_CALLBACK_ROI': 0.06,
        'TIER_2_DEV_PCT': 0.008, 'TIER_3_DEV_PCT': 0.016, 'SL_GLOBAL_CAP_PCT': -0.12,
        'TP_MARGIN_ROI': 0.25, 'SL_MARGIN_ROI': -0.60,
    },
    {  # 4
        'DYNAMIC_TPSL': True, 'ATR_TP_MULT': 4.0, 'ATR_SL_MULT': 1.8,
        'ATR_TP_MIN_ROI': 0.20, 'ATR_TP_MAX_ROI': 0.70, 'ATR_SL_MIN_ROI': -0.20, 'ATR_SL_MAX_ROI': -0.70,
        'LEVERAGE': 12, 'TIER_MARGIN_PCT': 0.120, 'SIGNAL_MODE': 'classic',
        'RSI_LONG_ENTRY': 35, 'RSI_SHORT_ENTRY': 65, 'BB_ENTRY_BUFFER_PCT': 0.010, 'VOLUME_FILTER_MULT': 0.35,
        'DYNAMIC_TIER_DEVIATIONS': True, 'TIER_2_ATR_DEV_MULT': 1.2, 'TIER_3_ATR_DEV_MULT': 2.0, 'MIN_TIER_DEV_PCT': 0.0020,
        'ENABLE_MONTHLY_CIRCUIT_BREAKER': False, 'MAX_CONSECUTIVE_LOSSES': 5,
        'TRAILING_TP_ACTIVATE_ROI': 0.20, 'TRAILING_TP_CALLBACK_ROI': 0.07,
        'TIER_2_DEV_PCT': 0.007, 'TIER_3_DEV_PCT': 0.014, 'SL_GLOBAL_CAP_PCT': -0.14,
        'TP_MARGIN_ROI': 0.30, 'SL_MARGIN_ROI': -0.70,
    },
    {  # 5
        'DYNAMIC_TPSL': True, 'ATR_TP_MULT': 2.8, 'ATR_SL_MULT': 1.2,
        'ATR_TP_MIN_ROI': 0.12, 'ATR_TP_MAX_ROI': 0.40, 'ATR_SL_MIN_ROI': -0.12, 'ATR_SL_MAX_ROI': -0.40,
        'LEVERAGE': 7, 'TIER_MARGIN_PCT': 0.080, 'SIGNAL_MODE': 'multi',
        'RSI_LONG_ENTRY': 35, 'RSI_SHORT_ENTRY': 65, 'BB_ENTRY_BUFFER_PCT': 0.004, 'VOLUME_FILTER_MULT': 0.50,
        'DYNAMIC_TIER_DEVIATIONS': True, 'TIER_2_ATR_DEV_MULT': 1.4, 'TIER_3_ATR_DEV_MULT': 2.4, 'MIN_TIER_DEV_PCT': 0.0030,
        'ENABLE_MONTHLY_CIRCUIT_BREAKER': False, 'MAX_CONSECUTIVE_LOSSES': 4,
        'TRAILING_TP_ACTIVATE_ROI': 0.12, 'TRAILING_TP_CALLBACK_ROI': 0.04,
        'TIER_2_DEV_PCT': 0.009, 'TIER_3_DEV_PCT': 0.018, 'SL_GLOBAL_CAP_PCT': -0.10,
        'TP_MARGIN_ROI': 0.18, 'SL_MARGIN_ROI': -0.45,
    },
    {  # 6
        'DYNAMIC_TPSL': True, 'ATR_TP_MULT': 3.2, 'ATR_SL_MULT': 1.2,
        'ATR_TP_MIN_ROI': 0.14, 'ATR_TP_MAX_ROI': 0.55, 'ATR_SL_MIN_ROI': -0.12, 'ATR_SL_MAX_ROI': -0.45,
        'LEVERAGE': 10, 'TIER_MARGIN_PCT': 0.090, 'SIGNAL_MODE': 'multi',
        'RSI_LONG_ENTRY': 36, 'RSI_SHORT_ENTRY': 64, 'BB_ENTRY_BUFFER_PCT': 0.006, 'VOLUME_FILTER_MULT': 0.45,
        'DYNAMIC_TIER_DEVIATIONS': True, 'TIER_2_ATR_DEV_MULT': 1.2, 'TIER_3_ATR_DEV_MULT': 2.0, 'MIN_TIER_DEV_PCT': 0.0025,
        'ENABLE_MONTHLY_CIRCUIT_BREAKER': False, 'MAX_CONSECUTIVE_LOSSES': 5,
        'TRAILING_TP_ACTIVATE_ROI': 0.15, 'TRAILING_TP_CALLBACK_ROI': 0.05,
        'TIER_2_DEV_PCT': 0.008, 'TIER_3_DEV_PCT': 0.016, 'SL_GLOBAL_CAP_PCT': -0.12,
        'TP_MARGIN_ROI': 0.22, 'SL_MARGIN_ROI': -0.50,
    },
    {  # 7
        'DYNAMIC_TPSL': True, 'ATR_TP_MULT': 3.0, 'ATR_SL_MULT': 1.4,
        'ATR_TP_MIN_ROI': 0.12, 'ATR_TP_MAX_ROI': 0.45, 'ATR_SL_MIN_ROI': -0.14, 'ATR_SL_MAX_ROI': -0.50,
        'LEVERAGE': 7, 'TIER_MARGIN_PCT': 0.090, 'SIGNAL_MODE': 'classic',
        'RSI_LONG_ENTRY': 33, 'RSI_SHORT_ENTRY': 67, 'BB_ENTRY_BUFFER_PCT': 0.006, 'VOLUME_FILTER_MULT': 0.45,
        'DYNAMIC_TIER_DEVIATIONS': True, 'TIER_2_ATR_DEV_MULT': 1.1, 'TIER_3_ATR_DEV_MULT': 1.8, 'MIN_TIER_DEV_PCT': 0.0025,
        'ENABLE_MONTHLY_CIRCUIT_BREAKER': True, 'MONTHLY_LOSS_LIMIT_PCT': -0.35, 'MAX_CONSECUTIVE_LOSSES': 5,
        'TRAILING_TP_ACTIVATE_ROI': 0.15, 'TRAILING_TP_CALLBACK_ROI': 0.05,
        'TIER_2_DEV_PCT': 0.008, 'TIER_3_DEV_PCT': 0.015, 'SL_GLOBAL_CAP_PCT': -0.12,
        'TP_MARGIN_ROI': 0.20, 'SL_MARGIN_ROI': -0.55,
    },
    {  # 8
        'DYNAMIC_TPSL': True, 'ATR_TP_MULT': 4.5, 'ATR_SL_MULT': 1.5,
        'ATR_TP_MIN_ROI': 0.20, 'ATR_TP_MAX_ROI': 0.90, 'ATR_SL_MIN_ROI': -0.15, 'ATR_SL_MAX_ROI': -0.60,
        'LEVERAGE': 15, 'TIER_MARGIN_PCT': 0.120, 'SIGNAL_MODE': 'classic',
        'RSI_LONG_ENTRY': 36, 'RSI_SHORT_ENTRY': 64, 'BB_ENTRY_BUFFER_PCT': 0.012, 'VOLUME_FILTER_MULT': 0.30,
        'DYNAMIC_TIER_DEVIATIONS': True, 'TIER_2_ATR_DEV_MULT': 1.0, 'TIER_3_ATR_DEV_MULT': 1.6, 'MIN_TIER_DEV_PCT': 0.0020,
        'ENABLE_MONTHLY_CIRCUIT_BREAKER': False, 'MAX_CONSECUTIVE_LOSSES': 6,
        'TRAILING_TP_ACTIVATE_ROI': 0.22, 'TRAILING_TP_CALLBACK_ROI': 0.07,
        'TIER_2_DEV_PCT': 0.006, 'TIER_3_DEV_PCT': 0.012, 'SL_GLOBAL_CAP_PCT': -0.16,
        'TP_MARGIN_ROI': 0.35, 'SL_MARGIN_ROI': -0.80,
    },
    {  # 9
        'DYNAMIC_TPSL': True, 'ATR_TP_MULT': 3.8, 'ATR_SL_MULT': 1.3,
        'ATR_TP_MIN_ROI': 0.18, 'ATR_TP_MAX_ROI': 0.70, 'ATR_SL_MIN_ROI': -0.14, 'ATR_SL_MAX_ROI': -0.50,
        'LEVERAGE': 12, 'TIER_MARGIN_PCT': 0.100, 'SIGNAL_MODE': 'multi',
        'RSI_LONG_ENTRY': 38, 'RSI_SHORT_ENTRY': 62, 'BB_ENTRY_BUFFER_PCT': 0.008, 'VOLUME_FILTER_MULT': 0.35,
        'DYNAMIC_TIER_DEVIATIONS': True, 'TIER_2_ATR_DEV_MULT': 1.0, 'TIER_3_ATR_DEV_MULT': 1.6, 'MIN_TIER_DEV_PCT': 0.0020,
        'ENABLE_MONTHLY_CIRCUIT_BREAKER': False, 'MAX_CONSECUTIVE_LOSSES': 6,
        'TRAILING_TP_ACTIVATE_ROI': 0.18, 'TRAILING_TP_CALLBACK_ROI': 0.06,
        'TIER_2_DEV_PCT': 0.006, 'TIER_3_DEV_PCT': 0.012, 'SL_GLOBAL_CAP_PCT': -0.15,
        'TP_MARGIN_ROI': 0.30, 'SL_MARGIN_ROI': -0.65,
    },
    {  # 10
        'DYNAMIC_TPSL': True, 'ATR_TP_MULT': 5.0, 'ATR_SL_MULT': 1.8,
        'ATR_TP_MIN_ROI': 0.25, 'ATR_TP_MAX_ROI': 1.20, 'ATR_SL_MIN_ROI': -0.20, 'ATR_SL_MAX_ROI': -0.80,
        'LEVERAGE': 20, 'TIER_MARGIN_PCT': 0.150, 'SIGNAL_MODE': 'classic',
        'RSI_LONG_ENTRY': 40, 'RSI_SHORT_ENTRY': 60, 'BB_ENTRY_BUFFER_PCT': 0.015, 'VOLUME_FILTER_MULT': 0.25,
        'DYNAMIC_TIER_DEVIATIONS': True, 'TIER_2_ATR_DEV_MULT': 0.9, 'TIER_3_ATR_DEV_MULT': 1.4, 'MIN_TIER_DEV_PCT': 0.0015,
        'ENABLE_MONTHLY_CIRCUIT_BREAKER': False, 'MAX_CONSECUTIVE_LOSSES': 7,
        'TRAILING_TP_ACTIVATE_ROI': 0.25, 'TRAILING_TP_CALLBACK_ROI': 0.08,
        'TIER_2_DEV_PCT': 0.005, 'TIER_3_DEV_PCT': 0.010, 'SL_GLOBAL_CAP_PCT': -0.18,
        'TP_MARGIN_ROI': 0.40, 'SL_MARGIN_ROI': -1.00,
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


def save_results(results, filename="/home/runner/work/Crypto/Crypto/optimization_profit_round3.txt"):
    with open(filename, "w", encoding="utf-8") as f:
        f.write("Round 3 Profit-Focused Optimization Report\n")
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
                f"AvgM={result['avg_monthly_pnl']:+.2f} | BestM={result['best_month']:+.2f}\n"
            )
            f.write(
                f"  Lev={params['LEVERAGE']}x Margin={params['TIER_MARGIN_PCT']:.3f} "
                f"Mode={params['SIGNAL_MODE']} RSI={params['RSI_LONG_ENTRY']}/{params['RSI_SHORT_ENTRY']} "
                f"BBbuf={params['BB_ENTRY_BUFFER_PCT']:.3f} Vol={params['VOLUME_FILTER_MULT']:.2f}\n"
            )
            f.write(
                f"  ATR TP/SL={params['ATR_TP_MULT']}/{params['ATR_SL_MULT']} "
                f"DynTier={params['DYNAMIC_TIER_DEVIATIONS']} "
                f"T2/T3 ATR mult={params['TIER_2_ATR_DEV_MULT']}/{params['TIER_3_ATR_DEV_MULT']} "
                f"Breaker={params['ENABLE_MONTHLY_CIRCUIT_BREAKER']}\n\n"
            )


def main():
    print("=" * 72)
    print("🚀 ROUND 3 PROFIT-FOCUSED OPTIMIZER (10 ITERATIONS)")
    print("=" * 72)
    print(f"Initial Capital: {config.BASE_CAPITAL} USDT")
    print("Target: yearly profit >= 400 USDT")
    print("Exploration axes: signal flexibility, dynamic DCA, circuit breaker, aggressive compounding")
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
                f"Best Month: {result['best_month']:+.2f}\n"
            )

    valid = [r for r in all_results if 'error' not in r and r['total_trades'] > 0]
    if not valid:
        print("\n❌ No valid results.")
        save_results(all_results)
        return

    valid.sort(key=lambda r: r['total_pnl'], reverse=True)
    best = valid[0]

    print("\n" + "=" * 72)
    print("🏆 ROUND 3 RANKING BY TOTAL PNL")
    print("=" * 72)
    for rank, result in enumerate(valid, start=1):
        params = result['params']
        marker = " ⭐ BEST" if rank == 1 else ""
        print(
            f"#{rank} Iter {result['iteration']}{marker} | PnL {result['total_pnl']:+.2f} | "
            f"Final {result['final_balance']:.2f} | DD {result['max_drawdown']:.1f}% | "
            f"Lev {params['LEVERAGE']}x | Margin {params['TIER_MARGIN_PCT']:.3f} | "
            f"Mode {params['SIGNAL_MODE']} | BB {params['BB_ENTRY_BUFFER_PCT']:.3f} | "
            f"Vol {params['VOLUME_FILTER_MULT']:.2f}"
        )

    print("\n" + "=" * 72)
    print(f"Best yearly PnL: {best['total_pnl']:+.2f} USDT")
    print(f"Target 400 USDT reached: {'YES' if best['total_pnl'] >= 400 else 'NO'}")
    print("=" * 72)

    save_results(all_results)


if __name__ == "__main__":
    main()
