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

def dte_category(days):
    if days == 0:
        return '0DTE'
    elif days <= 2:
        return '1-2 DTE'
    elif days <= 9:
        return '3-9 DTE (weekly)'
    elif days <= 49:
        return '10-49 DTE (monthly)'
    else:
        return '50+ DTE (LEAPS)'

with open('signals_75plus.json') as f:
    signals = json.load(f)

today = datetime.today().date()
results = []
skipped_future = 0
skipped_data = 0

r = 0.05
sigma = 0.40

print(f"Backtesting signals with P&L estimates (expired only)...\n")
print(f"{'Symbol':<8} {'C/P':<5} {'Conf':<7} {'DTE':<5} {'Entry$':<9} {'Exit$':<9} {'Entry Opt':<11} {'Exit Val':<10} {'P&L %':<10} Result")
print("-" * 100)

for s in signals:
    symbol = s['symbol']
    call_put = s['call_put']
    expiration = s['expiration']
    alert_time = s['timestamp']
    confidence = s['ai_confidence']

    try:
        strike = float(s['strike'])
        alert_date = datetime.fromisoformat(alert_time).date()
        exp_date = datetime.strptime(expiration, '%m/%d/%Y').date()
        days = (exp_date - alert_date).days

        # Skip future signals
        if exp_date > today:
            skipped_future += 1
            continue

        ticker = yf.Ticker(symbol)

        if days == 0:
            # 0DTE: get intraday open vs close on expiry day
            hist = ticker.history(start=str(exp_date), end=str(exp_date + timedelta(days=1)))
            if hist.empty:
                skipped_data += 1
                continue
            entry_price = hist.iloc[0]['Open']
            exit_price = hist.iloc[0]['Close']
            T_entry = 0.5 / 365  # assume ~half day left
        else:
            hist = ticker.history(start=str(alert_date), end=str(exp_date + timedelta(days=1)))
            if len(hist) < 2:
                skipped_data += 1
                continue
            entry_price = hist.iloc[0]['Close']
            exit_price = hist.iloc[-1]['Close']
            T_entry = days / 365

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
        category = dte_category(days)

        results.append({
            'symbol': symbol,
            'call_put': call_put,
            'strike': strike,
            'expiration': expiration,
            'alert_date': str(alert_date),
            'days': days,
            'dte_category': category,
            'ai_confidence': confidence,
            'entry_stock': round(entry_price, 2),
            'exit_stock': round(exit_price, 2),
            'entry_option': round(entry_option, 2),
            'exit_value': round(exit_value, 2),
            'pnl_pct': round(pnl_pct, 1),
            'win': bool(win),
        })

        status = 'WIN' if win else 'LOSS'
        print(f"{symbol:<8} {call_put:<5} {confidence:<7.1f} {days:<5} ${entry_price:<8.2f} ${exit_price:<8.2f} ${entry_option:<10.2f} ${exit_value:<9.2f} {pnl_pct:>+8.1f}%  {status}")

    except Exception as e:
        skipped_data += 1
        continue

# Summary
print(f"\nSkipped {skipped_future} future signals, {skipped_data} missing data\n")

if results:
    categories = ['0DTE', '1-2 DTE', '3-9 DTE (weekly)', '10-49 DTE (monthly)', '50+ DTE (LEAPS)']

    print(f"{'='*70}")
    print(f"BACKTEST RESULTS BY DTE CATEGORY (70%+ AI Confidence)")
    print(f"{'='*70}")
    print(f"{'Category':<22} {'Trades':<8} {'Wins':<7} {'Win%':<8} {'Avg P&L':<12} {'Avg Win':<12} {'Avg Loss'}")
    print(f"-"*70)

    all_wins = [r for r in results if r['win']]
    all_losses = [r for r in results if not r['win']]

    for cat in categories:
        group = [r for r in results if r['dte_category'] == cat]
        if not group:
            continue
        wins = [r for r in group if r['win']]
        losses = [r for r in group if not r['win']]
        win_rate = len(wins) / len(group) * 100
        avg_pnl = sum(r['pnl_pct'] for r in group) / len(group)
        avg_win = sum(r['pnl_pct'] for r in wins) / len(wins) if wins else 0
        avg_loss = sum(r['pnl_pct'] for r in losses) / len(losses) if losses else 0
        print(f"{cat:<22} {len(group):<8} {len(wins):<7} {win_rate:<8.1f} {avg_pnl:>+10.1f}%  {avg_win:>+10.1f}%  {avg_loss:>+10.1f}%")

    print(f"-"*70)
    total = len(results)
    overall_win_rate = len(all_wins) / total * 100
    overall_avg = sum(r['pnl_pct'] for r in results) / total
    avg_win_overall = sum(r['pnl_pct'] for r in all_wins) / len(all_wins) if all_wins else 0
    avg_loss_overall = sum(r['pnl_pct'] for r in all_losses) / len(all_losses) if all_losses else 0
    print(f"{'OVERALL':<22} {total:<8} {len(all_wins):<7} {overall_win_rate:<8.1f} {overall_avg:>+10.1f}%  {avg_win_overall:>+10.1f}%  {avg_loss_overall:>+10.1f}%")

    best = max(results, key=lambda x: x['pnl_pct'])
    worst = min(results, key=lambda x: x['pnl_pct'])
    print(f"\nBest:  {best['symbol']} {best['call_put']} {best['dte_category']} ({best['pnl_pct']:+.1f}%)")
    print(f"Worst: {worst['symbol']} {worst['call_put']} {worst['dte_category']} ({worst['pnl_pct']:+.1f}%)")

    with open('backtest_pnl_results.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nSaved to backtest_pnl_results.json")
