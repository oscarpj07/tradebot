# Automated Trading Bot — Discord Signal Copier

A Python-based automated trading system that monitors a Discord channel for options trading signals and executes trades automatically via the Alpaca API (paper and live trading supported).

## What It Does

- Monitors a Discord channel in real time for trading signals
- Parses entry, take profit, and exit signals automatically
- Executes limit and market orders via Alpaca brokerage API
- Implements a TP2 exit strategy based on backtested performance data
- Handles edge cases: breakeven stops, full loss exits, new entry while trade is open

## Backtest Results (QQQ 0DTE Options — 31 Trades)

- Win Rate: 87%
- Best Strategy: Exit all contracts at TP2
- Return: +63% on a $1,250 account over 5 months
- Avg win: significantly higher than avg loss
- Calls win rate: 90% | Puts win rate: 80%

## Tech Stack

- Python 3.11
- discord.py-self — Discord channel monitoring
- Alpaca API (alpaca-py) — order execution (paper and live)
- asyncio — asynchronous event handling
- dotenv — secure credential management

## Project Structure

```
tradebot/
├── main.py                  # Entry point
├── discord_watcher.py       # Discord monitoring and signal parsing
├── alpaca_executor.py       # Alpaca order execution
├── trade_executor.py        # Tastytrade order execution (alternative)
├── config.py                # Environment variable loading
├── discord_export/
│   ├── backtest_final.py    # Final backtest with 25% partial model
│   ├── backtest_best.py     # Strategy comparison across all exit methods
│   ├── backtest_optimize.py # Parameter optimisation
│   └── analyze_entries.py  # Entry context analysis (VWAP, trend)
```

## Signal Format

The bot parses the following Discord message formats:

| Signal | Emoji | Example |
|--------|-------|---------|
| Entry  | 🟡    | `🟡 ENTRY QQQ 480 PUTS @ 1.25` |
| Take Profit | 🟢 | `🟢 TAKE PROFIT QQQ 480 PUTS @ 1.85` |
| Exit   | 🔴    | `🔴 EXIT QQQ 480 PUTS` |

## Exit Strategy Logic

Based on backtesting, the optimal strategy is to exit the full position at TP2:

- **TP1 received** — hold, wait for TP2
- **TP2 received** — close full position at limit price
- **EXIT with no TP** — close at market (full loss)
- **EXIT after TP1** — close at entry price (breakeven)
- **New entry while trade open** — close previous position at market first

## Setup

1. Clone the repo
2. Create a virtual environment: `python3 -m venv venv && source venv/bin/activate`
3. Install dependencies: `pip install discord.py-self alpaca-py python-dotenv`
4. Create a `.env` file with your credentials:

```
DISCORD_TOKEN=your_discord_token
DISCORD_CHANNEL_ID=your_channel_id
ALPACA_API_KEY=your_alpaca_key
ALPACA_SECRET_KEY=your_alpaca_secret
CONTRACTS=1
```

5. Run: `python main.py`

## Running in Background

```bash
nohup python main.py > bot.log 2>&1 &
```

## Disclaimer

This project is for educational purposes. Past backtest performance does not guarantee future results. Always paper trade before going live.
