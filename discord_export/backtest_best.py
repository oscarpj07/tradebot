import json, re

with open('messages4.json') as f:
    messages = json.load(f)

messages = list(reversed(messages))

trades = []
current = None

for msg in messages:
    content = msg.get('content','').strip()
    if not content:
        continue
    ts = msg.get('timestamp','')

    entry = re.search(r'🟡.*?QQQ\s+(\d+)\s+(PUTS|CALLS)\s+@\s+([\d.]+)', content, re.IGNORECASE)
    tp    = re.search(r'🟢.*?QQQ\s+(\d+)\s+(PUTS|CALLS)\s+@\s+([\d.]+)', content, re.IGNORECASE)
    exit_ = re.search(r'🔴.*?QQQ\s+(\d+)\s+(PUTS|CALLS)', content, re.IGNORECASE)

    if entry:
        if current:
            trades.append(current)
        current = {'date': ts[:10], 'type': entry.group(2), 'strike': entry.group(1),
                   'entry': float(entry.group(3)), 'tps': [], 'stopped': False}
    elif tp and current:
        current['tps'].append(float(tp.group(3)))
    elif exit_ and current:
        current['stopped'] = True
        trades.append(current)
        current = None

if current:
    trades.append(current)

# Remove midnight test trade
trades = [t for t in trades if t['date'] != '2025-11-20']

def calc_pnl(trades, contracts, strategy):
    total = 0
    invested = 0
    results = []

    for t in trades:
        entry = t['entry']
        tps = t['tps']
        n = len(tps)
        inv = entry * 100 * contracts
        invested += inv

        # Full loss if stopped before any TP
        if n == 0 and t['stopped']:
            pnl = -inv
            results.append(pnl)
            total += pnl
            continue

        # No TPs and not stopped = no exit data, skip
        if n == 0:
            results.append(0)
            continue

        if strategy == 'exit_tp1':
            # Sell everything at TP1
            pnl = (tps[0] - entry) * contracts * 100

        elif strategy == 'exit_tp2':
            # Sell everything at TP2 if available, else TP1
            tp_exit = tps[1] if n >= 2 else tps[0]
            pnl = (tp_exit - entry) * contracts * 100

        elif strategy == '25pct_be':
            # 25% at each TP, rest at breakeven
            remaining = contracts
            pnl = 0
            for tp in tps:
                sell = remaining * 0.25
                pnl += (tp - entry) * sell * 100
                remaining -= sell

        elif strategy == '50pct_be':
            # 50% at each TP, rest at breakeven
            remaining = contracts
            pnl = 0
            for tp in tps:
                sell = remaining * 0.50
                pnl += (tp - entry) * sell * 100
                remaining -= sell

        elif strategy == 'split_tp1_last':
            # Sell half at TP1, hold other half to last TP
            half = contracts / 2
            pnl = (tps[0] - entry) * half * 100
            pnl += (tps[-1] - entry) * half * 100

        elif strategy == 'exit_last_tp':
            # Sell everything at last TP (requires watching for no more TPs)
            pnl = (tps[-1] - entry) * contracts * 100

        total += pnl
        results.append(pnl)

    return total, invested, results

strategies = [
    ('1c — exit ALL at TP1',              1, 'exit_tp1'),
    ('2c — exit ALL at TP1',              2, 'exit_tp1'),
    ('3c — exit ALL at TP1',              3, 'exit_tp1'),
    ('1c — exit ALL at TP2 (TP1 if only 1)', 1, 'exit_tp2'),
    ('2c — exit ALL at TP2 (TP1 if only 1)', 2, 'exit_tp2'),
    ('3c — exit ALL at TP2 (TP1 if only 1)', 3, 'exit_tp2'),
    ('1c — 25% partials + BE stop',       1, '25pct_be'),
    ('2c — 25% partials + BE stop',       2, '25pct_be'),
    ('3c — 25% partials + BE stop',       3, '25pct_be'),
    ('1c — 50% partials + BE stop',       1, '50pct_be'),
    ('2c — 50% partials + BE stop',       2, '50pct_be'),
    ('3c — 50% partials + BE stop',       3, '50pct_be'),
    ('1c — half at TP1, half at last TP', 1, 'split_tp1_last'),
    ('2c — half at TP1, half at last TP', 2, 'split_tp1_last'),
    ('3c — half at TP1, half at last TP', 3, 'split_tp1_last'),
    ('1c — exit ALL at last TP',          1, 'exit_last_tp'),
    ('2c — exit ALL at last TP',          2, 'exit_last_tp'),
    ('3c — exit ALL at last TP',          3, 'exit_last_tp'),
]

print(f'{"Strategy":<45} {"P&L":>9} {"Return":>8} {"Avg/trade":>10} {"W/L"}')
print('-'*85)

best_pnl = -999999
best = None

for name, c, s in strategies:
    pnl, inv, results = calc_pnl(trades, c, s)
    ret = pnl / inv * 100
    avg = pnl / len(trades)
    wins = sum(1 for r in results if r > 0)
    losses = sum(1 for r in results if r < 0)
    marker = ''
    if pnl > best_pnl:
        best_pnl = pnl
        best = (name, c, s, pnl, inv, results)
        marker = ' ◄ BEST'
    print(f'{name:<45} ${pnl:>+8.2f} {ret:>+7.1f}% ${avg:>+9.2f}  {wins}/{losses}{marker}')

# Best detail
print(f'\n{"="*65}')
name, c, s, pnl, inv, results = best
print(f'BEST STRATEGY: {name}')
print(f'{"="*65}')
print(f'Total P&L:       ${pnl:+.2f}')
print(f'Total invested:  ${inv:.2f}')
print(f'Overall return:  {pnl/inv*100:+.1f}%')
print(f'Avg per trade:   ${pnl/len(trades):+.2f}')
print(f'\nWith £1,000 ($1,250) account:')
print(f'Net profit:      ${pnl:+.2f} ({pnl/1250*100:+.1f}% of account)')
print(f'Monthly avg:     ${pnl/5:+.2f}/month ({len(trades)} trades over ~5 months)')

# Trade by trade for best
print(f'\nTrade breakdown:')
print(f'{"#":<4}{"Date":<12}{"C/P":<6}{"Entry":<8}{"TPs":<5}{"P&L":>10}  Result')
print('-'*50)
_, _, _, _, _, res = best
total2 = 0
for i, (t, r) in enumerate(zip(trades, res)):
    total2 += r
    print(f'{i+1:<4}{t["date"]:<12}{t["type"]:<6}${t["entry"]:<7}{len(t["tps"]):<5}${r:>+8.2f}  {"WIN" if r > 0 else "LOSS" if r < 0 else "BE"}  running: ${total2:+.2f}')
