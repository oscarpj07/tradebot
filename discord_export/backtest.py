import json
import yfinance as yf
from datetime import datetime, timedelta

with open('signals_75plus.json') as f:
    signals = json.load(f)

results = []

print(f"Backtesting {len(signals)} signals...\n")

for s in signals:
    symbol = s['symbol']
    call_put = s['call_put']
    expiration = s['expiration']
    alert_time = s['timestamp']
    confidence = s['ai_confidence']

    try:
        alert_date = datetime.fromisoformat(alert_time).date()
        exp_date = datetime.strptime(expiration, '%m/%d/%Y').date()

        # Fetch stock history
        ticker = yf.Ticker(symbol)
        hist = ticker.history(start=str(alert_date), end=str(exp_date + timedelta(days=1)))

        if len(hist) < 2:
            continue

        entry_price = hist.iloc[0]['Close']
        exit_price = hist.iloc[-1]['Close']
        pct_change = ((exit_price - entry_price) / entry_price) * 100

        if call_put == 'Call':
            win = exit_price > entry_price
        else:
            win = exit_price < entry_price

        results.append({
            'symbol': symbol,
            'call_put': call_put,
            'strike': s['strike'],
            'expiration': expiration,
            'alert_date': str(alert_date),
            'ai_confidence': confidence,
            'entry_price': round(entry_price, 2),
            'exit_price': round(exit_price, 2),
            'pct_change': round(pct_change, 2),
            'win': bool(win),
        })

        status = 'WIN' if win else 'LOSS'
        print(f"{symbol:<8} {call_put:<5} {confidence:.1f}%  {str(alert_date):<12} entry={entry_price:.2f} exit={exit_price:.2f} ({pct_change:+.2f}%)  {status}")

    except Exception as e:
        print(f"{symbol} - skipped ({e})")
        continue

# Summary
if results:
    wins = sum(1 for r in results if r['win'])
    total = len(results)
    win_rate = (wins / total) * 100

    calls = [r for r in results if r['call_put'] == 'Call']
    puts = [r for r in results if r['call_put'] == 'Put']
    call_wins = sum(1 for r in calls if r['win'])
    put_wins = sum(1 for r in puts if r['win'])

    print(f"\n{'='*60}")
    print(f"BACKTEST RESULTS (70%+ AI Confidence)")
    print(f"{'='*60}")
    print(f"Total signals:  {total}")
    print(f"Wins:           {wins}")
    print(f"Losses:         {total - wins}")
    print(f"Win Rate:       {win_rate:.1f}%")
    if calls:
        print(f"Call Win Rate:  {(call_wins/len(calls)*100):.1f}% ({call_wins}/{len(calls)})")
    if puts:
        print(f"Put Win Rate:   {(put_wins/len(puts)*100):.1f}% ({put_wins}/{len(puts)})")

    with open('backtest_results.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nFull results saved to backtest_results.json")
