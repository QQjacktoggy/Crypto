from src.engine_backtest import BacktestEngine
import pandas as pd
import logging

logging.getLogger().setLevel(logging.CRITICAL)

print("Starting 180 days backtest with Trend Filter...")
engine = BacktestEngine(days=180)
engine.run()

closed_trades = [t for t in engine.trades if t['type'] == 'close']
if not closed_trades:
    print("No trades found.")
    exit()

df = pd.DataFrame(closed_trades)
df['time'] = pd.to_datetime(df['time'])
df['month'] = df['time'].dt.to_period('M')

print("\n" + "="*50)
print("📅 180-DAY MONTHLY PERFORMANCE (TREND FILTER)")
print("="*50)

monthly_stats = df.groupby('month').apply(
    lambda x: pd.Series({
        'Total Trades': len(x),
        'Wins': (x['pnl'] > 0).sum(),
        'Losses': (x['pnl'] <= 0).sum(),
        'Win Rate (%)': (x['pnl'] > 0).sum() / len(x) * 100,
        'Net PnL (USDT)': x['pnl'].sum()
    })
).reset_index()

cumulative_pnl = 0.0
for _, row in monthly_stats.iterrows():
    month = row['month'].strftime('%Y-%m')
    trades = int(row['Total Trades'])
    wins = int(row['Wins'])
    losses = int(row['Losses'])
    wr = row['Win Rate (%)']
    pnl = row['Net PnL (USDT)']
    cumulative_pnl += pnl

    print(f"[{month}]")
    print(f"  • Trades: {trades} ({wins} W / {losses} L)")
    print(f"  • Win Rate: {wr:.2f}%")
    print(f"  • Monthly Net PnL: {pnl:+.2f} USDT")
    print(f"  • Cumulative PnL: {cumulative_pnl:+.2f} USDT")
    print("-" * 30)

print("="*50)
print(f"📊 6-Month Total Net PnL: {cumulative_pnl:+.2f} USDT")
print(f"🔥 Max Margin Usage: {engine.max_margin_usage:.2f} USDT")
print(f"📉 Max Drawdown: {engine.max_drawdown*100:.2f}%")
print("="*50)
