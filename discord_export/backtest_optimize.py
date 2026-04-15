import json
import re
from datetime import datetime
from itertools import product

with open('messages4.json') as f:
    messages = json.load(f)

messages = list(reversed(messages))

with open('backtest_qqq_results.json') as f:
    win_loss = json.load(f)

# Parse trades
trades = []
current_trade = None

for msg in messages:
    content = msg.get('content', '').strip()
    if not content:
        continue
    try:
        ts = datetime.fromisoformat(msg.get('timestamp', ''))
    except:
        continue

    entry_match = re.search(r'🟡.*?QQQ\s+(\d+)\s+(PUTS|CALLS)\s+@\s+([\d.]+)', content, re.IGNORECASE)
    tp_match = re.search(r'🟢.*?QQQ\s+(\d+)\s+(PUTS|CALLS)\s+@\s+([\d.]+)', content, re.IGNORECASE)
    exit_match = re.search(r'🔴.*?QQQ\s+(\d+)\s+(PUTS|CALLS)', content, re.IGNORECASE)

    if entry_match:
        if current_trade:
            if current_trade['status'] == 'open':
                current_trade['status'] = 'no_exit'
            trades.append(current_trade)
        current_trade = {
            'strike': int(entry_match.group(1)),
            'call_put': entry_match.group(2).capitalize(),
            'entry_price': float(entry_match.group(3)),
            'entry_time': ts,
            'take_profits': [],
            'status': 'open',
        }
    elif tp_match and current_trade and current_trade['status'] in ('open', 'tp'):
        current_trade['take_profits'].append(float(tp_match.group(3)))
        current_trade['status'] = 'tp'
    elif exit_match and current_trade and current_trade['status'] in ('open', 'tp'):
        current_trade['status'] = 'stopped'
        trades.append(current_trade)
        current_trade = None

if current_trade:
    if current_trade['status'] == 'open':
        current_trade['status'] = 'no_exit'
    trades.append(current_trade)

closed = [t for t in trades if t['status'] in ['tp', 'stopped']]

def simulate(contracts, partial_pct, exit_all_at_tp=None):
    """
    Correct model:
    - Buy contracts at entry
    - Each TP: sell partial_pct of REMAINING, profit on sold portion
    - After each TP: stop moves to breakeven
    - Remaining after all TPs: exits at breakeven = $0 profit
    - If exit_all_at_tp set: sell ALL remaining at that TP number
    - 0 TPs posted = full loss (stopped before any TP)
    """
    total_pnl = 0
    total_invested = 0

    for t in closed:
        entry = t['entry_price']
        tps = t['take_profits']
        num_tps = len(tps)
        invested = entry * 100 * contracts
        total_invested += invested

        if num_tps == 0:
            # Full loss — stopped before any TP
            total_pnl -= invested
            continue

        remaining = contracts
        pnl = 0

        for i, tp in enumerate(tps):
            if exit_all_at_tp and i + 1 == exit_all_at_tp:
                # Exit everything at this TP
                pnl += (tp - entry) * remaining * 100
                remaining = 0
                break
            else:
                sell = remaining * partial_pct
                pnl += (tp - entry) * sell * 100
                remaining -= sell

        # Remaining exits at breakeven = $0
        total_pnl += pnl

    return total_pnl, total_invested

print("Testing all strategies (correct model: 25% partials + breakeven stop)...\n")
print(f"{'Strategy':<50} {'Total P&L':>10} {'Return':>8} {'Avg/Trade':>10}")
print("-" * 80)

strategies = []

for contracts in [1, 2, 3]:
    # Exit ALL at TP1
    pnl, inv = simulate(contracts, 1.0, exit_all_at_tp=1)
    strategies.append((f"{contracts}c — exit ALL at TP1", pnl, inv, len(closed)))

    # Exit ALL at TP2
    pnl, inv = simulate(contracts, 1.0, exit_all_at_tp=2)
    strategies.append((f"{contracts}c — exit ALL at TP2", pnl, inv, len(closed)))

    # Exit ALL at TP3
    pnl, inv = simulate(contracts, 1.0, exit_all_at_tp=3)
    strategies.append((f"{contracts}c — exit ALL at TP3", pnl, inv, len(closed)))

    # 25% partials — his method (rest at BE)
    pnl, inv = simulate(contracts, 0.25)
    strategies.append((f"{contracts}c — 25% partials, rest at BE (his method)", pnl, inv, len(closed)))

    # 50% partials — rest at BE
    pnl, inv = simulate(contracts, 0.50)
    strategies.append((f"{contracts}c — 50% partials, rest at BE", pnl, inv, len(closed)))

    # 33% partials — rest at BE
    pnl, inv = simulate(contracts, 0.33)
    strategies.append((f"{contracts}c — 33% partials, rest at BE", pnl, inv, len(closed)))

# Sort by total P&L
strategies.sort(key=lambda x: x[1], reverse=True)

for name, pnl, inv, n in strategies:
    ret = (pnl / inv) * 100
    avg = pnl / n
    marker = " ◄ BEST" if strategies.index((name, pnl, inv, n)) == 0 else ""
    print(f"{name:<45} ${pnl:>+9.2f} {ret:>+7.1f}% ${avg:>+9.2f}{marker}")

# Show the best strategy in detail
print(f"\n{'='*60}")
best = strategies[0]
print(f"BEST STRATEGY: {best[0]}")
print(f"{'='*60}")

# Parse the best strategy
name = best[0]
contracts = int(name[0])
if 'exit ALL at TP1' in name:
    partial_pct, exit_all_at_tp = 1.0, 1
elif 'exit ALL at TP2' in name:
    partial_pct, exit_all_at_tp = 1.0, 2
elif 'exit ALL at TP3' in name:
    partial_pct, exit_all_at_tp = 1.0, 3
elif '25% partials' in name:
    partial_pct, exit_all_at_tp = 0.25, None
elif '50% partials' in name:
    partial_pct, exit_all_at_tp = 0.50, None
elif '33% partials' in name:
    partial_pct, exit_all_at_tp = 0.33, None
else:
    partial_pct, exit_all_at_tp = 1.0, 1

print(f"\nTrade-by-trade breakdown:")
print(f"{'C/P':<6} {'Strike':<8} {'Entry':<8} {'Exit':<8} {'$ P&L':<10} Result")
print("-" * 50)

trade_results = []
for t in closed:
    entry = t['entry_price']
    tps = t['take_profits']
    num_tps = len(tps)

    if num_tps == 0:
        pnl = -(entry * 100 * contracts)
        exit_price = 0
        win = False
    else:
        remaining = contracts
        pnl = 0
        exit_price = tps[-1]
        for i, tp in enumerate(tps):
            if exit_all_at_tp and i + 1 == exit_all_at_tp:
                pnl += (tp - entry) * remaining * 100
                remaining = 0
                exit_price = tp
                break
            else:
                sell = remaining * partial_pct
                pnl += (tp - entry) * sell * 100
                remaining -= sell
        win = pnl > 0

    trade_results.append({'win': win, 'pnl': pnl})
    status = 'WIN' if win else 'LOSS'
    print(f"{t['call_put']:<6} {t['strike']:<8} ${entry:<7} ${exit_price:<7} ${pnl:>+8.2f}  {status}")

total = sum(r['pnl'] for r in trade_results)
w = sum(1 for r in trade_results if r['win'])
print(f"\nWin Rate: {w}/{len(trade_results)} = {w/len(trade_results)*100:.0f}%")
print(f"Total P&L: ${total:+.2f}")
print(f"\nWith $1,250 account (£1,000):")
print(f"Net profit: ${total:+.2f} ({total/1250*100:+.1f}% of account)")
