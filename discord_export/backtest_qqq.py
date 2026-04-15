import json
import re
from datetime import datetime

with open('messages4.json') as f:
    messages = json.load(f)

# Parse messages in reverse (oldest first)
messages = list(reversed(messages))

trades = []
current_trade = None

for msg in messages:
    content = msg.get('content', '').strip()
    if not content:
        continue

    timestamp = msg.get('timestamp', '')
    try:
        ts = datetime.fromisoformat(timestamp)
    except:
        continue

    # Match entry: 🟡 QQQ 605 PUTS @ 1.25
    entry_match = re.search(r'🟡.*?QQQ\s+(\d+)\s+(PUTS|CALLS)\s+@\s+([\d.]+)', content, re.IGNORECASE)
    # Match take profit: 🟢 QQQ 605 PUTS @ 1.65
    tp_match = re.search(r'🟢.*?QQQ\s+(\d+)\s+(PUTS|CALLS)\s+@\s+([\d.]+)', content, re.IGNORECASE)
    # Match exit: 🔴 QQQ 574 PUTS (no price = stop loss)
    exit_match = re.search(r'🔴.*?QQQ\s+(\d+)\s+(PUTS|CALLS)', content, re.IGNORECASE)

    if entry_match:
        # Save previous trade if it exists
        if current_trade:
            if current_trade['status'] == 'open':
                current_trade['status'] = 'no_exit'
            trades.append(current_trade)

        strike = int(entry_match.group(1))
        call_put = entry_match.group(2).capitalize()
        entry_price = float(entry_match.group(3))

        current_trade = {
            'symbol': 'QQQ',
            'strike': strike,
            'call_put': call_put,
            'entry_price': entry_price,
            'entry_time': ts,
            'take_profits': [],
            'exit_price': None,
            'exit_time': None,
            'status': 'open',
        }

    elif tp_match and current_trade and current_trade['status'] in ('open', 'tp'):
        tp_price = float(tp_match.group(3))
        current_trade['take_profits'].append(tp_price)
        # Use highest take profit as final exit
        current_trade['exit_price'] = max(current_trade['take_profits'])
        current_trade['exit_time'] = ts
        current_trade['status'] = 'tp'

    elif exit_match and current_trade and current_trade['status'] in ('open', 'tp'):
        current_trade['exit_price'] = current_trade['entry_price'] * 0.5  # assume 50% loss on stop
        current_trade['exit_time'] = ts
        current_trade['status'] = 'stopped'
        trades.append(current_trade)
        current_trade = None

# Close any remaining open trade
if current_trade and current_trade['status'] == 'open':
    current_trade['status'] = 'no_exit'
    trades.append(current_trade)

# Filter to closed trades only
closed = [t for t in trades if t['status'] in ['tp', 'stopped']]

print(f"Total signals parsed: {len(trades)}")
print(f"Closed trades:        {len(closed)}")
print(f"No exit found:        {len([t for t in trades if t['status'] == 'no_exit'])}")
print()
CONTRACTS = 3

print(f"{'C/P':<6} {'Strike':<8} {'Entry':<8} {'TPs':<5} {'Partials':<35} {'$ P&L':<10} Result")
print("-" * 85)

results = []
for t in closed:
    entry = t['entry_price']
    tps = t['take_profits']
    num_tps = len(tps)

    if t['status'] == 'stopped' or num_tps == 0:
        # Full loss - lose all 3 contracts
        dollar_pnl = -(entry * 100 * CONTRACTS)
        pnl_pct = -100.0
        win = False
        partials_str = f"LOSS (3 contracts @ ${entry})"
    else:
        # Sell contracts evenly across TPs
        contracts_per_tp = CONTRACTS / num_tps
        dollar_pnl = 0
        partial_details = []

        for tp in tps:
            profit = (tp - entry) * contracts_per_tp * 100
            dollar_pnl += profit
            partial_details.append(f"${tp}x{contracts_per_tp:.1f}c")

        pnl_pct = (dollar_pnl / (entry * 100 * CONTRACTS)) * 100
        win = True
        partials_str = " | ".join(partial_details)

    results.append({
        'call_put': t['call_put'],
        'strike': t['strike'],
        'entry_price': entry,
        'tps': tps,
        'num_tps': num_tps,
        'pnl_pct': round(pnl_pct, 1),
        'dollar_pnl': round(dollar_pnl, 2),
        'status': t['status'],
        'entry_time': str(t['entry_time']),
        'win': bool(win),
    })

    status = 'WIN' if win else 'LOSS'
    print(f"{t['call_put']:<6} {t['strike']:<8} ${entry:<7} {num_tps:<5} {partials_str:<35} ${dollar_pnl:>+8.2f}  {status}")

if results:
    wins = [r for r in results if r['win']]
    losses = [r for r in results if not r['win']]
    win_rate = len(wins) / len(results) * 100
    avg_pnl = sum(r['pnl_pct'] for r in results) / len(results)
    avg_win = sum(r['pnl_pct'] for r in wins) / len(wins) if wins else 0
    avg_loss = sum(r['pnl_pct'] for r in losses) / len(losses) if losses else 0
    total_dollar = sum(r['dollar_pnl'] for r in results)
    total_invested = sum(r['entry_price'] * 100 * CONTRACTS for r in results)

    calls = [r for r in results if r['call_put'] == 'Calls']
    puts = [r for r in results if r['call_put'] == 'Puts']
    call_wins = [r for r in calls if r['win']]
    put_wins = [r for r in puts if r['win']]

    best = max(results, key=lambda x: x['pnl_pct'])
    worst = min(results, key=lambda x: x['pnl_pct'])

    print(f"\n{'='*60}")
    print(f"QQQ OPTIONS BACKTEST RESULTS")
    print(f"{'='*60}")
    print(f"Total closed trades: {len(results)}")
    print(f"Win Rate:            {win_rate:.1f}%")
    print(f"Avg P&L per trade:   {avg_pnl:+.1f}%")
    print(f"Avg Win:             {avg_win:+.1f}%")
    print(f"Avg Loss:            {avg_loss:+.1f}%")
    if calls:
        call_avg = sum(r['pnl_pct'] for r in calls) / len(calls)
        print(f"Call Win Rate:       {len(call_wins)/len(calls)*100:.1f}% ({len(call_wins)}/{len(calls)}) | Avg: {call_avg:+.1f}%")
    if puts:
        put_avg = sum(r['pnl_pct'] for r in puts) / len(puts)
        print(f"Put Win Rate:        {len(put_wins)/len(puts)*100:.1f}% ({len(put_wins)}/{len(puts)}) | Avg: {put_avg:+.1f}%")
    print(f"Total $ P&L ({CONTRACTS} contracts each): ${total_dollar:+.2f}")
    print(f"Total invested ({CONTRACTS} contracts each): ${total_invested:.2f}")
    print(f"Overall return: {(total_dollar/total_invested)*100:+.1f}%")
    print(f"\nBest trade:  {best['call_put']} {best['strike']} ({best['pnl_pct']:+.1f}% / ${best['dollar_pnl']:+.2f})")
    print(f"Worst trade: {worst['call_put']} {worst['strike']} ({worst['pnl_pct']:+.1f}% / ${worst['dollar_pnl']:+.2f})")

    with open('backtest_qqq_results.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nSaved to backtest_qqq_results.json")
