# Case Study — Automated Options Trading Bot

## The Problem

A profitable options trader was posting signals manually in a paid Discord server. Followers had to watch the channel constantly and execute trades by hand — missing entries, slow on exits, and making emotional decisions under pressure.

## The Solution

I built a fully automated trading bot in Python that:
- Monitors the Discord channel 24/7
- Instantly detects entry, take profit, and exit signals
- Executes orders automatically via the Alpaca brokerage API
- Manages the full trade lifecycle without any manual input

## Backtesting

Before building the bot I backtested 31 trades from the trader's signal history to find the optimal exit strategy.

| Strategy | Return | Win Rate |
|---|---|---|
| Exit all at TP2 | +63% | 87% |
| 25% partials + breakeven stop | -8% | 87% |
| Exit all at TP1 | +31% | 87% |

Key finding: the trader's own method (25% partials) was actually slightly negative at small contract sizes. Exiting the full position at TP2 was the most profitable approach.

## Results

- 31 trades analysed over 5 months
- 87% win rate overall (90% calls, 80% puts)
- +63% return on a $1,250 account using the TP2 exit strategy
- Bot tested and running on Alpaca paper trading account

## Tech Stack

Python, discord.py-self, Alpaca API, asyncio, dotenv

## What I Built

- Signal parser for emoji-based Discord messages
- Async event handler with TP counting logic
- Alpaca order executor (limit and market orders)
- Full backtest suite comparing 18 different exit strategies
- Offline test suite with 5 scenarios, all passing

---

Built by Oscar — Python Developer | Available on Fiverr & Upwork
