import json
import yfinance as yf
import re
from datetime import datetime, timedelta
import pandas as pd

with open('messages4.json') as f:
    messages = json.load(f)

messages = list(reversed(messages))

# Parse entries with exact timestamps
entries = []
for msg in messages:
    content = msg.get('content', '').strip()
    if not content:
        continue
    ts = datetime.fromisoformat(msg['timestamp'])
    entry_match = re.search(r'🟡.*?QQQ\s+(\d+)\s+(PUTS|CALLS)\s+@\s+([\d.]+)', content, re.IGNORECASE)
    if entry_match:
        entries.append({
            'timestamp': ts,
            'strike': int(entry_match.group(1)),
            'call_put': entry_match.group(2).capitalize(),
            'entry_price': float(entry_match.group(3)),
        })

# Load win/loss from backtest results
with open('backtest_qqq_results.json') as f:
    results = json.load(f)

for i, e in enumerate(entries[:len(results)]):
    e['win'] = results[i]['win']

print("Fetching QQQ intraday data for each entry...\n")

# Fetch QQQ 1-minute data for each trade day
# All entries are at 9:30 AM EST (market open) regardless of UK time shown
trade_dates = list(set(e['timestamp'].date() for e in entries))

# Only fetch dates within last 30 days (Yahoo Finance limit for 1m data)
from datetime import date as date_type
cutoff = datetime.now().date() - timedelta(days=29)
recent_dates = [d for d in trade_dates if d >= cutoff]
old_dates = [d for d in trade_dates if d < cutoff]

if old_dates:
    print(f"Note: {len(old_dates)} trade dates are older than 30 days — skipping (Yahoo Finance limit)")
    print(f"Analyzing {len(recent_dates)} recent dates\n")

qqq_data = {}
for date in recent_dates:
    try:
        ticker = yf.Ticker('QQQ')
        hist = ticker.history(
            start=str(date),
            end=str(date + timedelta(days=1)),
            interval='1m'
        )
        if not hist.empty:
            qqq_data[date] = hist
            print(f"Loaded {len(hist)} 1-min bars for {date}")
    except Exception as e:
        print(f"Failed {date}: {e}")

def get_vwap(df):
    """Calculate VWAP from start of day"""
    df = df.copy()
    df['cum_vol'] = df['Volume'].cumsum()
    df['cum_vwap'] = ((df['High'] + df['Low'] + df['Close']) / 3 * df['Volume']).cumsum()
    df['vwap'] = df['cum_vwap'] / df['cum_vol']
    return df

print(f"\n{'='*90}")
print(f"ENTRY CONTEXT ANALYSIS")
print(f"{'='*90}")
print(f"{'Time (UTC)':<14} {'C/P':<6} {'Strike':<8} {'QQQ Now':<11} {'Open':<11} {'vs Strike':<14} {'vs VWAP':<14} {'Trend from Open':<30} {'Result'}")
print(f"-"*110)

analysis = []

for entry in entries:
    ts = entry['timestamp']
    date = ts.date()

    if date not in qqq_data:
        continue

    df = qqq_data[date]
    df = get_vwap(df)

    # All entries are at 9:30 AM EST = 14:30 UTC (winter) or 13:30 UTC (after US DST)
    # Find the 9:30 AM EST bar = first bar of the day
    entry_time_str = ts.strftime('%H:%M UTC')
    closest_bar = None
    min_diff = timedelta(minutes=10)

    for idx in df.index:
        bar_time = idx.to_pydatetime()
        # Convert to EST: UTC-5 (or UTC-4 during EDT)
        # Just find bar closest to entry timestamp
        bar_utc = bar_time.replace(tzinfo=None) if bar_time.tzinfo else bar_time
        entry_utc = ts.replace(tzinfo=None)
        diff = abs(bar_utc - entry_utc)
        if diff < min_diff:
            min_diff = diff
            closest_bar = idx

    if closest_bar is None:
        continue

    bar = df.loc[closest_bar]
    qqq_price = bar['Close']
    vwap = bar['vwap']

    # Opening range: first bar of the day (9:30 open)
    first_bar = df.iloc[0]
    open_price = first_bar['Open']
    bar_idx = df.index.get_loc(closest_bar)

    # 5-minute trend from open
    trend = 'UP' if qqq_price > open_price else 'DOWN'
    trend_pct = ((qqq_price - open_price) / open_price) * 100
    trend_str = f"{trend} ({trend_pct:+.2f}% from open)"

    # Previous day close
    prev_close = None
    if bar_idx >= 1:
        # First bar open IS the gap from prev close
        gap_pct = ((open_price - qqq_price) / qqq_price) * 100

    # Strike vs QQQ price
    strike = entry['strike']
    vs_strike = qqq_price - strike
    vs_strike_str = f"{vs_strike:+.2f} ({'ITM' if (entry['call_put']=='Calls' and vs_strike > 0) or (entry['call_put']=='Puts' and vs_strike < 0) else 'OTM'})"

    # vs VWAP
    vs_vwap = qqq_price - vwap
    vs_vwap_str = f"{vs_vwap:+.2f} ({'above' if vs_vwap > 0 else 'below'})"

    win_str = 'WIN' if entry.get('win') else 'LOSS'

    analysis.append({
        'time': entry_time_str,
        'call_put': entry['call_put'],
        'strike': strike,
        'qqq_price': round(qqq_price, 2),
        'vs_strike': round(vs_strike, 2),
        'vs_vwap': round(vs_vwap, 2),
        'trend_5m': trend_str,
        'win': entry.get('win'),
    })

    print(f"{entry_time_str:<14} {entry['call_put']:<6} {strike:<8} ${qqq_price:<10.2f} ${open_price:<10.2f} {vs_strike_str:<14} {vs_vwap_str:<14} {trend_str:<30} {win_str}")

# Summary patterns
print(f"\n{'='*60}")
print("PATTERN SUMMARY")
print(f"{'='*60}")

wins = [a for a in analysis if a['win']]
losses = [a for a in analysis if not a['win']]

# ITM vs OTM on wins
print("\n--- MONEYNESS AT ENTRY ---")
for group, label in [(wins, 'WINS'), (losses, 'LOSSES')]:
    itm = 0
    otm = 0
    for a in group:
        if a['call_put'] == 'Calls':
            if a['vs_strike'] > 0:
                itm += 1
            else:
                otm += 1
        else:
            if a['vs_strike'] < 0:
                itm += 1
            else:
                otm += 1
    print(f"{label}: ITM={itm}, OTM={otm}")

# VWAP relationship
print("\n--- VWAP AT ENTRY ---")
for group, label in [(wins, 'WINS'), (losses, 'LOSSES')]:
    above = sum(1 for a in group if a['vs_vwap'] > 0)
    below = sum(1 for a in group if a['vs_vwap'] < 0)
    avg_vs_vwap = sum(a['vs_vwap'] for a in group) / len(group) if group else 0
    print(f"{label}: above VWAP={above}, below VWAP={below}, avg distance={avg_vs_vwap:+.2f}")

# Calls: wins above or below VWAP?
print("\n--- CALLS: VWAP DIRECTION ---")
call_wins = [a for a in wins if a['call_put'] == 'Calls']
call_losses = [a for a in losses if a['call_put'] == 'Calls']
print(f"Call WINS  - above VWAP: {sum(1 for a in call_wins if a['vs_vwap'] > 0)}, below: {sum(1 for a in call_wins if a['vs_vwap'] < 0)}")
print(f"Call LOSSES - above VWAP: {sum(1 for a in call_losses if a['vs_vwap'] > 0)}, below: {sum(1 for a in call_losses if a['vs_vwap'] < 0)}")

print("\n--- PUTS: VWAP DIRECTION ---")
put_wins = [a for a in wins if a['call_put'] == 'Puts']
put_losses = [a for a in losses if a['call_put'] == 'Puts']
print(f"Put WINS  - above VWAP: {sum(1 for a in put_wins if a['vs_vwap'] > 0)}, below: {sum(1 for a in put_wins if a['vs_vwap'] < 0)}")
print(f"Put LOSSES - above VWAP: {sum(1 for a in put_losses if a['vs_vwap'] > 0)}, below: {sum(1 for a in put_losses if a['vs_vwap'] < 0)}")

with open('entry_analysis.json', 'w') as f:
    json.dump(analysis, f, indent=2, default=str)
print(f"\nSaved to entry_analysis.json")
