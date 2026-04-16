"""
optimize_100.py - 100-Iteration Backtest Optimizer with Monthly Analysis

Runs 100 parameter combinations over 1-year backtest data.
For each iteration:
  - Varies key strategy parameters (RSI thresholds, TP/SL, margin allocation, leverage)
  - Runs full 365-day backtest simulation
  - Records monthly PnL breakdown
  - Generates comprehensive analysis report

Target: Monthly profit > 40 USDT on 150 USDT initial capital

Realistic factors considered:
  - Trading fees (0.05% taker)
  - Funding rate (0.01% every 8h)
  - Slippage simulation
  - Cooldown after stop losses
  - Consecutive loss limits
  - Maximum drawdown tracking
  - Balance-based margin checking (can't trade with more than available)
"""

import itertools
import random
import logging
import pandas as pd
import sys
import os
import json
from datetime import datetime

# Suppress verbose logging during optimization
logging.getLogger().setLevel(logging.CRITICAL)

from src.engine_backtest import BacktestEngine
from src.config import config

# ============================================================
# Parameter Grid for 100 iterations
# ============================================================

# Define parameter ranges
PARAM_GRID = {
    'RSI_LONG_ENTRY': [28, 30, 32, 35],
    'RSI_SHORT_ENTRY': [65, 68, 70, 72],
    'TP_MARGIN_ROI': [0.12, 0.15, 0.18, 0.20],
    'SL_MARGIN_ROI': [-0.30, -0.40, -0.50, -0.60],
    'SL_GLOBAL_CAP_PCT': [-0.06, -0.08, -0.10, -0.12],
    'TIER_MARGIN_PCT': [0.045, 0.050, 0.055, 0.060],
    'LEVERAGE': [5, 7, 10],
    'TRAILING_TP_ACTIVATE_ROI': [0.10, 0.12, 0.15],
    'TRAILING_TP_CALLBACK_ROI': [0.03, 0.04, 0.05],
    'TIER_2_DEV_PCT': [0.010, 0.012, 0.015],
    'TIER_3_DEV_PCT': [0.020, 0.025, 0.030],
    'MAX_ACTIVE_TRADES': [4, 5],
    'COOLDOWN_CANDLES': [8, 12, 18],
    'SIGNAL_MODE': ['classic', 'multi'],
}

def generate_100_param_sets():
    """
    Generate 100 parameter combinations using stratified random sampling.
    Ensures diverse coverage of the parameter space.
    """
    param_sets = []
    random.seed(42)  # Reproducibility

    # Generate all combinations and sample 100
    keys = list(PARAM_GRID.keys())
    all_values = [PARAM_GRID[k] for k in keys]

    # Use random combinations (total space is huge, so we sample)
    for i in range(100):
        params = {}
        for key, values in PARAM_GRID.items():
            params[key] = random.choice(values)

        # Apply constraints:
        # Trailing callback must be less than trailing activate
        if params['TRAILING_TP_CALLBACK_ROI'] >= params['TRAILING_TP_ACTIVATE_ROI']:
            params['TRAILING_TP_CALLBACK_ROI'] = params['TRAILING_TP_ACTIVATE_ROI'] * 0.5

        # Tier 3 deviation must be greater than Tier 2
        if params['TIER_3_DEV_PCT'] <= params['TIER_2_DEV_PCT']:
            params['TIER_3_DEV_PCT'] = params['TIER_2_DEV_PCT'] * 2

        # Check margin safety: MAX_ACTIVE_TRADES * 3 tiers * TIER_MARGIN_PCT < 0.9
        max_utilization = params['MAX_ACTIVE_TRADES'] * 3 * params['TIER_MARGIN_PCT']
        if max_utilization > 0.85:
            params['TIER_MARGIN_PCT'] = 0.85 / (params['MAX_ACTIVE_TRADES'] * 3)

        param_sets.append(params)

    return param_sets


def run_single_iteration(iteration_num, params, days=365):
    """Run a single backtest iteration with given parameters."""
    try:
        # Ensure essential defaults are present
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

        # Calculate monthly profit stats
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
    print(f"Parameters: RSI L/S={params['RSI_LONG_ENTRY']}/{params['RSI_SHORT_ENTRY']}, "
          f"TP={params['TP_MARGIN_ROI']*100:.0f}%, SL={params['SL_MARGIN_ROI']*100:.0f}%, "
          f"Lev={params['LEVERAGE']}x, Margin={params['TIER_MARGIN_PCT']*100:.1f}%")
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


def print_summary_report(all_results):
    """Print summary across all 100 iterations."""
    print("\n" + "="*70)
    print("🏆 100-ITERATION OPTIMIZATION SUMMARY")
    print("="*70)

    # Filter out errored results
    valid = [r for r in all_results if 'error' not in r and r['total_trades'] > 0]

    if not valid:
        print("No valid results.")
        return

    # Sort by total PnL
    valid.sort(key=lambda x: x['total_pnl'], reverse=True)

    print(f"\nTotal valid iterations: {len(valid)}/100")
    print(f"\n{'='*70}")
    print("TOP 10 STRATEGIES BY TOTAL PnL:")
    print(f"{'='*70}")

    for i, r in enumerate(valid[:10]):
        p = r['params']
        print(f"\n🥇 #{i+1} (Iteration {r['iteration']})")
        print(f"   Final Balance: {r['final_balance']:.2f} USDT | PnL: {r['total_pnl']:+.2f} USDT")
        print(f"   Trades: {r['total_trades']} | Win Rate: {r['win_rate']:.1f}%")
        print(f"   Max DD: {r['max_drawdown']:.1f}% | Avg Monthly: {r['avg_monthly_pnl']:+.2f} USDT")
        print(f"   Months ≥ 40U: {r['months_above_40']}/{r['total_months']} | Profitable: {r['months_profitable']}/{r['total_months']}")
        print(f"   Params: RSI={p['RSI_LONG_ENTRY']}/{p['RSI_SHORT_ENTRY']}, TP={p['TP_MARGIN_ROI']*100:.0f}%, "
              f"SL={p['SL_MARGIN_ROI']*100:.0f}%, Lev={p['LEVERAGE']}x, "
              f"Margin={p['TIER_MARGIN_PCT']*100:.1f}%, "
              f"Trail={p['TRAILING_TP_ACTIVATE_ROI']*100:.0f}%/{p['TRAILING_TP_CALLBACK_ROI']*100:.0f}%")

    # Sort by months with ≥ 40 USDT
    valid.sort(key=lambda x: (x['months_above_40'], x['avg_monthly_pnl']), reverse=True)

    print(f"\n{'='*70}")
    print("TOP 10 STRATEGIES BY MONTHS ≥ 40 USDT:")
    print(f"{'='*70}")

    for i, r in enumerate(valid[:10]):
        p = r['params']
        print(f"\n🎯 #{i+1} (Iteration {r['iteration']})")
        print(f"   Months ≥ 40U: {r['months_above_40']}/{r['total_months']} | Avg Monthly: {r['avg_monthly_pnl']:+.2f} USDT")
        print(f"   Final Balance: {r['final_balance']:.2f} USDT | Total PnL: {r['total_pnl']:+.2f} USDT")
        print(f"   Win Rate: {r['win_rate']:.1f}% | Max DD: {r['max_drawdown']:.1f}%")

    # Sort by risk-adjusted return (Sharpe-like: avg_monthly / max_dd)
    for r in valid:
        if r['max_drawdown'] > 0 and r['avg_monthly_pnl'] > 0:
            r['risk_score'] = r['avg_monthly_pnl'] / r['max_drawdown']
        else:
            r['risk_score'] = 0

    valid.sort(key=lambda x: x['risk_score'], reverse=True)

    print(f"\n{'='*70}")
    print("TOP 10 RISK-ADJUSTED STRATEGIES (Avg Monthly PnL / Max Drawdown %):")
    print(f"{'='*70}")

    for i, r in enumerate(valid[:10]):
        p = r['params']
        print(f"\n⚖️ #{i+1} (Iteration {r['iteration']})")
        print(f"   Risk Score: {r['risk_score']:.3f}")
        print(f"   Avg Monthly: {r['avg_monthly_pnl']:+.2f} USDT | Max DD: {r['max_drawdown']:.1f}%")
        print(f"   Final Balance: {r['final_balance']:.2f} USDT | Win Rate: {r['win_rate']:.1f}%")

    # Overall statistics
    pnls = [r['total_pnl'] for r in valid]
    dds = [r['max_drawdown'] for r in valid]
    wrs = [r['win_rate'] for r in valid]
    avg_monthlies = [r['avg_monthly_pnl'] for r in valid]

    print(f"\n{'='*70}")
    print("📈 OVERALL STATISTICS ACROSS ALL ITERATIONS:")
    print(f"{'='*70}")
    print(f"  PnL:         Mean={sum(pnls)/len(pnls):+.2f}, Median={sorted(pnls)[len(pnls)//2]:+.2f}, "
          f"Best={max(pnls):+.2f}, Worst={min(pnls):+.2f}")
    print(f"  Win Rate:    Mean={sum(wrs)/len(wrs):.1f}%, Best={max(wrs):.1f}%, Worst={min(wrs):.1f}%")
    print(f"  Max DD:      Mean={sum(dds)/len(dds):.1f}%, Best={min(dds):.1f}%, Worst={max(dds):.1f}%")
    print(f"  Avg Monthly: Mean={sum(avg_monthlies)/len(avg_monthlies):+.2f}, Best={max(avg_monthlies):+.2f}")
    print(f"  Profitable iterations: {sum(1 for p in pnls if p > 0)}/{len(valid)}")
    print(f"  Iterations with all months > 0: {sum(1 for r in valid if r['months_profitable'] == r['total_months'] and r['total_months'] > 0)}/{len(valid)}")


def save_results_to_file(all_results, filename="optimization_report.txt"):
    """Save detailed results to a file."""
    with open(filename, 'w') as f:
        f.write(f"100-Iteration Backtest Optimization Report\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Initial Capital: {config.BASE_CAPITAL} USDT\n")
        f.write(f"Backtest Period: 365 days\n")
        f.write(f"Symbols: {', '.join(config.SYMBOLS)}\n")
        f.write(f"{'='*70}\n\n")

        for r in all_results:
            if 'error' in r:
                f.write(f"Iteration #{r['iteration']}: ERROR - {r['error']}\n\n")
                continue

            p = r['params']
            f.write(f"{'='*60}\n")
            f.write(f"ITERATION #{r['iteration']}\n")
            f.write(f"{'='*60}\n")
            f.write(f"Parameters:\n")
            f.write(f"  RSI Long/Short: {p['RSI_LONG_ENTRY']}/{p['RSI_SHORT_ENTRY']}\n")
            f.write(f"  TP/SL ROI: {p['TP_MARGIN_ROI']*100:.0f}% / {p['SL_MARGIN_ROI']*100:.0f}%\n")
            f.write(f"  Leverage: {p['LEVERAGE']}x\n")
            f.write(f"  Tier Margin: {p['TIER_MARGIN_PCT']*100:.1f}%\n")
            f.write(f"  Trailing TP: Activate {p['TRAILING_TP_ACTIVATE_ROI']*100:.0f}% / Callback {p['TRAILING_TP_CALLBACK_ROI']*100:.0f}%\n")
            f.write(f"  DCA Tiers: T2={p['TIER_2_DEV_PCT']*100:.1f}% / T3={p['TIER_3_DEV_PCT']*100:.1f}%\n")
            f.write(f"  Max Active: {p['MAX_ACTIVE_TRADES']} | Cooldown: {p['COOLDOWN_CANDLES']} candles\n")
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
    print("🚀 100-ITERATION BACKTEST OPTIMIZER")
    print("="*70)
    print(f"Initial Capital: {config.BASE_CAPITAL} USDT")
    print(f"Backtest Period: 365 days")
    print(f"Symbols: {', '.join(config.SYMBOLS)}")
    print(f"Target: Monthly profit ≥ 40 USDT")
    print("="*70)

    param_sets = generate_100_param_sets()
    all_results = []

    for i, params in enumerate(param_sets):
        iteration_num = i + 1
        sys.stdout.write(f"\r⏳ Running iteration {iteration_num}/100...")
        sys.stdout.flush()

        result = run_single_iteration(iteration_num, params, days=365)
        all_results.append(result)

        # Print brief progress
        if result.get('total_trades', 0) > 0:
            sys.stdout.write(
                f"\r✅ Iteration {iteration_num}/100 | "
                f"PnL: {result['total_pnl']:+.2f} | "
                f"WR: {result['win_rate']:.0f}% | "
                f"Avg Monthly: {result['avg_monthly_pnl']:+.2f} | "
                f"DD: {result['max_drawdown']:.0f}%\n"
            )
        else:
            sys.stdout.write(f"\r⚠️ Iteration {iteration_num}/100 | No trades\n")

    # Print monthly report for top 5 iterations
    valid = [r for r in all_results if r.get('total_trades', 0) > 0]
    valid.sort(key=lambda x: x['total_pnl'], reverse=True)

    print(f"\n\n{'='*70}")
    print("📋 DETAILED MONTHLY REPORTS FOR TOP 5 STRATEGIES")
    print(f"{'='*70}")

    for r in valid[:5]:
        print_monthly_report(r)

    # Print summary
    print_summary_report(all_results)

    # Save full report
    save_results_to_file(all_results)


if __name__ == "__main__":
    main()
