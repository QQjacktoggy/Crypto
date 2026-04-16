"""
Iterative Backtest Optimizer
============================
1. Runs a 365-day baseline backtest
2. Analyses monthly PnL, drawdown, win-rate
3. Adjusts parameters to fix weaknesses
4. Repeats for 5 iterations
5. Prints a comprehensive multi-iteration comparison report

Output files
------------
  iteration_results.csv   – per-iteration summary metrics
  monthly_comparison.csv  – monthly PnL for every iteration side-by-side
  comprehensive_report.txt – human-readable final report
"""

import sys
import os
import copy
import logging
import json
import textwrap
from datetime import datetime

import pandas as pd

# ── repo root on path ───────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import config
from src.engine_backtest import BacktestEngine

# silence noisy engine logs during optimisation
logging.getLogger("src.engine_backtest").setLevel(logging.CRITICAL)
logging.getLogger("src.signal_logic").setLevel(logging.CRITICAL)
logging.basicConfig(level=logging.WARNING, format="%(message)s")

# ── default parameter set (mirrors src/config.py) ───────────────────────────
DEFAULT_PARAMS = {
    "TIER_MARGIN_PCT":  0.03,
    "LEVERAGE":         4,
    "TP_MARGIN_ROI":    0.10,
    "SL_GLOBAL_CAP_PCT":-0.10,
    "RSI_LONG_ENTRY":   25,
    "RSI_SHORT_ENTRY":  75,
    "TIER_2_DEV_PCT":   0.015,
    "TIER_3_DEV_PCT":   0.030,
    "MAX_ACTIVE_TRADES":4,
}

DAYS = 365   # fixed 1-year horizon


# ────────────────────────────────────────────────────────────────────────────
# Helper: apply / restore config overrides
# ────────────────────────────────────────────────────────────────────────────
def _apply(params: dict):
    for k, v in params.items():
        setattr(config, k, v)


def _snapshot() -> dict:
    """Return current relevant config values."""
    return {k: getattr(config, k) for k in DEFAULT_PARAMS}


# ────────────────────────────────────────────────────────────────────────────
# Run one 365-day simulation and return rich result dict
# ────────────────────────────────────────────────────────────────────────────
def run_backtest(params: dict, label: str = "") -> dict:
    saved = _snapshot()
    try:
        _apply(params)
        engine = BacktestEngine(days=DAYS)
        engine.run()

        closed = [t for t in engine.trades if t["type"] == "close"]
        wins   = [t for t in closed if t["pnl"] > 0]
        losses = [t for t in closed if t["pnl"] <= 0]

        total_pnl  = sum(t["pnl"] for t in closed)
        win_rate   = (len(wins) / len(closed) * 100) if closed else 0.0
        mdd        = engine.max_drawdown * 100
        final_bal  = engine.current_balance
        max_margin = engine.max_margin_usage

        # monthly breakdown
        monthly = {}
        if closed:
            df = pd.DataFrame(closed)
            df["time"]  = pd.to_datetime(df["time"])
            df["month"] = df["time"].dt.to_period("M")

            for month, grp in df.groupby("month"):
                mkey = str(month)
                monthly[mkey] = {
                    "trades":   len(grp),
                    "wins":     int((grp["pnl"] > 0).sum()),
                    "losses":   int((grp["pnl"] <= 0).sum()),
                    "win_rate": float((grp["pnl"] > 0).mean() * 100),
                    "net_pnl":  float(grp["pnl"].sum()),
                }

        # avg win/loss sizes
        avg_win  = (sum(t["pnl"] for t in wins)   / len(wins))   if wins   else 0.0
        avg_loss = (sum(t["pnl"] for t in losses) / len(losses)) if losses else 0.0
        profit_factor = (-sum(t["pnl"] for t in wins) /
                         sum(t["pnl"] for t in losses)) if losses and sum(t["pnl"] for t in losses) != 0 else float("inf")

        # negative months count
        neg_months = sum(1 for v in monthly.values() if v["net_pnl"] < 0)

        return {
            "label":         label,
            "params":        copy.deepcopy(params),
            "total_pnl":     total_pnl,
            "final_balance": final_bal,
            "win_rate":      win_rate,
            "mdd_pct":       mdd,
            "max_margin":    max_margin,
            "trades":        len(closed),
            "avg_win":       avg_win,
            "avg_loss":      avg_loss,
            "profit_factor": profit_factor,
            "neg_months":    neg_months,
            "monthly":       monthly,
        }
    finally:
        _apply(saved)


# ────────────────────────────────────────────────────────────────────────────
# Parameter optimiser: analyse weaknesses → propose next params
# ────────────────────────────────────────────────────────────────────────────
def propose_next_params(current: dict, result: dict, iteration: int) -> dict:
    """
    Rule-based adaptive parameter tuning.
    Each iteration applies ONE primary fix strategy + minor tweaks.
    """
    p = copy.deepcopy(current)

    mdd       = result["mdd_pct"]
    wr        = result["win_rate"]
    pnl       = result["total_pnl"]
    neg_m     = result["neg_months"]
    avg_win   = result["avg_win"]
    avg_loss  = result["avg_loss"]
    pf        = result["profit_factor"]

    # ── decide primary strategy ─────────────────────────────────────────────
    # Priority 1: catastrophic drawdown → protect capital first
    if mdd > 60:
        p["TIER_MARGIN_PCT"]   = round(max(p["TIER_MARGIN_PCT"] - 0.005, 0.015), 4)
        p["SL_GLOBAL_CAP_PCT"] = round(max(p["SL_GLOBAL_CAP_PCT"] + 0.02, -0.25), 3)
        p["LEVERAGE"]          = max(p["LEVERAGE"] - 1, 2)

    # Priority 2: too many losing months → tighten entry quality
    elif neg_m >= 3:
        p["RSI_LONG_ENTRY"]  = max(p["RSI_LONG_ENTRY"]  - 2, 18)
        p["RSI_SHORT_ENTRY"] = min(p["RSI_SHORT_ENTRY"] + 2, 82)
        p["TIER_2_DEV_PCT"]  = round(p["TIER_2_DEV_PCT"] + 0.005, 3)

    # Priority 3: low win rate → more selective entries
    elif wr < 80:
        p["RSI_LONG_ENTRY"]  = max(p["RSI_LONG_ENTRY"]  - 3, 15)
        p["RSI_SHORT_ENTRY"] = min(p["RSI_SHORT_ENTRY"] + 3, 85)

    # Priority 4: high win rate but low PnL → push TP higher, add margin
    elif wr >= 85 and pnl < 80:
        p["TP_MARGIN_ROI"]   = round(min(p["TP_MARGIN_ROI"]  + 0.02, 0.25), 3)
        p["TIER_MARGIN_PCT"] = round(min(p["TIER_MARGIN_PCT"] + 0.005, 0.06), 4)

    # Priority 5: already profitable but profit factor weak → re-balance TP/SL
    elif 0 < pf < 1.5:
        p["TP_MARGIN_ROI"]   = round(min(p["TP_MARGIN_ROI"] + 0.03, 0.25), 3)
        p["SL_GLOBAL_CAP_PCT"] = round(max(p["SL_GLOBAL_CAP_PCT"] - 0.02, -0.20), 3)

    # Priority 6: everything is good → scale up slightly
    else:
        p["TIER_MARGIN_PCT"] = round(min(p["TIER_MARGIN_PCT"] + 0.003, 0.06), 4)
        p["TP_MARGIN_ROI"]   = round(min(p["TP_MARGIN_ROI"]  + 0.01, 0.25), 3)
        p["MAX_ACTIVE_TRADES"] = min(p["MAX_ACTIVE_TRADES"] + 1, 5)

    # ── always clamp to safe boundaries ─────────────────────────────────────
    p["LEVERAGE"]          = max(2, min(p["LEVERAGE"],          8))
    p["TIER_MARGIN_PCT"]   = max(0.015, min(p["TIER_MARGIN_PCT"],  0.07))
    p["TP_MARGIN_ROI"]     = max(0.06,  min(p["TP_MARGIN_ROI"],    0.30))
    p["SL_GLOBAL_CAP_PCT"] = max(-0.25, min(p["SL_GLOBAL_CAP_PCT"], -0.05))
    p["RSI_LONG_ENTRY"]    = max(15,    min(p["RSI_LONG_ENTRY"],   35))
    p["RSI_SHORT_ENTRY"]   = max(65,    min(p["RSI_SHORT_ENTRY"],  85))
    p["TIER_2_DEV_PCT"]    = max(0.01,  min(p["TIER_2_DEV_PCT"],   0.03))
    p["TIER_3_DEV_PCT"]    = round(p["TIER_2_DEV_PCT"] * 2, 3)          # keep tier-3 = 2× tier-2
    p["MAX_ACTIVE_TRADES"] = max(2, min(p["MAX_ACTIVE_TRADES"],    5))

    return p


# ────────────────────────────────────────────────────────────────────────────
# Report builders
# ────────────────────────────────────────────────────────────────────────────
def build_monthly_comparison(all_results: list) -> pd.DataFrame:
    """Wide DataFrame: rows = months, columns = iteration PnL values."""
    all_months = sorted(
        set(m for r in all_results for m in r["monthly"].keys())
    )
    rows = []
    for month in all_months:
        row = {"Month": month}
        for r in all_results:
            lbl = r["label"]
            row[f"{lbl}_pnl"]     = r["monthly"].get(month, {}).get("net_pnl",  0.0)
            row[f"{lbl}_wr"]      = r["monthly"].get(month, {}).get("win_rate", 0.0)
            row[f"{lbl}_trades"]  = r["monthly"].get(month, {}).get("trades",   0)
        rows.append(row)
    return pd.DataFrame(rows)


def print_separator(char="=", width=72):
    print(char * width)


def fmt_param_delta(prev: dict, curr: dict) -> str:
    changes = []
    for k in DEFAULT_PARAMS:
        pv, cv = prev.get(k), curr.get(k)
        if pv != cv:
            changes.append(f"  {k}: {pv} → {cv}")
    return "\n".join(changes) if changes else "  (no parameter changes)"


def write_comprehensive_report(all_results: list, monthly_df: pd.DataFrame,
                                report_path: str = "comprehensive_report.txt"):
    lines = []
    W = 72

    def add(s=""):
        lines.append(s)

    add("=" * W)
    add(" ITERATIVE BACKTEST OPTIMIZATION — COMPREHENSIVE REPORT")
    add(f" Generated : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    add(f" Horizon   : {DAYS} days  |  Symbols: {', '.join(config.SYMBOLS)}")
    add(f" Timeframe : {config.TIMEFRAME}  |  Initial Capital: {config.BASE_CAPITAL} USDT")
    add("=" * W)
    add()

    # ── iteration-by-iteration summary ──────────────────────────────────────
    add("━" * W)
    add("  ITERATION SUMMARY")
    add("━" * W)
    hdr = (f"{'Label':<18} {'Net PnL':>9} {'FinalBal':>10} {'WinRate':>9}"
           f" {'MDD%':>7} {'Trades':>7} {'NegMo':>6} {'PF':>6}")
    add(hdr)
    add("-" * W)

    for r in all_results:
        pf_str = f"{r['profit_factor']:.2f}" if r["profit_factor"] != float("inf") else "  ∞"
        row = (f"{r['label']:<18} {r['total_pnl']:>+9.2f} {r['final_balance']:>10.2f}"
               f" {r['win_rate']:>8.2f}% {r['mdd_pct']:>6.2f}% {r['trades']:>7}"
               f" {r['neg_months']:>6} {pf_str:>6}")
        add(row)
    add()

    # ── parameter evolution ─────────────────────────────────────────────────
    add("━" * W)
    add("  PARAMETER EVOLUTION")
    add("━" * W)
    for i, r in enumerate(all_results):
        p = r["params"]
        add(f"  [{r['label']}]")
        for k, v in p.items():
            add(f"    {k:<22} = {v}")
        if i > 0:
            add("  Changes vs previous iteration:")
            add(fmt_param_delta(all_results[i - 1]["params"], p))
        add()

    # ── monthly detail per iteration ────────────────────────────────────────
    add("━" * W)
    add("  MONTHLY TRADING DETAIL — BY ITERATION")
    add("━" * W)

    for r in all_results:
        add()
        add(f"  ── {r['label']} ──")
        add(f"  {'Month':<10} {'Trades':>7} {'W':>4} {'L':>4} {'WR%':>7} {'Net PnL':>10} {'Cum PnL':>10}")
        add("  " + "-" * 60)
        cum = 0.0
        for month in sorted(r["monthly"].keys()):
            m = r["monthly"][month]
            cum += m["net_pnl"]
            add(f"  {month:<10} {m['trades']:>7} {m['wins']:>4} {m['losses']:>4}"
                f" {m['win_rate']:>6.1f}% {m['net_pnl']:>+10.2f} {cum:>+10.2f}")

    add()

    # ── month-by-month PnL comparison across all iterations ─────────────────
    add("━" * W)
    add("  MONTH-BY-MONTH PnL COMPARISON (all iterations)")
    add("━" * W)
    labels   = [r["label"] for r in all_results]
    col_w    = 11
    hdr2     = f"  {'Month':<10}" + "".join(f" {lb:>{col_w}}" for lb in labels)
    add(hdr2)
    add("  " + "-" * (12 + col_w * len(labels)))

    for _, row in monthly_df.iterrows():
        line = f"  {row['Month']:<10}"
        for r in all_results:
            pnl_key = f"{r['label']}_pnl"
            v = row.get(pnl_key, 0.0)
            line += f" {v:>+{col_w}.2f}"
        add(line)

    add()

    # ── key takeaways ────────────────────────────────────────────────────────
    best_pnl = max(all_results, key=lambda r: r["total_pnl"])
    best_mdd = min(all_results, key=lambda r: r["mdd_pct"])
    best_wr  = max(all_results, key=lambda r: r["win_rate"])
    last     = all_results[-1]

    add("━" * W)
    add("  KEY TAKEAWAYS")
    add("━" * W)
    add(f"  Highest Net PnL     : {best_pnl['label']}  → {best_pnl['total_pnl']:+.2f} USDT")
    add(f"  Lowest Max Drawdown : {best_mdd['label']}  → {best_mdd['mdd_pct']:.2f}%")
    add(f"  Best Win Rate       : {best_wr['label']}   → {best_wr['win_rate']:.2f}%")
    add()
    add(f"  Final Optimised Parameters ({last['label']}):")
    for k, v in last["params"].items():
        add(f"    {k:<22} = {v}")
    add()
    add("  Recommendation:")
    if last["mdd_pct"] > 50:
        add("  ⚠  MDD still elevated. Further reduce TIER_MARGIN_PCT / LEVERAGE.")
    elif last["mdd_pct"] <= 25 and last["total_pnl"] > 50:
        add("  ✅ Strategy looks deployment-ready. Monitor live performance closely.")
    else:
        add("  ℹ  Good progress. Consider another optimisation round or live paper-trading.")
    add()
    add("=" * W)
    add(f" Report written to: {report_path}")
    add("=" * W)

    report_text = "\n".join(lines)

    # print to stdout
    print(report_text)

    # save to file
    with open(report_path, "w") as f:
        f.write(report_text)

    return report_text


# ────────────────────────────────────────────────────────────────────────────
# Main loop
# ────────────────────────────────────────────────────────────────────────────
def main():
    print("=" * 72)
    print(" ITERATIVE BACKTEST OPTIMIZER — 5 ITERATIONS × 365 DAYS")
    print("=" * 72)
    print()

    params      = copy.deepcopy(DEFAULT_PARAMS)
    all_results = []

    # ── Iteration 0: Baseline ───────────────────────────────────────────────
    NUM_ITERATIONS = 5   # baseline + 5 optimisation rounds = 6 total runs

    for iteration in range(NUM_ITERATIONS + 1):
        if iteration == 0:
            label = "Baseline"
        else:
            label = f"Iter_{iteration}"

        print(f"[{iteration}/{NUM_ITERATIONS}] Running {label}  (params below)")
        for k, v in params.items():
            print(f"         {k} = {v}")
        print()

        result = run_backtest(params, label=label)
        all_results.append(result)

        pf_disp = f"{result['profit_factor']:.2f}" if result["profit_factor"] != float("inf") else "∞"
        print(f"  → Net PnL: {result['total_pnl']:+.2f} USDT  |  "
              f"Balance: {result['final_balance']:.2f}  |  "
              f"WR: {result['win_rate']:.1f}%  |  "
              f"MDD: {result['mdd_pct']:.1f}%  |  "
              f"PF: {pf_disp}  |  "
              f"NegMonths: {result['neg_months']}")
        print()

        if iteration < NUM_ITERATIONS:
            params = propose_next_params(params, result, iteration)
            print(f"  → Proposed parameters for Iter_{iteration + 1}:")
            prev = all_results[-1]["params"]
            for k, v in params.items():
                marker = " ◄" if v != prev.get(k) else ""
                print(f"       {k:<22} = {v}{marker}")
            print()

    # ── Save CSVs ────────────────────────────────────────────────────────────
    summary_rows = []
    for r in all_results:
        row = {"label": r["label"], "total_pnl": r["total_pnl"],
               "final_balance": r["final_balance"], "win_rate": r["win_rate"],
               "mdd_pct": r["mdd_pct"], "trades": r["trades"],
               "avg_win": r["avg_win"], "avg_loss": r["avg_loss"],
               "profit_factor": r["profit_factor"], "neg_months": r["neg_months"]}
        row.update({f"param_{k}": v for k, v in r["params"].items()})
        summary_rows.append(row)

    df_summary = pd.DataFrame(summary_rows)
    df_summary.to_csv("iteration_results.csv", index=False)
    print("Saved  iteration_results.csv")

    monthly_df = build_monthly_comparison(all_results)
    monthly_df.to_csv("monthly_comparison.csv", index=False)
    print("Saved  monthly_comparison.csv")

    # ── Write final report ───────────────────────────────────────────────────
    print()
    write_comprehensive_report(all_results, monthly_df, "comprehensive_report.txt")


if __name__ == "__main__":
    main()
