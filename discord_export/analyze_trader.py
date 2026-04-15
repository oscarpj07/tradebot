import json
from datetime import datetime

with open('backtest_qqq_results.json') as f:
    trades = json.load(f)

with open('messages4.json') as f:
    messages = json.load(f)

messages = list(reversed(messages))

print("=" * 60)
print("TRADER PATTERN ANALYSIS")
print("=" * 60)

# 1. Time of day analysis
print("\n--- TIME OF DAY ---")
times = []
for msg in messages:
    content = msg.get('content', '')
    if '🟡' in content and 'ENTRY' in content:
        ts = datetime.fromisoformat(msg['timestamp'])
        times.append(ts)
        print(f"Entry at: {ts.strftime('%H:%M')} EST  ({ts.strftime('%A')})")

# 2. Call vs Put breakdown
print("\n--- CALL vs PUT ---")
calls = [t for t in trades if t['call_put'] == 'Calls']
puts = [t for t in trades if t['call_put'] == 'Puts']
print(f"Calls: {len(calls)}  |  Puts: {len(puts)}")
print(f"Call win rate: {sum(1 for t in calls if t['win'])/len(calls)*100:.0f}%")
print(f"Put win rate:  {sum(1 for t in puts if t['win'])/len(puts)*100:.0f}%")

# 3. Entry price patterns
print("\n--- ENTRY PRICE PATTERNS ---")
entry_prices = [t['entry_price'] for t in trades]
print(f"Min entry:  ${min(entry_prices):.3f}")
print(f"Max entry:  ${max(entry_prices):.3f}")
print(f"Avg entry:  ${sum(entry_prices)/len(entry_prices):.3f}")
wins = [t for t in trades if t['win']]
losses = [t for t in trades if not t['win']]
if wins:
    print(f"Avg entry on WINS:   ${sum(t['entry_price'] for t in wins)/len(wins):.3f}")
if losses:
    print(f"Avg entry on LOSSES: ${sum(t['entry_price'] for t in losses)/len(losses):.3f}")

# 4. Strike vs QQQ price patterns
print("\n--- STRIKE ANALYSIS ---")
strikes = [t['strike'] for t in trades]
print(f"Min strike: {min(strikes)}")
print(f"Max strike: {max(strikes)}")
print(f"Avg strike: {sum(strikes)/len(strikes):.1f}")

# 5. Number of TPs on wins vs losses
print("\n--- TPs ON WINS vs LOSSES ---")
print(f"Avg TPs on wins:   {sum(t['num_tps'] for t in wins)/len(wins):.1f}")
print(f"Avg TPs on losses: 0 (all losses had 0 TPs - stopped immediately)")

# 6. Day of week
print("\n--- DAY OF WEEK ---")
from collections import Counter
days = Counter(ts.strftime('%A') for ts in times)
for day, count in sorted(days.items(), key=lambda x: ['Monday','Tuesday','Wednesday','Thursday','Friday'].index(x[0]) if x[0] in ['Monday','Tuesday','Wednesday','Thursday','Friday'] else 5):
    wins_on_day = []
    for t, ts in zip([t for msg in messages if '🟡' in msg.get('content','') and 'ENTRY' in msg.get('content','') for t in [datetime.fromisoformat(msg['timestamp'])]], times):
        pass
    print(f"{day}: {count} trades")

# 7. P&L by month
print("\n--- P&L BY MONTH ---")
months = {}
for msg in messages:
    content = msg.get('content', '')
    if '🟡' in content and 'ENTRY' in content:
        ts = datetime.fromisoformat(msg['timestamp'])
        month = ts.strftime('%Y-%m')
        if month not in months:
            months[month] = []
        months[month].append(ts)

for month, ts_list in sorted(months.items()):
    print(f"{month}: {len(ts_list)} trades")

# 8. Win/loss streaks
print("\n--- WIN/LOSS STREAKS ---")
streak = 1
max_win_streak = 0
max_loss_streak = 0
current_streak_type = trades[0]['win'] if trades else None

for i in range(1, len(trades)):
    if trades[i]['win'] == trades[i-1]['win']:
        streak += 1
    else:
        if trades[i-1]['win']:
            max_win_streak = max(max_win_streak, streak)
        else:
            max_loss_streak = max(max_loss_streak, streak)
        streak = 1

print(f"Longest win streak:  {max_win_streak}")
print(f"Longest loss streak: {max_loss_streak}")

print("\n--- CONSECUTIVE LOSSES (when do losses cluster?) ---")
for i, t in enumerate(trades):
    if not t['win']:
        prev = trades[i-1]['win'] if i > 0 else None
        next_ = trades[i+1]['win'] if i < len(trades)-1 else None
        print(f"Loss #{i+1}: prev={'WIN' if prev else 'LOSS'}, next={'WIN' if next_ else 'LOSS'}")
