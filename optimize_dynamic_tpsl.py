"""
optimize_dynamic_tpsl.py - 10-Iteration Dynamic ATR-based TP/SL Optimizer

Uses ATR (Average True Range) to dynamically set TP/SL per trade based on
current market volatility, instead of fixed ROI percentages.

Key idea:
  - TP = ATR × TP_MULT → converted to margin ROI, clamped by min/max bounds
  - SL = ATR × SL_MULT → converted to margin ROI, clamped by min/max bounds
  - In low-volatility periods: tighter targets → more frequent small wins
  - In high-volatility periods: wider targets → ride big moves, avoid premature SL

10 iterations explore different ATR multiplier combinations and clamp ranges.
"""

import logging
import sys
import os
from datetime import datetime

logging.getLogger().setLevel(logging.CRITICAL)

from src.engine_backtest import BacktestEngine
from src.config import config

# ============================================================
# 10 Dynamic TP/SL Parameter Sets
# ============================================================

PARAM_SETS = [
    {  # 1: Tight ATR TP/SL, classic signals, 5x
        'DYNAMIC_TPSL': True,
        'ATR_TP_MULT': 1.5, 'ATR_SL_MULT': 1.0,
        'ATR_TP_MIN_ROI': 0.08, 'ATR_TP_MAX_ROI': 0.25,
        'ATR_SL_MIN_ROI': -0.12, 'ATR_SL_MAX_ROI': -0.40,
        'RSI_LONG_ENTRY': 30, 'RSI_SHORT_ENTRY': 70,
        'SL_GLOBAL_CAP_PCT': -0.06, 'TIER_MARGIN_PCT': 0.055,
        'LEVERAGE': 5, 'TRAILING_TP_ACTIVATE_ROI': 0.10, 'TRAILING_TP_CALLBACK_ROI': 0.03,
        'TIER_2_DEV_PCT': 0.012, 'TIER_3_DEV_PCT': 0.025,
        'MAX_ACTIVE_TRADES': 5, 'COOLDOWN_CANDLES': 12, 'SIGNAL_MODE': 'classic',
        'TP_MARGIN_ROI': 0.15, 'SL_MARGIN_ROI': -0.50,  # fallback if ATR missing
    },
    {  # 2: Balanced ATR 2.0/1.5, classic, 5x
        'DYNAMIC_TPSL': True,
        'ATR_TP_MULT': 2.0, 'ATR_SL_MULT': 1.5,
        'ATR_TP_MIN_ROI': 0.10, 'ATR_TP_MAX_ROI': 0.30,
        'ATR_SL_MIN_ROI': -0.15, 'ATR_SL_MAX_ROI': -0.50,
        'RSI_LONG_ENTRY': 32, 'RSI_SHORT_ENTRY': 68,
        'SL_GLOBAL_CAP_PCT': -0.08, 'TIER_MARGIN_PCT': 0.055,
        'LEVERAGE': 5, 'TRAILING_TP_ACTIVATE_ROI': 0.12, 'TRAILING_TP_CALLBACK_ROI': 0.04,
        'TIER_2_DEV_PCT': 0.012, 'TIER_3_DEV_PCT': 0.025,
        'MAX_ACTIVE_TRADES': 5, 'COOLDOWN_CANDLES': 12, 'SIGNAL_MODE': 'classic',
        'TP_MARGIN_ROI': 0.15, 'SL_MARGIN_ROI': -0.50,
    },
    {  # 3: Wide ATR 3.0/1.5, classic, 5x — TP:SL = 2:1
        'DYNAMIC_TPSL': True,
        'ATR_TP_MULT': 3.0, 'ATR_SL_MULT': 1.5,
        'ATR_TP_MIN_ROI': 0.12, 'ATR_TP_MAX_ROI': 0.40,
        'ATR_SL_MIN_ROI': -0.15, 'ATR_SL_MAX_ROI': -0.50,
        'RSI_LONG_ENTRY': 30, 'RSI_SHORT_ENTRY': 70,
        'SL_GLOBAL_CAP_PCT': -0.08, 'TIER_MARGIN_PCT': 0.055,
        'LEVERAGE': 5, 'TRAILING_TP_ACTIVATE_ROI': 0.12, 'TRAILING_TP_CALLBACK_ROI': 0.04,
        'TIER_2_DEV_PCT': 0.015, 'TIER_3_DEV_PCT': 0.030,
        'MAX_ACTIVE_TRADES': 5, 'COOLDOWN_CANDLES': 12, 'SIGNAL_MODE': 'classic',
        'TP_MARGIN_ROI': 0.18, 'SL_MARGIN_ROI': -0.50,
    },
    {  # 4: ATR 2.5/1.0 — very aggressive TP:SL = 2.5:1, multi, 7x
        'DYNAMIC_TPSL': True,
        'ATR_TP_MULT': 2.5, 'ATR_SL_MULT': 1.0,
        'ATR_TP_MIN_ROI': 0.10, 'ATR_TP_MAX_ROI': 0.35,
        'ATR_SL_MIN_ROI': -0.10, 'ATR_SL_MAX_ROI': -0.35,
        'RSI_LONG_ENTRY': 32, 'RSI_SHORT_ENTRY': 68,
        'SL_GLOBAL_CAP_PCT': -0.06, 'TIER_MARGIN_PCT': 0.050,
        'LEVERAGE': 7, 'TRAILING_TP_ACTIVATE_ROI': 0.10, 'TRAILING_TP_CALLBACK_ROI': 0.03,
        'TIER_2_DEV_PCT': 0.010, 'TIER_3_DEV_PCT': 0.020,
        'MAX_ACTIVE_TRADES': 4, 'COOLDOWN_CANDLES': 12, 'SIGNAL_MODE': 'multi',
        'TP_MARGIN_ROI': 0.15, 'SL_MARGIN_ROI': -0.40,
    },
    {  # 5: ATR 2.0/1.0, multi, 7x — tight SL, moderate TP
        'DYNAMIC_TPSL': True,
        'ATR_TP_MULT': 2.0, 'ATR_SL_MULT': 1.0,
        'ATR_TP_MIN_ROI': 0.08, 'ATR_TP_MAX_ROI': 0.30,
        'ATR_SL_MIN_ROI': -0.10, 'ATR_SL_MAX_ROI': -0.30,
        'RSI_LONG_ENTRY': 35, 'RSI_SHORT_ENTRY': 65,
        'SL_GLOBAL_CAP_PCT': -0.06, 'TIER_MARGIN_PCT': 0.050,
        'LEVERAGE': 7, 'TRAILING_TP_ACTIVATE_ROI': 0.10, 'TRAILING_TP_CALLBACK_ROI': 0.03,
        'TIER_2_DEV_PCT': 0.010, 'TIER_3_DEV_PCT': 0.020,
        'MAX_ACTIVE_TRADES': 4, 'COOLDOWN_CANDLES': 8, 'SIGNAL_MODE': 'multi',
        'TP_MARGIN_ROI': 0.15, 'SL_MARGIN_ROI': -0.40,
    },
    {  # 6: ATR 3.0/2.0, classic, 10x — wide both, high leverage
        'DYNAMIC_TPSL': True,
        'ATR_TP_MULT': 3.0, 'ATR_SL_MULT': 2.0,
        'ATR_TP_MIN_ROI': 0.12, 'ATR_TP_MAX_ROI': 0.40,
        'ATR_SL_MIN_ROI': -0.20, 'ATR_SL_MAX_ROI': -0.60,
        'RSI_LONG_ENTRY': 28, 'RSI_SHORT_ENTRY': 72,
        'SL_GLOBAL_CAP_PCT': -0.08, 'TIER_MARGIN_PCT': 0.040,
        'LEVERAGE': 10, 'TRAILING_TP_ACTIVATE_ROI': 0.15, 'TRAILING_TP_CALLBACK_ROI': 0.05,
        'TIER_2_DEV_PCT': 0.010, 'TIER_3_DEV_PCT': 0.025,
        'MAX_ACTIVE_TRADES': 4, 'COOLDOWN_CANDLES': 12, 'SIGNAL_MODE': 'classic',
        'TP_MARGIN_ROI': 0.20, 'SL_MARGIN_ROI': -0.40,
    },
    {  # 7: ATR 2.0/0.8, multi, 7x — very tight SL, standard TP
        'DYNAMIC_TPSL': True,
        'ATR_TP_MULT': 2.0, 'ATR_SL_MULT': 0.8,
        'ATR_TP_MIN_ROI': 0.08, 'ATR_TP_MAX_ROI': 0.25,
        'ATR_SL_MIN_ROI': -0.08, 'ATR_SL_MAX_ROI': -0.25,
        'RSI_LONG_ENTRY': 32, 'RSI_SHORT_ENTRY': 68,
        'SL_GLOBAL_CAP_PCT': -0.06, 'TIER_MARGIN_PCT': 0.055,
        'LEVERAGE': 7, 'TRAILING_TP_ACTIVATE_ROI': 0.10, 'TRAILING_TP_CALLBACK_ROI': 0.03,
        'TIER_2_DEV_PCT': 0.012, 'TIER_3_DEV_PCT': 0.025,
        'MAX_ACTIVE_TRADES': 5, 'COOLDOWN_CANDLES': 8, 'SIGNAL_MODE': 'multi',
        'TP_MARGIN_ROI': 0.15, 'SL_MARGIN_ROI': -0.50,
    },
    {  # 8: ATR 2.5/1.5, classic, 10x — high lev + moderate ATR ratio
        'DYNAMIC_TPSL': True,
        'ATR_TP_MULT': 2.5, 'ATR_SL_MULT': 1.5,
        'ATR_TP_MIN_ROI': 0.10, 'ATR_TP_MAX_ROI': 0.35,
        'ATR_SL_MIN_ROI': -0.15, 'ATR_SL_MAX_ROI': -0.50,
        'RSI_LONG_ENTRY': 28, 'RSI_SHORT_ENTRY': 72,
        'SL_GLOBAL_CAP_PCT': -0.08, 'TIER_MARGIN_PCT': 0.040,
        'LEVERAGE': 10, 'TRAILING_TP_ACTIVATE_ROI': 0.12, 'TRAILING_TP_CALLBACK_ROI': 0.04,
        'TIER_2_DEV_PCT': 0.010, 'TIER_3_DEV_PCT': 0.025,
        'MAX_ACTIVE_TRADES': 4, 'COOLDOWN_CANDLES': 12, 'SIGNAL_MODE': 'classic',
        'TP_MARGIN_ROI': 0.20, 'SL_MARGIN_ROI': -0.40,
    },
    {  # 9: ATR 1.8/1.2, multi, 5x — moderate with wider RSI
        'DYNAMIC_TPSL': True,
        'ATR_TP_MULT': 1.8, 'ATR_SL_MULT': 1.2,
        'ATR_TP_MIN_ROI': 0.08, 'ATR_TP_MAX_ROI': 0.25,
        'ATR_SL_MIN_ROI': -0.12, 'ATR_SL_MAX_ROI': -0.40,
        'RSI_LONG_ENTRY': 35, 'RSI_SHORT_ENTRY': 65,
        'SL_GLOBAL_CAP_PCT': -0.08, 'TIER_MARGIN_PCT': 0.055,
        'LEVERAGE': 5, 'TRAILING_TP_ACTIVATE_ROI': 0.12, 'TRAILING_TP_CALLBACK_ROI': 0.04,
        'TIER_2_DEV_PCT': 0.012, 'TIER_3_DEV_PCT': 0.025,
        'MAX_ACTIVE_TRADES': 5, 'COOLDOWN_CANDLES': 12, 'SIGNAL_MODE': 'multi',
        'TP_MARGIN_ROI': 0.15, 'SL_MARGIN_ROI': -0.50,
    },
    {  # 10: Best-guess hybrid — ATR 2.5/1.2, classic, 7x
        'DYNAMIC_TPSL': True,
        'ATR_TP_MULT': 2.5, 'ATR_SL_MULT': 1.2,
        'ATR_TP_MIN_ROI': 0.10, 'ATR_TP_MAX_ROI': 0.35,
        'ATR_SL_MIN_ROI': -0.12, 'ATR_SL_MAX_ROI': -0.40,
        'RSI_LONG_ENTRY': 30, 'RSI_SHORT_ENTRY': 70,
        'SL_GLOBAL_CAP_PCT': -0.08, 'TIER_MARGIN_PCT': 0.055,
        'LEVERAGE': 7, 'TRAILING_TP_ACTIVATE_ROI': 0.12, 'TRAILING_TP_CALLBACK_ROI': 0.04,
        'TIER_2_DEV_PCT': 0.012, 'TIER_3_DEV_PCT': 0.025,
        'MAX_ACTIVE_TRADES': 5, 'COOLDOWN_CANDLES': 12, 'SIGNAL_MODE': 'classic',
        'TP_MARGIN_ROI': 0.15, 'SL_MARGIN_ROI': -0.50,
    },
]

PROFILE_NAMES = {
    1: 'Tight-ATR-Classic-5x',
    2: 'Balanced-ATR-Classic-5x',
    3: 'Wide-TP-ATR-Classic-5x',
    4: 'Aggressive-Ratio-Multi-7x',
    5: 'Tight-SL-ATR-Multi-7x',
    6: 'Wide-ATR-Classic-10x',
    7: 'VeryTight-SL-Multi-7x',
    8: 'HighLev-ATR-Classic-10x',
    9: 'Moderate-ATR-Multi-5x',
    10: 'Hybrid-BestGuess-7x',
}


def run_single_iteration(iteration_num, params, days=365):
    """Run a single backtest iteration with given parameters."""
    try:
        full_params = {
            'EMA_FAST': config.EMA_FAST,
            'EMA_SLOW': config.EMA_SLOW,
            'FUNDING_RATE': config.FUNDING_RATE,
            'FEE_RATE': config.FEE_RATE,
            'COMPOUND_MODE': config.COMPOUND_MODE,
            'BASE_CAPITAL': config.BASE_CAPITAL,
        }
        full_params.update(params)

        engine = BacktestEngine(days=days, param_overrides=full_params)
        engine.run()

        monthly_data = engine.get_monthly_pnl_report()
        closed_trades = [t for t in engine.trades if t['type'] == 'close']

        result = {
            'iteration': iteration_num,
            'params': params,
            'initial_balance': engine.initial_balance,
            'final_balance': engine.current_balance,
            'total_pnl': sum(t['pnl'] for t in closed_trades),
            'total_trades': len(closed_trades),
            'win_rate': (sum(1 for t in closed_trades if t['pnl'] > 0) / len(closed_trades) * 100) if closed_trades else 0,
            'max_drawdown': engine.max_drawdown * 100,
            'max_margin_usage': engine.max_margin_usage,
            'monthly_data': monthly_data,
        }

        if monthly_data:
            monthly_pnls = [m['net_pnl'] for m in monthly_data]
            result['avg_monthly_pnl'] = sum(monthly_pnls) / len(monthly_pnls)
            result['min_monthly_pnl'] = min(monthly_pnls)
            result['max_monthly_pnl'] = max(monthly_pnls)
            result['months_above_40'] = sum(1 for p in monthly_pnls if p >= 40)
            result['months_profitable'] = sum(1 for p in monthly_pnls if p > 0)
            result['total_months'] = len(monthly_pnls)
        else:
            result['avg_monthly_pnl'] = 0
            result['min_monthly_pnl'] = 0
            result['max_monthly_pnl'] = 0
            result['months_above_40'] = 0
            result['months_profitable'] = 0
            result['total_months'] = 0

        return result

    except Exception as e:
        import traceback
        return {
            'iteration': iteration_num,
            'params': params,
            'error': str(e),
            'traceback': traceback.format_exc(),
            'final_balance': 0,
            'total_pnl': 0,
            'total_trades': 0,
            'win_rate': 0,
            'max_drawdown': 100,
            'monthly_data': [],
            'avg_monthly_pnl': 0,
            'min_monthly_pnl': 0,
            'max_monthly_pnl': 0,
            'months_above_40': 0,
            'months_profitable': 0,
            'total_months': 0,
        }


def main():
    print("=" * 70)
    print("🚀 10-ITERATION DYNAMIC ATR TP/SL OPTIMIZER")
    print("=" * 70)
    print(f"Initial Capital: {config.BASE_CAPITAL} USDT")
    print(f"Backtest Period: 365 days")
    print(f"Symbols: {', '.join(config.SYMBOLS)}")
    print(f"Target: Monthly profit ≥ 40 USDT")
    print(f"Key innovation: ATR-based dynamic TP/SL per trade")
    print("=" * 70)

    all_results = []

    for i, params in enumerate(PARAM_SETS):
        iteration_num = i + 1
        sys.stdout.write(f"\r⏳ Running iteration {iteration_num}/10...")
        sys.stdout.flush()

        result = run_single_iteration(iteration_num, params, days=365)
        all_results.append(result)

        if 'error' in result:
            sys.stdout.write(f"\r❌ Iteration {iteration_num}/10 | ERROR: {result['error'][:60]}\n")
        elif result.get('total_trades', 0) > 0:
            sys.stdout.write(
                f"\r✅ Iteration {iteration_num}/10 | "
                f"PnL: {result['total_pnl']:+.2f} | "
                f"WR: {result['win_rate']:.0f}% | "
                f"Avg Monthly: {result['avg_monthly_pnl']:+.2f} | "
                f"DD: {result['max_drawdown']:.0f}%\n"
            )
        else:
            sys.stdout.write(f"\r⚠️ Iteration {iteration_num}/10 | No trades\n")

    # === DETAILED MONTHLY REPORTS ===
    print(f"\n\n{'=' * 70}")
    print("📋 DETAILED MONTHLY REPORTS")
    print(f"{'=' * 70}")
    for r in all_results:
        if r.get('total_trades', 0) > 0 and 'error' not in r:
            print_monthly_report(r)

    # === RANKING ===
    valid = [r for r in all_results if r.get('total_trades', 0) > 0 and 'error' not in r]
    if not valid:
        print("\n❌ No valid results.")
        return all_results

    print(f"\n\n{'=' * 70}")
    print("🏆 DYNAMIC ATR TP/SL OPTIMIZATION RANKINGS")
    print(f"{'=' * 70}")

    # Rank by Total PnL
    valid.sort(key=lambda x: x['total_pnl'], reverse=True)
    print(f"\n📈 RANKED BY TOTAL PnL:")
    for i, r in enumerate(valid):
        p = r['params']
        profile = PROFILE_NAMES.get(r['iteration'], 'Custom')
        star = " ⭐ BEST" if i == 0 else ""
        print(f"  #{i + 1} [{profile}] (Iter {r['iteration']}){star}")
        print(f"      PnL: {r['total_pnl']:+.2f} USDT | Final: {r['final_balance']:.2f} | "
              f"WR: {r['win_rate']:.1f}% | DD: {r['max_drawdown']:.1f}%")
        print(f"      ATR TP/SL: {p['ATR_TP_MULT']}/{p['ATR_SL_MULT']} | "
              f"Lev={p['LEVERAGE']}x | Mode={p['SIGNAL_MODE']} | "
              f"Avg Monthly: {r['avg_monthly_pnl']:+.2f}")

    # Composite score
    pnl_max = max(r['total_pnl'] for r in valid) or 1
    months_max = max(r['months_above_40'] for r in valid) or 1

    for r in valid:
        pnl_score = r['total_pnl'] / pnl_max if pnl_max > 0 else 0
        dd_score = 1 - (r['max_drawdown'] / 100)
        months_score = r['months_above_40'] / months_max if months_max > 0 else 0
        r['composite_score'] = pnl_score * 0.4 + dd_score * 0.3 + months_score * 0.3

    valid.sort(key=lambda x: x['composite_score'], reverse=True)
    best = valid[0]
    best_profile = PROFILE_NAMES.get(best['iteration'], 'Custom')

    print(f"\n{'=' * 70}")
    print(f"🏆 BEST DYNAMIC ATR STRATEGY: [{best_profile}] (Iteration {best['iteration']})")
    print(f"{'=' * 70}")
    print(f"  Composite Score: {best['composite_score']:.3f}")
    print(f"  Final Balance: {best['final_balance']:.2f} USDT (from {best['initial_balance']:.2f})")
    print(f"  Total PnL: {best['total_pnl']:+.2f} USDT")
    print(f"  Total Trades: {best['total_trades']} | Win Rate: {best['win_rate']:.1f}%")
    print(f"  Max Drawdown: {best['max_drawdown']:.1f}%")
    print(f"  Avg Monthly PnL: {best['avg_monthly_pnl']:+.2f} USDT")
    print(f"  Months ≥ 40 USDT: {best['months_above_40']}/{best['total_months']}")
    bp = best['params']
    print(f"\n  📋 RECOMMENDED DYNAMIC TP/SL CONFIG:")
    print(f"     DYNAMIC_TPSL = True")
    print(f"     ATR_TP_MULT = {bp['ATR_TP_MULT']}")
    print(f"     ATR_SL_MULT = {bp['ATR_SL_MULT']}")
    print(f"     ATR_TP_MIN_ROI = {bp['ATR_TP_MIN_ROI']}")
    print(f"     ATR_TP_MAX_ROI = {bp['ATR_TP_MAX_ROI']}")
    print(f"     ATR_SL_MIN_ROI = {bp['ATR_SL_MIN_ROI']}")
    print(f"     ATR_SL_MAX_ROI = {bp['ATR_SL_MAX_ROI']}")
    print(f"     LEVERAGE = {bp['LEVERAGE']}")
    print(f"     SIGNAL_MODE = '{bp['SIGNAL_MODE']}'")
    print(f"     RSI_LONG_ENTRY = {bp['RSI_LONG_ENTRY']}")
    print(f"     RSI_SHORT_ENTRY = {bp['RSI_SHORT_ENTRY']}")
    print(f"{'=' * 70}")

    return all_results


def print_monthly_report(result):
    """Print detailed monthly report for a single iteration."""
    print(f"\n{'=' * 60}")
    print(f"📅 ITERATION #{result['iteration']} - MONTHLY PERFORMANCE")
    profile = PROFILE_NAMES.get(result['iteration'], 'Custom')
    print(f"Profile: {profile}")
    params = result['params']
    print(f"ATR TP/SL: {params['ATR_TP_MULT']}/{params['ATR_SL_MULT']} "
          f"(TP bounds: {params['ATR_TP_MIN_ROI']*100:.0f}-{params['ATR_TP_MAX_ROI']*100:.0f}% | "
          f"SL bounds: {params['ATR_SL_MIN_ROI']*100:.0f} to {params['ATR_SL_MAX_ROI']*100:.0f}%)")
    print(f"Lev={params['LEVERAGE']}x, Margin={params['TIER_MARGIN_PCT'] * 100:.1f}%, "
          f"Mode={params['SIGNAL_MODE']}, RSI={params['RSI_LONG_ENTRY']}/{params['RSI_SHORT_ENTRY']}")
    print(f"{'=' * 60}")

    if not result['monthly_data']:
        print("  No trades executed.")
        return

    for m in result['monthly_data']:
        status = "✅" if m['net_pnl'] >= 40 else ("⚠️" if m['net_pnl'] > 0 else "❌")
        print(f"[{m['month']}] {status} PnL: {m['net_pnl']:+.2f} | "
              f"Trades: {m['trades']} ({m['wins']}W/{m['losses']}L) | "
              f"WR: {m['win_rate']:.0f}% | Balance: {m['end_balance']:.2f}")

    print(f"\n📊 Summary: {result['initial_balance']:.0f} → {result['final_balance']:.2f} USDT | "
          f"PnL: {result['total_pnl']:+.2f} | WR: {result['win_rate']:.1f}% | "
          f"DD: {result['max_drawdown']:.1f}% | Avg Monthly: {result['avg_monthly_pnl']:+.2f}")


if __name__ == "__main__":
    main()
