"""
optimize_10.py - 10-Iteration Focused Backtest Optimizer

Runs 10 carefully designed parameter combinations over 1-year backtest data.
Each iteration explores a meaningfully different strategy profile:
  1-3:  Conservative (tight SL, lower leverage, classic signals)
  4-6:  Balanced (moderate risk/reward, mixed signals)
  7-9:  Aggressive (wider SL, higher leverage, multi signals)
  10:   Hybrid best-guess from known profitable ranges

Target: Monthly profit > 40 USDT on 150 USDT initial capital.
"""

import logging
import sys
import os
import json
from datetime import datetime

logging.getLogger().setLevel(logging.CRITICAL)

from src.engine_backtest import BacktestEngine
from src.config import config

# ============================================================
# 10 Manually Designed Parameter Sets
# ============================================================

PARAM_SETS = [
    # --- Conservative Profiles ---
    {  # 1: Classic RSI+BB, low leverage, tight SL
        'RSI_LONG_ENTRY': 28, 'RSI_SHORT_ENTRY': 72,
        'TP_MARGIN_ROI': 0.12, 'SL_MARGIN_ROI': -0.30,
        'SL_GLOBAL_CAP_PCT': -0.06, 'TIER_MARGIN_PCT': 0.045,
        'LEVERAGE': 5, 'TRAILING_TP_ACTIVATE_ROI': 0.10, 'TRAILING_TP_CALLBACK_ROI': 0.03,
        'TIER_2_DEV_PCT': 0.012, 'TIER_3_DEV_PCT': 0.025,
        'MAX_ACTIVE_TRADES': 4, 'COOLDOWN_CANDLES': 12, 'SIGNAL_MODE': 'classic',
    },
    {  # 2: Classic, moderate leverage, wider RSI
        'RSI_LONG_ENTRY': 32, 'RSI_SHORT_ENTRY': 68,
        'TP_MARGIN_ROI': 0.15, 'SL_MARGIN_ROI': -0.40,
        'SL_GLOBAL_CAP_PCT': -0.08, 'TIER_MARGIN_PCT': 0.050,
        'LEVERAGE': 5, 'TRAILING_TP_ACTIVATE_ROI': 0.12, 'TRAILING_TP_CALLBACK_ROI': 0.04,
        'TIER_2_DEV_PCT': 0.012, 'TIER_3_DEV_PCT': 0.025,
        'MAX_ACTIVE_TRADES': 5, 'COOLDOWN_CANDLES': 12, 'SIGNAL_MODE': 'classic',
    },
    {  # 3: Classic with tight trailing TP
        'RSI_LONG_ENTRY': 30, 'RSI_SHORT_ENTRY': 70,
        'TP_MARGIN_ROI': 0.18, 'SL_MARGIN_ROI': -0.50,
        'SL_GLOBAL_CAP_PCT': -0.08, 'TIER_MARGIN_PCT': 0.055,
        'LEVERAGE': 5, 'TRAILING_TP_ACTIVATE_ROI': 0.10, 'TRAILING_TP_CALLBACK_ROI': 0.03,
        'TIER_2_DEV_PCT': 0.015, 'TIER_3_DEV_PCT': 0.030,
        'MAX_ACTIVE_TRADES': 5, 'COOLDOWN_CANDLES': 8, 'SIGNAL_MODE': 'classic',
    },

    # --- Balanced Profiles ---
    {  # 4: Multi-signal, moderate everything
        'RSI_LONG_ENTRY': 32, 'RSI_SHORT_ENTRY': 68,
        'TP_MARGIN_ROI': 0.15, 'SL_MARGIN_ROI': -0.50,
        'SL_GLOBAL_CAP_PCT': -0.08, 'TIER_MARGIN_PCT': 0.055,
        'LEVERAGE': 5, 'TRAILING_TP_ACTIVATE_ROI': 0.12, 'TRAILING_TP_CALLBACK_ROI': 0.04,
        'TIER_2_DEV_PCT': 0.012, 'TIER_3_DEV_PCT': 0.025,
        'MAX_ACTIVE_TRADES': 5, 'COOLDOWN_CANDLES': 12, 'SIGNAL_MODE': 'multi',
    },
    {  # 5: Multi-signal, 7x leverage
        'RSI_LONG_ENTRY': 35, 'RSI_SHORT_ENTRY': 65,
        'TP_MARGIN_ROI': 0.15, 'SL_MARGIN_ROI': -0.40,
        'SL_GLOBAL_CAP_PCT': -0.10, 'TIER_MARGIN_PCT': 0.050,
        'LEVERAGE': 7, 'TRAILING_TP_ACTIVATE_ROI': 0.12, 'TRAILING_TP_CALLBACK_ROI': 0.04,
        'TIER_2_DEV_PCT': 0.010, 'TIER_3_DEV_PCT': 0.020,
        'MAX_ACTIVE_TRADES': 4, 'COOLDOWN_CANDLES': 12, 'SIGNAL_MODE': 'multi',
    },
    {  # 6: Multi-signal, wider DCA, long cooldown
        'RSI_LONG_ENTRY': 30, 'RSI_SHORT_ENTRY': 70,
        'TP_MARGIN_ROI': 0.20, 'SL_MARGIN_ROI': -0.60,
        'SL_GLOBAL_CAP_PCT': -0.10, 'TIER_MARGIN_PCT': 0.050,
        'LEVERAGE': 5, 'TRAILING_TP_ACTIVATE_ROI': 0.15, 'TRAILING_TP_CALLBACK_ROI': 0.05,
        'TIER_2_DEV_PCT': 0.015, 'TIER_3_DEV_PCT': 0.030,
        'MAX_ACTIVE_TRADES': 5, 'COOLDOWN_CANDLES': 18, 'SIGNAL_MODE': 'multi',
    },

    # --- Aggressive Profiles ---
    {  # 7: Multi, 10x leverage, aggressive entries
        'RSI_LONG_ENTRY': 35, 'RSI_SHORT_ENTRY': 65,
        'TP_MARGIN_ROI': 0.12, 'SL_MARGIN_ROI': -0.30,
        'SL_GLOBAL_CAP_PCT': -0.06, 'TIER_MARGIN_PCT': 0.045,
        'LEVERAGE': 10, 'TRAILING_TP_ACTIVATE_ROI': 0.10, 'TRAILING_TP_CALLBACK_ROI': 0.03,
        'TIER_2_DEV_PCT': 0.010, 'TIER_3_DEV_PCT': 0.020,
        'MAX_ACTIVE_TRADES': 4, 'COOLDOWN_CANDLES': 8, 'SIGNAL_MODE': 'multi',
    },
    {  # 8: 10x leverage, wider TP, classic signals
        'RSI_LONG_ENTRY': 28, 'RSI_SHORT_ENTRY': 72,
        'TP_MARGIN_ROI': 0.20, 'SL_MARGIN_ROI': -0.40,
        'SL_GLOBAL_CAP_PCT': -0.08, 'TIER_MARGIN_PCT': 0.040,
        'LEVERAGE': 10, 'TRAILING_TP_ACTIVATE_ROI': 0.15, 'TRAILING_TP_CALLBACK_ROI': 0.05,
        'TIER_2_DEV_PCT': 0.010, 'TIER_3_DEV_PCT': 0.025,
        'MAX_ACTIVE_TRADES': 4, 'COOLDOWN_CANDLES': 12, 'SIGNAL_MODE': 'classic',
    },
    {  # 9: 7x leverage, multi with short cooldown
        'RSI_LONG_ENTRY': 32, 'RSI_SHORT_ENTRY': 68,
        'TP_MARGIN_ROI': 0.18, 'SL_MARGIN_ROI': -0.50,
        'SL_GLOBAL_CAP_PCT': -0.12, 'TIER_MARGIN_PCT': 0.055,
        'LEVERAGE': 7, 'TRAILING_TP_ACTIVATE_ROI': 0.12, 'TRAILING_TP_CALLBACK_ROI': 0.04,
        'TIER_2_DEV_PCT': 0.012, 'TIER_3_DEV_PCT': 0.025,
        'MAX_ACTIVE_TRADES': 5, 'COOLDOWN_CANDLES': 8, 'SIGNAL_MODE': 'multi',
    },

    # --- Hybrid Best-Guess ---
    {  # 10: Best guess combining profitable ranges
        'RSI_LONG_ENTRY': 32, 'RSI_SHORT_ENTRY': 68,
        'TP_MARGIN_ROI': 0.15, 'SL_MARGIN_ROI': -0.50,
        'SL_GLOBAL_CAP_PCT': -0.08, 'TIER_MARGIN_PCT': 0.055,
        'LEVERAGE': 7, 'TRAILING_TP_ACTIVATE_ROI': 0.12, 'TRAILING_TP_CALLBACK_ROI': 0.04,
        'TIER_2_DEV_PCT': 0.012, 'TIER_3_DEV_PCT': 0.025,
        'MAX_ACTIVE_TRADES': 5, 'COOLDOWN_CANDLES': 12, 'SIGNAL_MODE': 'multi',
    },
]


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
            'min_monthly_pnl': 0,
            'max_monthly_pnl': 0,
            'months_above_40': 0,
            'months_profitable': 0,
            'total_months': 0,
        }


def print_monthly_report(result):
    """Print detailed monthly report for a single iteration."""
    print(f"\n{'='*60}")
    print(f"📅 ITERATION #{result['iteration']} - MONTHLY PERFORMANCE")
    print(f"{'='*60}")

    params = result['params']
    profile_names = {
        1: 'Conservative-A', 2: 'Conservative-B', 3: 'Conservative-C',
        4: 'Balanced-A', 5: 'Balanced-B', 6: 'Balanced-C',
        7: 'Aggressive-A', 8: 'Aggressive-B', 9: 'Aggressive-C',
        10: 'Hybrid-BestGuess',
    }
    profile = profile_names.get(result['iteration'], 'Custom')
    print(f"Profile: {profile}")
    print(f"Params: RSI L/S={params['RSI_LONG_ENTRY']}/{params['RSI_SHORT_ENTRY']}, "
          f"TP={params['TP_MARGIN_ROI']*100:.0f}%, SL={params['SL_MARGIN_ROI']*100:.0f}%, "
          f"Lev={params['LEVERAGE']}x, Margin={params['TIER_MARGIN_PCT']*100:.1f}%, "
          f"Mode={params['SIGNAL_MODE']}")
    print(f"{'='*60}")

    if not result['monthly_data']:
        print("  No trades executed.")
        return

    for m in result['monthly_data']:
        status = "✅" if m['net_pnl'] >= 40 else ("⚠️" if m['net_pnl'] > 0 else "❌")
        print(f"[{m['month']}] {status}")
        print(f"  • Trades: {m['trades']} ({m['wins']} W / {m['losses']} L)")
        print(f"  • Win Rate: {m['win_rate']:.1f}%")
        print(f"  • Monthly Net PnL: {m['net_pnl']:+.2f} USDT")
        print(f"  • Cumulative PnL: {m['cumulative_pnl']:+.2f} USDT")
        print(f"  • Balance: {m['end_balance']:.2f} USDT")
        print(f"  {'-'*30}")

    print(f"\n📊 Summary:")
    print(f"  Initial: {result['initial_balance']:.2f} → Final: {result['final_balance']:.2f} USDT")
    print(f"  Total PnL: {result['total_pnl']:+.2f} USDT | Trades: {result['total_trades']}")
    print(f"  Win Rate: {result['win_rate']:.1f}% | Max Drawdown: {result['max_drawdown']:.1f}%")
    print(f"  Avg Monthly PnL: {result['avg_monthly_pnl']:+.2f} USDT")
    print(f"  Months ≥ 40 USDT: {result['months_above_40']}/{result['total_months']}")
    print(f"  Months Profitable: {result['months_profitable']}/{result['total_months']}")


def save_results(all_results, filename="optimization_10_report.txt"):
    """Save results to a file."""
    with open(filename, 'w') as f:
        f.write(f"10-Iteration Focused Backtest Optimization Report\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Initial Capital: {config.BASE_CAPITAL} USDT\n")
        f.write(f"Backtest Period: 365 days\n")
        f.write(f"Symbols: {', '.join(config.SYMBOLS)}\n")
        f.write(f"{'='*70}\n\n")

        profile_names = {
            1: 'Conservative-A', 2: 'Conservative-B', 3: 'Conservative-C',
            4: 'Balanced-A', 5: 'Balanced-B', 6: 'Balanced-C',
            7: 'Aggressive-A', 8: 'Aggressive-B', 9: 'Aggressive-C',
            10: 'Hybrid-BestGuess',
        }

        for r in all_results:
            if 'error' in r:
                f.write(f"Iteration #{r['iteration']}: ERROR - {r['error']}\n\n")
                continue

            p = r['params']
            profile = profile_names.get(r['iteration'], 'Custom')
            f.write(f"{'='*60}\n")
            f.write(f"ITERATION #{r['iteration']} - {profile}\n")
            f.write(f"{'='*60}\n")
            f.write(f"Parameters:\n")
            f.write(f"  RSI Long/Short: {p['RSI_LONG_ENTRY']}/{p['RSI_SHORT_ENTRY']}\n")
            f.write(f"  TP/SL ROI: {p['TP_MARGIN_ROI']*100:.0f}% / {p['SL_MARGIN_ROI']*100:.0f}%\n")
            f.write(f"  Leverage: {p['LEVERAGE']}x\n")
            f.write(f"  Tier Margin: {p['TIER_MARGIN_PCT']*100:.1f}%\n")
            f.write(f"  Trailing TP: {p['TRAILING_TP_ACTIVATE_ROI']*100:.0f}%/{p['TRAILING_TP_CALLBACK_ROI']*100:.0f}%\n")
            f.write(f"  DCA: T2={p['TIER_2_DEV_PCT']*100:.1f}% / T3={p['TIER_3_DEV_PCT']*100:.1f}%\n")
            f.write(f"  Max Trades: {p['MAX_ACTIVE_TRADES']} | Cooldown: {p['COOLDOWN_CANDLES']}\n")
            f.write(f"  Signal Mode: {p['SIGNAL_MODE']}\n")
            f.write(f"  SL Global Cap: {p['SL_GLOBAL_CAP_PCT']*100:.1f}%\n")
            f.write(f"\nResults:\n")
            f.write(f"  Initial: {r['initial_balance']:.2f} USDT\n")
            f.write(f"  Final: {r['final_balance']:.2f} USDT\n")
            f.write(f"  Total PnL: {r['total_pnl']:+.2f} USDT\n")
            f.write(f"  Trades: {r['total_trades']} | Win Rate: {r['win_rate']:.1f}%\n")
            f.write(f"  Max Drawdown: {r['max_drawdown']:.1f}%\n")
            f.write(f"  Avg Monthly PnL: {r['avg_monthly_pnl']:+.2f} USDT\n")
            f.write(f"  Months >= 40 USDT: {r['months_above_40']}/{r['total_months']}\n")

            f.write(f"\nMonthly Breakdown:\n")
            for m in r.get('monthly_data', []):
                status = "✅" if m['net_pnl'] >= 40 else ("⚠️" if m['net_pnl'] > 0 else "❌")
                f.write(f"  [{m['month']}] {status} PnL: {m['net_pnl']:+.2f} | "
                        f"Trades: {m['trades']} ({m['wins']}W/{m['losses']}L) | "
                        f"WR: {m['win_rate']:.0f}% | Balance: {m['end_balance']:.2f}\n")
            f.write(f"\n")

    print(f"\n✅ Full report saved to: {filename}")


def main():
    print("="*70)
    print("🚀 10-ITERATION FOCUSED BACKTEST OPTIMIZER")
    print("="*70)
    print(f"Initial Capital: {config.BASE_CAPITAL} USDT")
    print(f"Backtest Period: 365 days")
    print(f"Symbols: {', '.join(config.SYMBOLS)}")
    print(f"Target: Monthly profit ≥ 40 USDT")
    print(f"Profiles: Conservative(1-3), Balanced(4-6), Aggressive(7-9), Hybrid(10)")
    print("="*70)

    all_results = []

    for i, params in enumerate(PARAM_SETS):
        iteration_num = i + 1
        sys.stdout.write(f"\r⏳ Running iteration {iteration_num}/10...")
        sys.stdout.flush()

        result = run_single_iteration(iteration_num, params, days=365)
        all_results.append(result)

        if result.get('total_trades', 0) > 0:
            sys.stdout.write(
                f"\r✅ Iteration {iteration_num}/10 | "
                f"PnL: {result['total_pnl']:+.2f} | "
                f"WR: {result['win_rate']:.0f}% | "
                f"Avg Monthly: {result['avg_monthly_pnl']:+.2f} | "
                f"DD: {result['max_drawdown']:.0f}%\n"
            )
        else:
            sys.stdout.write(f"\r⚠️ Iteration {iteration_num}/10 | No trades\n")

    # Print monthly reports for all iterations
    print(f"\n\n{'='*70}")
    print("📋 DETAILED MONTHLY REPORTS FOR ALL 10 STRATEGIES")
    print(f"{'='*70}")
    for r in all_results:
        if r.get('total_trades', 0) > 0:
            print_monthly_report(r)

    # === RANKING ===
    valid = [r for r in all_results if r.get('total_trades', 0) > 0 and 'error' not in r]
    if not valid:
        print("\n❌ No valid results.")
        return

    print(f"\n\n{'='*70}")
    print("🏆 10-ITERATION OPTIMIZATION RANKINGS")
    print(f"{'='*70}")

    profile_names = {
        1: 'Conservative-A', 2: 'Conservative-B', 3: 'Conservative-C',
        4: 'Balanced-A', 5: 'Balanced-B', 6: 'Balanced-C',
        7: 'Aggressive-A', 8: 'Aggressive-B', 9: 'Aggressive-C',
        10: 'Hybrid-BestGuess',
    }

    # Rank by Total PnL
    valid.sort(key=lambda x: x['total_pnl'], reverse=True)
    print(f"\n📈 RANKED BY TOTAL PnL:")
    for i, r in enumerate(valid):
        p = r['params']
        profile = profile_names.get(r['iteration'], 'Custom')
        star = " ⭐ BEST" if i == 0 else ""
        print(f"  #{i+1} [{profile}] (Iter {r['iteration']}){star}")
        print(f"      PnL: {r['total_pnl']:+.2f} USDT | Final: {r['final_balance']:.2f} | "
              f"WR: {r['win_rate']:.1f}% | DD: {r['max_drawdown']:.1f}%")
        print(f"      Avg Monthly: {r['avg_monthly_pnl']:+.2f} | "
              f"Months≥40U: {r['months_above_40']}/{r['total_months']} | "
              f"Lev={p['LEVERAGE']}x Mode={p['SIGNAL_MODE']}")

    # Rank by Risk Score (avg monthly / max DD)
    for r in valid:
        if r['max_drawdown'] > 0 and r['avg_monthly_pnl'] > 0:
            r['risk_score'] = r['avg_monthly_pnl'] / r['max_drawdown']
        else:
            r['risk_score'] = 0

    valid.sort(key=lambda x: x['risk_score'], reverse=True)
    print(f"\n⚖️ RANKED BY RISK-ADJUSTED RETURN (Avg Monthly / Max DD):")
    for i, r in enumerate(valid):
        profile = profile_names.get(r['iteration'], 'Custom')
        star = " ⭐ BEST" if i == 0 else ""
        print(f"  #{i+1} [{profile}] Risk Score: {r['risk_score']:.3f}{star}")
        print(f"      Avg Monthly: {r['avg_monthly_pnl']:+.2f} | DD: {r['max_drawdown']:.1f}% | "
              f"PnL: {r['total_pnl']:+.2f}")

    # Rank by months above 40 USDT
    valid.sort(key=lambda x: (x['months_above_40'], x['avg_monthly_pnl']), reverse=True)
    print(f"\n🎯 RANKED BY MONTHS ≥ 40 USDT:")
    for i, r in enumerate(valid):
        profile = profile_names.get(r['iteration'], 'Custom')
        star = " ⭐ BEST" if i == 0 else ""
        print(f"  #{i+1} [{profile}] Months≥40U: {r['months_above_40']}/{r['total_months']}{star}")
        print(f"      Avg Monthly: {r['avg_monthly_pnl']:+.2f} | PnL: {r['total_pnl']:+.2f} | "
              f"WR: {r['win_rate']:.1f}%")

    # === BEST OVERALL RECOMMENDATION ===
    # Composite score: normalize and combine
    pnl_max = max(r['total_pnl'] for r in valid) or 1
    dd_min = min(r['max_drawdown'] for r in valid) or 1
    months_max = max(r['months_above_40'] for r in valid) or 1

    for r in valid:
        pnl_score = r['total_pnl'] / pnl_max if pnl_max > 0 else 0
        dd_score = 1 - (r['max_drawdown'] / 100)  # lower DD is better
        months_score = r['months_above_40'] / months_max if months_max > 0 else 0
        r['composite_score'] = pnl_score * 0.4 + dd_score * 0.3 + months_score * 0.3

    valid.sort(key=lambda x: x['composite_score'], reverse=True)
    best = valid[0]
    best_profile = profile_names.get(best['iteration'], 'Custom')

    print(f"\n{'='*70}")
    print(f"🏆 BEST OVERALL STRATEGY: [{best_profile}] (Iteration {best['iteration']})")
    print(f"{'='*70}")
    print(f"  Composite Score: {best['composite_score']:.3f}")
    print(f"  Final Balance: {best['final_balance']:.2f} USDT (from {best['initial_balance']:.2f})")
    print(f"  Total PnL: {best['total_pnl']:+.2f} USDT")
    print(f"  Total Trades: {best['total_trades']} | Win Rate: {best['win_rate']:.1f}%")
    print(f"  Max Drawdown: {best['max_drawdown']:.1f}%")
    print(f"  Avg Monthly PnL: {best['avg_monthly_pnl']:+.2f} USDT")
    print(f"  Months ≥ 40 USDT: {best['months_above_40']}/{best['total_months']}")
    print(f"  Months Profitable: {best['months_profitable']}/{best['total_months']}")
    bp = best['params']
    print(f"\n  📋 RECOMMENDED CONFIG:")
    print(f"     RSI_LONG_ENTRY = {bp['RSI_LONG_ENTRY']}")
    print(f"     RSI_SHORT_ENTRY = {bp['RSI_SHORT_ENTRY']}")
    print(f"     TP_MARGIN_ROI = {bp['TP_MARGIN_ROI']}")
    print(f"     SL_MARGIN_ROI = {bp['SL_MARGIN_ROI']}")
    print(f"     SL_GLOBAL_CAP_PCT = {bp['SL_GLOBAL_CAP_PCT']}")
    print(f"     TIER_MARGIN_PCT = {bp['TIER_MARGIN_PCT']}")
    print(f"     LEVERAGE = {bp['LEVERAGE']}")
    print(f"     TRAILING_TP_ACTIVATE_ROI = {bp['TRAILING_TP_ACTIVATE_ROI']}")
    print(f"     TRAILING_TP_CALLBACK_ROI = {bp['TRAILING_TP_CALLBACK_ROI']}")
    print(f"     TIER_2_DEV_PCT = {bp['TIER_2_DEV_PCT']}")
    print(f"     TIER_3_DEV_PCT = {bp['TIER_3_DEV_PCT']}")
    print(f"     MAX_ACTIVE_TRADES = {bp['MAX_ACTIVE_TRADES']}")
    print(f"     COOLDOWN_CANDLES = {bp['COOLDOWN_CANDLES']}")
    print(f"     SIGNAL_MODE = '{bp['SIGNAL_MODE']}'")
    print(f"{'='*70}")

    save_results(all_results)


if __name__ == "__main__":
    main()
