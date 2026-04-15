import json
import re
from datetime import datetime

with open('messages4.json') as f:
    messages = json.load(f)

messages = list(reversed(messages))

CONTRACTS = 3  # starting contracts per trade

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

    entry_match = re.search(r'🟡.*?QQQ\s+(\d+)\s+(PUTS|CALLS)\s+@\s+([\d.]+)', content, re.IGNORECASE)
    tp_match = re.search(r'🟢.*?QQQ\s+(\d+)\s+(PUTS|CALLS)\s+@\s+([\d.]+)', content, re.IGNORECASE)
    exit_match = re.search(r'🔴.*?QQQ\s+(\d+)\s+(PUTS|CALLS)', content, re.IGNORECASE)

    if entry_match:
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
        current_trade['exit_time'] = ts
        current_trade['status'] = 'tp'

    elif exit_match and current_trade and current_trade['status'] in ('open', 'tp'):
        current_trade['exit_time'] = ts
        current_trade['status'] = 'stopped'
        trades.append(current_trade)
        current_trade = None

if current_trade:
    if current_trade['status'] == 'open':
        current_trade['status'] = 'no_exit'
    trades.append(current_trade)

closed = [t for t in trades if t['status'] in ['tp', 'stopped']]

# ─── P&L with correct 25% partial model ───────────────────────────────────────
# Rules:
#   - Start with CONTRACTS contracts
#   - Each TP: sell 25% of REMAINING holdings
#   - After first TP: stop moves to breakeven (entry price)
#   - If stopped at breakeven: exit remaining at entry price = $0 on remainder
#   - If no TP before stop: full loss (-100% of premium)

results = []

print(f"{'='*80}")
print(f"FINAL BACKTEST — 0DTE QQQ | {CONTRACTS} Contracts | 25% Partials | Breakeven Stop")
print(f"{'='*80}\n")
print(f"{'C/P':<6} {'Strike':<8} {'Entry':<8} {'TPs':<5} {'TP Prices':<40} {'$ P&L':<10} Result")
print(f"-"*85)

for t in closed:
    entry = t['entry_price']
    tps = t['take_profits']
    num_tps = len(tps)
    status = t['status']

    remaining = CONTRACTS
    dollar_pnl = 0
    tp_log = []

    if num_tps == 0:
        # No TP hit before exit — full loss
        dollar_pnl = -(entry * 100 * CONTRACTS)
        win = False
        tp_str = 'FULL LOSS'
    else:
        # Process each TP: sell 25% of remaining
        for tp in tps:
            sell_qty = remaining * 0.25
            profit = (tp - entry) * sell_qty * 100
            dollar_pnl += profit
            tp_log.append(f"${tp}x{sell_qty:.2f}c")
            remaining -= sell_qty

        # After TPs: remaining contracts exit at breakeven (entry price) = $0 P&L
        # (stop moved to breakeven after first TP)
        # So remaining P&L contribution = 0
        tp_str = ' | '.join(tp_log)
        win = dollar_pnl > 0

    invested = entry * 100 * CONTRACTS
    pnl_pct = (dollar_pnl / invested) * 100

    results.append({
        'call_put': t['call_put'],
        'strike': t['strike'],
        'entry_price': entry,
        'num_tps': num_tps,
        'tps': tps,
        'dollar_pnl': round(dollar_pnl, 2),
        'pnl_pct': round(pnl_pct, 1),
        'win': bool(win),
        'entry_time': str(t['entry_time']),
    })

    result_str = 'WIN' if win else 'LOSS'
    print(f"{t['call_put']:<6} {t['strike']:<8} ${entry:<7} {num_tps:<5} {tp_str:<40} ${dollar_pnl:>+8.2f}  {result_str}")

# ─── Summary ──────────────────────────────────────────────────────────────────
wins = [r for r in results if r['win']]
losses = [r for r in results if not r['win']]
total = len(results)
win_rate = len(wins) / total * 100
avg_pnl = sum(r['dollar_pnl'] for r in results) / total
avg_win = sum(r['dollar_pnl'] for r in wins) / len(wins) if wins else 0
avg_loss = sum(r['dollar_pnl'] for r in losses) / len(losses) if losses else 0
total_pnl = sum(r['dollar_pnl'] for r in results)
total_invested = sum(r['entry_price'] * 100 * CONTRACTS for r in results)

calls = [r for r in results if r['call_put'] == 'Calls']
puts = [r for r in results if r['call_put'] == 'Puts']
call_wins = [r for r in calls if r['win']]
put_wins = [r for r in puts if r['win']]

best = max(results, key=lambda x: x['dollar_pnl'])
worst = min(results, key=lambda x: x['dollar_pnl'])

print(f"\n{'='*60}")
print(f"RESULTS SUMMARY")
print(f"{'='*60}")
print(f"Total trades:        {total}")
print(f"Wins / Losses:       {len(wins)} / {len(losses)}")
print(f"Win Rate:            {win_rate:.1f}%")
print(f"Avg $ per trade:     ${avg_pnl:+.2f}")
print(f"Avg Win:             ${avg_win:+.2f}")
print(f"Avg Loss:            ${avg_loss:+.2f}")
if calls:
    print(f"Call Win Rate:       {len(call_wins)/len(calls)*100:.0f}% ({len(call_wins)}/{len(calls)})")
if puts:
    print(f"Put Win Rate:        {len(put_wins)/len(puts)*100:.0f}% ({len(put_wins)}/{len(puts)})")
print(f"\nTotal P&L:           ${total_pnl:+.2f}")
print(f"Total invested:      ${total_invested:.2f}")
print(f"Overall return:      {(total_pnl/total_invested)*100:+.1f}%")
print(f"\nBest trade:          {best['call_put']} {best['strike']} (${best['dollar_pnl']:+.2f})")
print(f"Worst trade:         {worst['call_put']} {worst['strike']} (${worst['dollar_pnl']:+.2f})")

# ─── Risk metrics ─────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"RISK METRICS")
print(f"{'='*60}")
max_loss = min(r['dollar_pnl'] for r in results)
max_consec_losses = 1
cur = 1
for i in range(1, len(results)):
    if not results[i]['win'] and not results[i-1]['win']:
        cur += 1
        max_consec_losses = max(max_consec_losses, cur)
    else:
        cur = 1

print(f"Max single loss:     ${max_loss:+.2f}")
print(f"Max consec losses:   {max_consec_losses}")
print(f"Loss rate:           {100-win_rate:.1f}%")

# Starting with £1000 / $1250
account = 1250
trades_to_bust = int(account / abs(avg_loss)) if avg_loss < 0 else 999
print(f"\nWith $1,250 account:")
print(f"Avg loss per trade:  ${avg_loss:+.2f}")
print(f"Trades to bust:      {trades_to_bust} consecutive losses")

with open('backtest_final_results.json', 'w') as f:
    json.dump(results, f, indent=2, default=str)
print(f"\nSaved to backtest_final_results.json")
