import pandas as pd
from src.engine_backtest import BacktestEngine
import logging

logging.getLogger().setLevel(logging.CRITICAL)

print("Starting debug run...")
engine = BacktestEngine(days=180)
engine.run()

closed_trades = [t for t in engine.trades if t['type'] == 'close']
df = pd.DataFrame(closed_trades)
df['time'] = pd.to_datetime(df['time'])

print("\n--- 2025-11 TRADES ---")
nov = df[(df['time'] >= '2025-11-01') & (df['time'] < '2025-12-01')]
for _, t in nov.iterrows():
    if t['pnl'] < 0:
        print(f"[{t['time']}] {t['symbol']} | LOSS: {t['pnl']:.2f}")

print("\n--- 2026-03 TRADES ---")
mar = df[(df['time'] >= '2026-03-01') & (df['time'] < '2026-04-01')]
for _, t in mar.iterrows():
    if t['pnl'] < 0:
        print(f"[{t['time']}] {t['symbol']} | LOSS: {t['pnl']:.2f}")

print("\nStats:")
print("Nov Total Losses:", nov[nov['pnl'] < 0]['pnl'].sum())
print("Mar Total Losses:", mar[mar['pnl'] < 0]['pnl'].sum())
print("Nov Total Wins:", nov[nov['pnl'] > 0]['pnl'].sum())
print("Mar Total Wins:", mar[mar['pnl'] > 0]['pnl'].sum())
