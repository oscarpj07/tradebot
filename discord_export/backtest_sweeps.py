import json
import yfinance as yf
from datetime import datetime, timedelta
from scipy.stats import norm
import math

def black_scholes(S, K, T, r, sigma, option_type):
    if T <= 0:
        if option_type == 'Call':
            return max(S - K, 0.01)
        else:
            return max(K - S, 0.01)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if option_type == 'Call':
        price = S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    else:
        price = K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
    return max(price, 0.01)

def get_field(fields, name):
    for f in fields:
        if f['name'] == name:
            return f['value']
    return None

with open('messages3.json') as f:
    messages = json.load(f)

today = datetime.today().date()
results = []
skipped = 0

r = 0.05
sigma = 0.40

print(f"Backtesting Golden Sweeps...\n")
print(f"{'Symbol':<8} {'C/P':<5} {'Strike':<9} {'Entry$':<9} {'Exit$':<9} {'Entry Opt':<11} {'Exit Val':<10} {'P&L %':<10} Result")
print("-" * 95)

for msg in messages:
    for embed in msg.get('embeds', []):
        fields = embed.get('fields', [])
        description = embed.get('description', '')

        symbol = get_field(fields, 'Symbol')
        strike_raw = get_field(fields, 'Strike')
        expiration = get_field(fields, 'Expiration')
        timestamp = embed.get('timestamp', '')

        if not all([symbol, strike_raw, expiration, timestamp]):
            skipped += 1
            continue

        # Get call/put from description
        if 'Call' in description:
            call_put = 'Call'
        elif 'Put' in description:
            call_put = 'Put'
        else:
            skipped += 1
            continue

        try:
            strike = float(strike_raw)
            alert_date = datetime.fromisoformat(timestamp).date()
            exp_date = datetime.strptime(expiration, '%m/%d/%Y').date()
            days = (exp_date - alert_date).days

            # Skip future signals
            if exp_date > today:
                skipped += 1
                continue

            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=str(alert_date), end=str(exp_date + timedelta(days=1)))

            if len(hist) < 2:
                skipped += 1
                continue

            entry_price = hist.iloc[0]['Close']
            exit_price = hist.iloc[-1]['Close']
            T_entry = max(days / 365, 0.003)

            entry_option = black_scholes(entry_price, strike, T_entry, r, sigma, call_put)

            if call_put == 'Call':
                exit_value = max(exit_price - strike, 0)
            else:
                exit_value = max(strike - exit_price, 0)

            if exit_value == 0:
                pnl_pct = -100.0
            else:
                pnl_pct = ((exit_value - entry_option) / entry_option) * 100

            win = exit_value > entry_option

            results.append({
                'symbol': symbol,
                'call_put': call_put,
                'strike': strike,
                'expiration': expiration,
                'alert_date': str(alert_date),
                'days': days,
                'entry_stock': round(entry_price, 2),
                'exit_stock': round(exit_price, 2),
                'entry_option': round(entry_option, 2),
                'exit_value': round(exit_value, 2),
                'pnl_pct': round(pnl_pct, 1),
                'win': bool(win),
            })

            status = 'WIN' if win else 'LOSS'
            print(f"{symbol:<8} {call_put:<5} ${strike:<8} ${entry_price:<8.2f} ${exit_price:<8.2f} ${entry_option:<10.2f} ${exit_value:<9.2f} {pnl_pct:>+8.1f}%  {status}")

        except Exception as e:
            skipped += 1
            continue

print(f"\nSkipped {skipped} signals (future/missing data)\n")

if results:
    wins = [r for r in results if r['win']]
    losses = [r for r in results if not r['win']]
    win_rate = len(wins) / len(results) * 100
    avg_pnl = sum(r['pnl_pct'] for r in results) / len(results)
    avg_win = sum(r['pnl_pct'] for r in wins) / len(wins) if wins else 0
    avg_loss = sum(r['pnl_pct'] for r in losses) / len(losses) if losses else 0

    calls = [r for r in results if r['call_put'] == 'Call']
    puts = [r for r in results if r['call_put'] == 'Put']
    call_wins = [r for r in calls if r['win']]
    put_wins = [r for r in puts if r['win']]

    best = max(results, key=lambda x: x['pnl_pct'])
    worst = min(results, key=lambda x: x['pnl_pct'])

    print(f"{'='*60}")
    print(f"GOLDEN SWEEP BACKTEST RESULTS")
    print(f"{'='*60}")
    print(f"Total signals:   {len(results)}")
    print(f"Win Rate:        {win_rate:.1f}%")
    print(f"Avg P&L:         {avg_pnl:+.1f}%")
    print(f"Avg Win:         {avg_win:+.1f}%")
    print(f"Avg Loss:        {avg_loss:+.1f}%")
    if calls:
        call_avg = sum(r['pnl_pct'] for r in calls) / len(calls)
        print(f"Call Win Rate:   {len(call_wins)/len(calls)*100:.1f}% ({len(call_wins)}/{len(calls)}) | Avg P&L: {call_avg:+.1f}%")
    if puts:
        put_avg = sum(r['pnl_pct'] for r in puts) / len(puts)
        print(f"Put Win Rate:    {len(put_wins)/len(puts)*100:.1f}% ({len(put_wins)}/{len(puts)}) | Avg P&L: {put_avg:+.1f}%")
    print(f"\nBest:  {best['symbol']} {best['call_put']} ({best['pnl_pct']:+.1f}%)")
    print(f"Worst: {worst['symbol']} {worst['call_put']} ({worst['pnl_pct']:+.1f}%)")

    with open('backtest_sweeps_results.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nSaved to backtest_sweeps_results.json")
