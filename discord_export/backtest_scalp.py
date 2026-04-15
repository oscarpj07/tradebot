import json
import yfinance as yf
from datetime import datetime, timedelta

def get_field(fields, name):
    for f in fields:
        if f['name'] == name:
            return f['value']
    return None

with open('messages2.json') as f:
    messages = json.load(f)

# Parse signals
signals = []
for msg in messages:
    for embed in msg.get('embeds', []):
        fields = embed.get('fields', [])
        symbol = get_field(fields, 'Symbol')
        entry = get_field(fields, 'Entry')
        position = get_field(fields, 'Position')
        target = get_field(fields, 'Target')
        stoploss = get_field(fields, 'Stoploss')
        potential = get_field(fields, 'Potential Profit')
        timestamp = embed.get('timestamp', '')
        description = embed.get('description', '')

        if not all([symbol, entry, position, target, stoploss]):
            continue

        signals.append({
            'symbol': symbol,
            'entry': float(entry),
            'position': position,
            'target': float(target),
            'stoploss': float(stoploss),
            'potential_profit': float(potential) if potential else 0,
            'timestamp': timestamp,
            'description': description,
        })

print(f"Found {len(signals)} scalp signals\n")
print(f"{'Symbol':<8} {'Position':<8} {'Entry':<9} {'Target':<9} {'Stop':<9} {'Result':<8} P&L%")
print("-" * 65)

results = []
today = datetime.today().date()

for s in signals:
    symbol = s['symbol']
    entry = s['entry']
    target = s['target']
    stoploss = s['stoploss']
    position = s['position']
    alert_time = s['timestamp']

    try:
        alert_date = datetime.fromisoformat(alert_time).date()

        # Look at next 5 trading days for target/stop to be hit
        end_date = alert_date + timedelta(days=7)
        if end_date > today:
            end_date = today

        ticker = yf.Ticker(symbol)
        hist = ticker.history(start=str(alert_date), end=str(end_date + timedelta(days=1)), interval='1h')

        if hist.empty:
            continue

        result = None
        exit_price = None

        for _, bar in hist.iterrows():
            high = bar['High']
            low = bar['Low']

            if position == 'Long':
                if low <= stoploss:
                    result = 'LOSS'
                    exit_price = stoploss
                    break
                if high >= target:
                    result = 'WIN'
                    exit_price = target
                    break
            else:  # Short
                if high >= stoploss:
                    result = 'LOSS'
                    exit_price = stoploss
                    break
                if low <= target:
                    result = 'WIN'
                    exit_price = target
                    break

        if result is None:
            result = 'OPEN'
            exit_price = hist.iloc[-1]['Close']

        if position == 'Long':
            pnl_pct = ((exit_price - entry) / entry) * 100
        else:
            pnl_pct = ((entry - exit_price) / entry) * 100

        results.append({
            'symbol': symbol,
            'position': position,
            'entry': entry,
            'target': target,
            'stoploss': stoploss,
            'alert_date': str(alert_date),
            'description': s['description'],
            'result': result,
            'exit_price': round(exit_price, 2),
            'pnl_pct': round(pnl_pct, 2),
        })

        print(f"{symbol:<8} {position:<8} ${entry:<8} ${target:<8} ${stoploss:<8} {result:<8} {pnl_pct:+.2f}%")

    except Exception as e:
        print(f"{symbol} - skipped ({e})")
        continue

# Summary
closed = [r for r in results if r['result'] != 'OPEN']
wins = [r for r in closed if r['result'] == 'WIN']
losses = [r for r in closed if r['result'] == 'LOSS']
open_trades = [r for r in results if r['result'] == 'OPEN']

if closed:
    win_rate = len(wins) / len(closed) * 100
    avg_pnl = sum(r['pnl_pct'] for r in closed) / len(closed)
    avg_win = sum(r['pnl_pct'] for r in wins) / len(wins) if wins else 0
    avg_loss = sum(r['pnl_pct'] for r in losses) / len(losses) if losses else 0

    longs = [r for r in closed if r['position'] == 'Long']
    shorts = [r for r in closed if r['position'] == 'Short']
    long_wins = [r for r in longs if r['result'] == 'WIN']
    short_wins = [r for r in shorts if r['result'] == 'WIN']

    print(f"\n{'='*60}")
    print(f"SCALP BACKTEST RESULTS")
    print(f"{'='*60}")
    print(f"Total signals:   {len(signals)}")
    print(f"Closed trades:   {len(closed)}")
    print(f"Open/incomplete: {len(open_trades)}")
    print(f"Win Rate:        {win_rate:.1f}%")
    print(f"Avg P&L:         {avg_pnl:+.2f}%")
    print(f"Avg Win:         {avg_win:+.2f}%")
    print(f"Avg Loss:        {avg_loss:+.2f}%")
    if longs:
        print(f"Long Win Rate:   {len(long_wins)/len(longs)*100:.1f}% ({len(long_wins)}/{len(longs)})")
    if shorts:
        print(f"Short Win Rate:  {len(short_wins)/len(shorts)*100:.1f}% ({len(short_wins)}/{len(shorts)})")

    if results:
        best = max(closed, key=lambda x: x['pnl_pct'])
        worst = min(closed, key=lambda x: x['pnl_pct'])
        print(f"\nBest:  {best['symbol']} {best['position']} ({best['pnl_pct']:+.2f}%)")
        print(f"Worst: {worst['symbol']} {worst['position']} ({worst['pnl_pct']:+.2f}%)")

with open('backtest_scalp_results.json', 'w') as f:
    json.dump(results, f, indent=2, default=str)
print(f"\nSaved to backtest_scalp_results.json")
