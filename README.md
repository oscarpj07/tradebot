# Tradebot — Discord Option Embed Copier

A Python trading bot that monitors a Discord channel for live options trade embeds and mirrors those entries/exits to Alpaca paper trading.

## What It Does

- Monitors one configured Discord channel in real time
- Reads Discord embed alerts, not just plain message text
- Opens option positions from `LIVE ENTRY` embeds
- Places broker-side exit protection from entry embeds when prices are supplied
- Sells option contracts from `LIVE EXIT` embeds
- Uses the quantity shown in each embed
- Tracks separate trades by ticker, strike, direction, model ID, and source
- Runs as a user `systemd` service so it keeps working after the terminal closes

## Current Signal Layout

The current supported server layout is the `0DTE Live Apex` style embed.

### Live Entry

The bot looks for embeds with titles/descriptions like:

```text
LIVE ENTRY — Most Stable MultiConf
CALL position opened on SPY $740.0 strike
```

Required embed fields:

```text
Strike: $740.0
Type: CALL
Entry Price: $0.78
Quantity: 3 contracts
Take Profit: +100% ($1.56)
Stop Loss: -80% ($0.16)
Model ID: MSP_TripleEMA
Source: 0DTE_Most_Stable_Profitable
```

That becomes an Alpaca paper `BUY` order for 3 SPY 740 calls. If the entry includes `Take Profit` and `Stop Loss` dollar prices, the bot keeps the stop loss live as an Alpaca stop order and monitors the option's current price for the take-profit level. When the current price reaches the take-profit price, the bot cancels the stop and sells the contract at market.

### Live Exit

The bot looks for embeds with titles like:

```text
LIVE EXIT — Most Stable MultiConf
```

Required embed fields:

```text
Strike: $740.0 CALL
Exit Price: $0.81
Qty: 2 contracts
Model ID: MSP_TripleEMA
Source: 0DTE_Most_Stable_Profitable
```

That becomes an Alpaca paper `SELL` order for 2 contracts. If the original entry had 3 contracts, the bot keeps 1 contract open internally.

If the broker-side stop loss or bot-side take profit has already closed the option before a `LIVE EXIT` arrives, the bot checks the live Alpaca position quantity first and clears stale local state instead of sending another sell.

## Trade Matching

For the new embed format, trades are matched by:

```text
ticker + strike + CALL/PUT + Model ID + Source
```

This lets the bot handle multiple SPY alerts on the same strike without overwriting them when they come from different models or sources.

Legacy plain-text signals such as `ENTRY QQQ 480 PUTS @ 1.25` are still parsed for compatibility, but the active workflow is the live embed layout above.

## Tech Stack

- Python 3.11
- `discord.py-self` for Discord monitoring
- `alpaca-py` for Alpaca paper trading
- `python-dotenv` for local credentials
- `systemd` user service for continuous running

## Project Structure

```text
tradebot/
├── main.py                  # Entry point and process lock
├── discord_watcher.py       # Discord monitoring and signal parsing
├── alpaca_executor.py       # Alpaca paper order execution
├── config.py                # Environment variable loading
├── test_logic.py            # Offline parser/state tests
├── scripts/                 # systemd helper scripts
└── systemd/tradebot.service # user service definition
```

## Setup

1. Create a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

2. Install dependencies:

```bash
pip install discord.py-self alpaca-py python-dotenv
```

3. Create a `.env` file with your credentials:

```text
DISCORD_TOKEN=your_discord_token
DISCORD_CHANNEL_ID=1498008564730429690
ALPACA_API_KEY=your_alpaca_key
ALPACA_SECRET_KEY=your_alpaca_secret
CONTRACTS=1
```

4. Run the offline tests:

```bash
./venv/bin/python test_logic.py
```

5. Run manually if needed:

```bash
./venv/bin/python main.py
```

## Running Continuously

Use the user `systemd` service when the bot should keep running after the terminal closes and restart automatically if it crashes:

```bash
./scripts/install_service.sh
```

Useful service commands:

```bash
./scripts/status_service.sh
./scripts/logs_service.sh
./scripts/stop_service.sh
./scripts/start_service.sh
```

The service runs:

```bash
/home/pjoscar126/tradebot/venv/bin/python /home/pjoscar126/tradebot/main.py
```

Logs are available through:

```bash
journalctl --user -u tradebot.service -f
```

## Safety Notes

- The bot currently uses Alpaca paper trading.
- `.env` must not be committed.
- Discord tokens and GitHub tokens should be treated like passwords.
- Past results from any strategy or server do not guarantee future performance.
