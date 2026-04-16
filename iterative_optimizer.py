"""
Iterative Backtest Optimizer v2
===============================
Compound-interest aware, multi-dimensional parameter search.

1. Runs a 365-day baseline backtest (COMPOUND_MODE = True)
2. Analyses monthly PnL, drawdown, win-rate, profit factor
3. Keeps the BEST result seen so far and explores a NEW axis each iteration
4. Repeats for 10 iterations (11 total runs including baseline)
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
NUM_ITERATIONS = 10  # baseline + 10 optimisation rounds = 11 total runs

# ── parameter boundaries ────────────────────────────────────────────────────
BOUNDS = {
    "TIER_MARGIN_PCT":   (0.015, 0.08),
    "LEVERAGE":          (2, 8),
    "TP_MARGIN_ROI":     (0.05, 0.30),
    "SL_GLOBAL_CAP_PCT": (-0.25, -0.04),
    "RSI_LONG_ENTRY":    (15, 35),
    "RSI_SHORT_ENTRY":   (65, 85),
    "TIER_2_DEV_PCT":    (0.008, 0.03),
    "MAX_ACTIVE_TRADES": (2, 6),
}


# ────────────────────────────────────────────────────────────────────────────
# Helper: apply / restore config overrides
# ────────────────────────────────────────────────────────────────────────────
def _apply(params: dict):
    for k, v in params.items():
        setattr(config, k, v)


def _snapshot() -> dict:
    return {k: getattr(config, k) for k in DEFAULT_PARAMS}


def _clamp(p: dict) -> dict:
    """Clamp all parameters to their safe boundaries."""
    for k, (lo, hi) in BOUNDS.items():
        if k in p:
            if isinstance(p[k], int):
                p[k] = max(lo, min(int(p[k]), hi))
            else:
                p[k] = round(max(lo, min(p[k], hi)), 4)
    # keep tier-3 = 2x tier-2
    p["TIER_3_DEV_PCT"] = round(p["TIER_2_DEV_PCT"] * 2, 4)
    # RSI pair must stay symmetric
    p["RSI_SHORT_ENTRY"] = max(p["RSI_SHORT_ENTRY"], 100 - p["RSI_LONG_ENTRY"])
    return p


# ────────────────────────────────────────────────────────────────────────────
# Score function: balances PnL, drawdown, and consistency
# ────────────────────────────────────────────────────────────────────────────
def score(r: dict) -> float:
    """
    Composite score: higher is better.
    Rewards net PnL and win rate, penalises drawdown and negative months.
    """
    pnl_score = r["total_pnl"]
    mdd_penalty = -r["mdd_pct"] * 1.5          # heavy penalty on drawdown
    wr_bonus = (r["win_rate"] - 90) * 2         # bonus above 90% WR
    neg_penalty = -r["neg_months"] * 5          # penalty per negative month
    pf_bonus = min(r["profit_factor"], 5) * 10  # cap PF contribution
    return pnl_score + mdd_penalty + wr_bonus + neg_penalty + pf_bonus


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

        avg_win  = (sum(t["pnl"] for t in wins)   / len(wins))   if wins   else 0.0
        avg_loss = (sum(t["pnl"] for t in losses) / len(losses)) if losses else 0.0
        total_loss = sum(t["pnl"] for t in losses)
        profit_factor = (-sum(t["pnl"] for t in wins) / total_loss) if total_loss != 0 else float("inf")

        neg_months = sum(1 for v in monthly.values() if v["net_pnl"] < 0)

        roi_pct = ((final_bal - engine.initial_balance) / engine.initial_balance) * 100

        return {
            "label":         label,
            "params":        copy.deepcopy(params),
            "total_pnl":     total_pnl,
            "final_balance": final_bal,
            "roi_pct":       roi_pct,
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
# Multi-dimensional parameter optimiser
# ────────────────────────────────────────────────────────────────────────────

# 10 distinct exploration strategies — one per iteration
STRATEGIES = [
    "raise_tp",           # 1: raise TP target to capture more per win
    "tighten_sl",         # 2: tighten global SL cap for capital protection
    "boost_margin",       # 3: increase position size for compound growth
    "add_leverage",       # 4: increase leverage for amplified returns
    "relax_rsi",          # 5: relax RSI thresholds for more trade opportunities
    "widen_dca",          # 6: wider DCA tiers to average at better prices
    "narrow_dca",         # 7: narrow DCA tiers to recover faster
    "max_trades_up",      # 8: allow more concurrent trades
    "aggressive_combo",   # 9: combine TP + margin + leverage push
    "conservative_combo", # 10: reduce risk across the board
]

def propose_next_params(best_params: dict, best_result: dict,
                        current_result: dict, iteration: int) -> dict:
    """
    Each iteration explores a DIFFERENT axis from the best-seen params.
    If the current iteration worsened things, we revert to best and try
    a different strategy. No stuck-in-a-rut loops.
    """
    # always start from the best-known parameters
    p = copy.deepcopy(best_params)

    strategy = STRATEGIES[(iteration - 1) % len(STRATEGIES)]
    mdd = best_result["mdd_pct"]
    wr  = best_result["win_rate"]
    pf  = best_result["profit_factor"]

    if strategy == "raise_tp":
        p["TP_MARGIN_ROI"] = round(p["TP_MARGIN_ROI"] + 0.03, 3)

    elif strategy == "tighten_sl":
        p["SL_GLOBAL_CAP_PCT"] = round(p["SL_GLOBAL_CAP_PCT"] + 0.02, 3)

    elif strategy == "boost_margin":
        p["TIER_MARGIN_PCT"] = round(p["TIER_MARGIN_PCT"] + 0.01, 4)

    elif strategy == "add_leverage":
        p["LEVERAGE"] = p["LEVERAGE"] + 1

    elif strategy == "relax_rsi":
        p["RSI_LONG_ENTRY"]  = p["RSI_LONG_ENTRY"]  + 3
        p["RSI_SHORT_ENTRY"] = p["RSI_SHORT_ENTRY"] - 3

    elif strategy == "widen_dca":
        p["TIER_2_DEV_PCT"] = round(p["TIER_2_DEV_PCT"] + 0.005, 4)

    elif strategy == "narrow_dca":
        p["TIER_2_DEV_PCT"] = round(p["TIER_2_DEV_PCT"] - 0.003, 4)

    elif strategy == "max_trades_up":
        p["MAX_ACTIVE_TRADES"] = p["MAX_ACTIVE_TRADES"] + 1

    elif strategy == "aggressive_combo":
        p["TP_MARGIN_ROI"]   = round(p["TP_MARGIN_ROI"]   + 0.02, 3)
        p["TIER_MARGIN_PCT"] = round(p["TIER_MARGIN_PCT"] + 0.008, 4)
        p["LEVERAGE"]        = p["LEVERAGE"] + 1

    elif strategy == "conservative_combo":
        p["TIER_MARGIN_PCT"]   = round(p["TIER_MARGIN_PCT"]   - 0.005, 4)
        p["LEVERAGE"]          = max(p["LEVERAGE"] - 1, 2)
        p["SL_GLOBAL_CAP_PCT"] = round(p["SL_GLOBAL_CAP_PCT"] + 0.02, 3)
        p["TP_MARGIN_ROI"]     = round(p["TP_MARGIN_ROI"]     - 0.01, 3)

    p = _clamp(p)
    return p, strategy


# ────────────────────────────────────────────────────────────────────────────
# Report builders
# ────────────────────────────────────────────────────────────────────────────
def build_monthly_comparison(all_results: list) -> pd.DataFrame:
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


def fmt_param_delta(prev: dict, curr: dict) -> str:
    changes = []
    for k in DEFAULT_PARAMS:
        pv, cv = prev.get(k), curr.get(k)
        if pv != cv:
            changes.append(f"  {k}: {pv} -> {cv}")
    return "\n".join(changes) if changes else "  (no parameter changes)"


def write_comprehensive_report(all_results: list, best_result: dict,
                                monthly_df: pd.DataFrame,
                                report_path: str = "comprehensive_report.txt"):
    lines = []
    W = 80

    def add(s=""):
        lines.append(s)

    add("=" * W)
    add("  ITERATIVE BACKTEST OPTIMIZATION v2 — COMPREHENSIVE REPORT")
    add(f"  Generated : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    add(f"  Horizon   : {DAYS} days  |  Symbols: {', '.join(config.SYMBOLS)}")
    add(f"  Timeframe : {config.TIMEFRAME}  |  Initial Capital: {config.BASE_CAPITAL} USDT")
    add(f"  Mode      : COMPOUND INTEREST (profits reinvested each trade)")
    add("=" * W)
    add()

    # ── iteration summary table ──────────────────────────────────────────────
    add("=" * W)
    add("  ITERATION SUMMARY")
    add("=" * W)
    hdr = (f"{'Label':<15} {'Net PnL':>9} {'FinalBal':>9} {'ROI%':>8}"
           f" {'WR%':>7} {'MDD%':>7} {'Trades':>6} {'NegMo':>5} {'PF':>6} {'Score':>7}")
    add(hdr)
    add("-" * W)

    for r in all_results:
        pf_str = f"{r['profit_factor']:.2f}" if r["profit_factor"] != float("inf") else "  inf"
        sc = score(r)
        best_mark = " <-- BEST" if r["label"] == best_result["label"] else ""
        row = (f"{r['label']:<15} {r['total_pnl']:>+9.2f} {r['final_balance']:>9.2f}"
               f" {r['roi_pct']:>+7.1f}% {r['win_rate']:>6.1f}% {r['mdd_pct']:>6.1f}%"
               f" {r['trades']:>6} {r['neg_months']:>5} {pf_str:>6} {sc:>+7.1f}{best_mark}")
        add(row)
    add()

    # ── compound growth analysis ─────────────────────────────────────────────
    add("=" * W)
    add("  COMPOUND GROWTH ANALYSIS (Best: %s)" % best_result["label"])
    add("=" * W)
    add(f"  Initial Capital    : {config.BASE_CAPITAL:.2f} USDT")
    add(f"  Final Balance      : {best_result['final_balance']:.2f} USDT")
    add(f"  Net PnL (trades)   : {best_result['total_pnl']:+.2f} USDT")
    add(f"  ROI                : {best_result['roi_pct']:+.1f}%")
    add(f"  Max Drawdown       : {best_result['mdd_pct']:.1f}%")
    add(f"  Max Margin Usage   : {best_result['max_margin']:.2f} USDT")
    add(f"  Win Rate           : {best_result['win_rate']:.1f}%")
    pf_disp = f"{best_result['profit_factor']:.2f}" if best_result["profit_factor"] != float("inf") else "inf"
    add(f"  Profit Factor      : {pf_disp}")
    add(f"  Total Trades       : {best_result['trades']}")
    add(f"  Negative Months    : {best_result['neg_months']}")
    add()

    # ── parameter evolution ─────────────────────────────────────────────────
    add("=" * W)
    add("  PARAMETER EVOLUTION")
    add("=" * W)
    for i, r in enumerate(all_results):
        p = r["params"]
        strat = r.get("strategy", "-")
        sc = score(r)
        add(f"  [{r['label']}]  strategy={strat}  score={sc:+.1f}")
        for k, v in p.items():
            add(f"    {k:<22} = {v}")
        if i > 0:
            add("  Changes vs previous:")
            add(fmt_param_delta(all_results[i - 1]["params"], p))
        add()

    # ── monthly detail for BEST iteration ───────────────────────────────────
    add("=" * W)
    add("  MONTHLY DETAIL — BEST ITERATION: %s" % best_result["label"])
    add("=" * W)
    add(f"  {'Month':<10} {'Trades':>7} {'W':>4} {'L':>4} {'WR%':>7} {'Net PnL':>10} {'Cum PnL':>10}")
    add("  " + "-" * 62)
    cum = 0.0
    for month in sorted(best_result["monthly"].keys()):
        m = best_result["monthly"][month]
        cum += m["net_pnl"]
        add(f"  {month:<10} {m['trades']:>7} {m['wins']:>4} {m['losses']:>4}"
            f" {m['win_rate']:>6.1f}% {m['net_pnl']:>+10.2f} {cum:>+10.2f}")
    add()

    # ── month-by-month PnL comparison ────────────────────────────────────────
    add("=" * W)
    add("  MONTH-BY-MONTH PnL COMPARISON (all iterations)")
    add("=" * W)
    # show Baseline, best, and a few interesting ones
    labels = [r["label"] for r in all_results]
    col_w = 10
    hdr2 = f"  {'Month':<10}" + "".join(f" {lb:>{col_w}}" for lb in labels)
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
    best_pnl_r = max(all_results, key=lambda r: r["total_pnl"])
    best_mdd_r = min(all_results, key=lambda r: r["mdd_pct"])
    best_wr_r  = max(all_results, key=lambda r: r["win_rate"])
    best_sc_r  = max(all_results, key=score)

    add("=" * W)
    add("  KEY TAKEAWAYS & RECOMMENDED PARAMETERS")
    add("=" * W)
    add(f"  Highest Net PnL      : {best_pnl_r['label']:<14} -> {best_pnl_r['total_pnl']:+.2f} USDT ({best_pnl_r['roi_pct']:+.1f}% ROI)")
    add(f"  Lowest Max Drawdown  : {best_mdd_r['label']:<14} -> {best_mdd_r['mdd_pct']:.1f}%")
    add(f"  Best Win Rate        : {best_wr_r['label']:<14} -> {best_wr_r['win_rate']:.1f}%")
    add(f"  Best Composite Score : {best_sc_r['label']:<14} -> score {score(best_sc_r):+.1f}")
    add()
    add(f"  RECOMMENDED PARAMETERS (from {best_sc_r['label']}):")
    for k, v in best_sc_r["params"].items():
        add(f"    {k:<22} = {v}")
    add()
    if best_sc_r["mdd_pct"] > 50:
        add("  WARNING: MDD > 50%. Consider further reducing TIER_MARGIN_PCT / LEVERAGE.")
    elif best_sc_r["mdd_pct"] <= 30 and best_sc_r["total_pnl"] > 30:
        add("  READY: Strategy looks deployment-ready with compound growth.")
        add("  Monitor live performance; consider paper-trading first.")
    else:
        add("  PROGRESS: Good risk-adjusted result. Consider additional tuning or paper-trading.")
    add()
    add("=" * W)
    add(f"  Report written to: {report_path}")
    add("=" * W)

    report_text = "\n".join(lines)
    print(report_text)

    with open(report_path, "w") as f:
        f.write(report_text)

    return report_text


# ────────────────────────────────────────────────────────────────────────────
# Main loop
# ────────────────────────────────────────────────────────────────────────────
def main():
    print("=" * 80)
    print("  ITERATIVE BACKTEST OPTIMIZER v2 — %d ITERATIONS x %d DAYS" % (NUM_ITERATIONS, DAYS))
    print("  Mode: COMPOUND INTEREST (profits reinvested)")
    print("=" * 80)
    print()

    params      = copy.deepcopy(DEFAULT_PARAMS)
    all_results = []

    # track the best-scoring result across all iterations
    best_result = None
    best_params = copy.deepcopy(DEFAULT_PARAMS)
    best_score  = float("-inf")

    for iteration in range(NUM_ITERATIONS + 1):
        if iteration == 0:
            label = "Baseline"
            strategy = "-"
        else:
            label = f"Iter_{iteration}"

        print(f"[{iteration}/{NUM_ITERATIONS}] Running {label}")
        for k, v in params.items():
            print(f"         {k} = {v}")
        if iteration > 0:
            print(f"         strategy = {strategy}")
        print()

        result = run_backtest(params, label=label)
        result["strategy"] = strategy if iteration > 0 else "baseline"
        all_results.append(result)

        sc = score(result)
        pf_disp = f"{result['profit_factor']:.2f}" if result["profit_factor"] != float("inf") else "inf"
        is_new_best = sc > best_score

        print(f"  -> PnL: {result['total_pnl']:+.2f}  |  "
              f"Bal: {result['final_balance']:.2f}  |  "
              f"ROI: {result['roi_pct']:+.1f}%  |  "
              f"WR: {result['win_rate']:.1f}%  |  "
              f"MDD: {result['mdd_pct']:.1f}%  |  "
              f"PF: {pf_disp}  |  "
              f"Score: {sc:+.1f}")

        if is_new_best:
            best_score  = sc
            best_result = result
            best_params = copy.deepcopy(params)
            print(f"  ** NEW BEST (score {sc:+.1f}) **")
        else:
            print(f"  -- reverting to best params ({best_result['label']}, score {best_score:+.1f})")
        print()

        if iteration < NUM_ITERATIONS:
            params, strategy = propose_next_params(
                best_params, best_result or result, result, iteration + 1
            )
            prev_p = all_results[-1]["params"]
            print(f"  -> Next: Iter_{iteration + 1}  strategy={strategy}")
            for k, v in params.items():
                marker = " <-" if v != prev_p.get(k) else ""
                print(f"       {k:<22} = {v}{marker}")
            print()

    # ── Save CSVs ────────────────────────────────────────────────────────────
    summary_rows = []
    for r in all_results:
        row = {
            "label": r["label"], "strategy": r.get("strategy", ""),
            "total_pnl": r["total_pnl"], "final_balance": r["final_balance"],
            "roi_pct": r["roi_pct"], "win_rate": r["win_rate"],
            "mdd_pct": r["mdd_pct"], "trades": r["trades"],
            "avg_win": r["avg_win"], "avg_loss": r["avg_loss"],
            "profit_factor": r["profit_factor"], "neg_months": r["neg_months"],
            "score": score(r),
        }
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
    write_comprehensive_report(all_results, best_result, monthly_df,
                                "comprehensive_report.txt")


if __name__ == "__main__":
    main()
