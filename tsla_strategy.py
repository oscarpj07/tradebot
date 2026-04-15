"""
TSLA Trailing Stop + Ladder Strategy
- Buys 10 shares at market
- Hard stop loss at -10% from entry
- Trailing stop activates at +10%, trails 5% below peak
- Ladders in: -20% → buy 20 shares, -30% → buy 10 shares
"""

import time
import logging
import os
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

# ── Strategy config ───────────────────────────────────────────────────────────
TICKER          = "TSLA"
INITIAL_SHARES  = 10
HARD_STOP_PCT   = 0.10   # sell all if down 10% from entry
TRAIL_TRIGGER   = 0.10   # activate trailing stop when up 10%
TRAIL_OFFSET    = 0.05   # trail 5% below current peak
LADDER_LEVELS   = [
    (0.20, 20),  # down 20% → buy 20 shares
    (0.30, 10),  # down 30% → buy 10 more shares
]
POLL_INTERVAL = 30  # seconds between price checks


def get_price(data_client):
    req = StockLatestQuoteRequest(symbol_or_symbols=TICKER)
    quote = data_client.get_stock_latest_quote(req)
    q = quote[TICKER]
    # Use midpoint if both sides available, else whichever exists
    ask = float(q.ask_price) if q.ask_price else None
    bid = float(q.bid_price) if q.bid_price else None
    if ask and bid:
        return (ask + bid) / 2
    return ask or bid


def place_order(client, qty, side):
    order = MarketOrderRequest(
        symbol=TICKER,
        qty=qty,
        side=side,
        time_in_force=TimeInForce.DAY
    )
    return client.submit_order(order)


def print_summary(entry_price, total_shares):
    print("\n" + "=" * 60)
    print("ORDER SUMMARY — TSLA STRATEGY")
    print("=" * 60)
    print(f"  Initial buy       : {INITIAL_SHARES} shares @ ${entry_price:.2f}")
    print(f"  Total cost        : ${entry_price * total_shares:,.2f}")
    print(f"  Hard stop loss    : ${entry_price * (1 - HARD_STOP_PCT):.2f}  (-{HARD_STOP_PCT*100:.0f}% from entry)")
    print(f"  Trailing activates: ${entry_price * (1 + TRAIL_TRIGGER):.2f}  (+{TRAIL_TRIGGER*100:.0f}% from entry)")
    print(f"  Trail offset      : 5% below running peak")
    print()
    print("  Ladder buy orders:")
    for pct, shares in LADDER_LEVELS:
        print(f"    -{pct*100:.0f}% (${entry_price * (1-pct):.2f}) → BUY {shares} shares")
    print()
    print("  ⚠  Note: Hard stop at -10% will trigger before ladder")
    print("     levels (-20%, -30%) under normal conditions.")
    print("     Ladder protects against gap-down scenarios.")
    print("=" * 60 + "\n")


def main():
    client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)
    data_client = StockHistoricalDataClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)

    account = client.get_account()
    log.info(f"Connected — Buying power: ${float(account.buying_power):,.2f}")

    # ── Initial buy ───────────────────────────────────────────────────────────
    log.info(f"Placing initial BUY: {INITIAL_SHARES} shares of {TICKER}")
    order = place_order(client, INITIAL_SHARES, OrderSide.BUY)
    log.info(f"Order placed — ID: {order.id} | Status: {order.status}")

    time.sleep(2)  # let order settle

    entry_price = get_price(data_client)
    log.info(f"Entry price: ${entry_price:.2f}")

    total_shares = INITIAL_SHARES
    trailing_active = False
    trailing_stop = None
    peak_price = entry_price
    ladders_triggered = set()

    print_summary(entry_price, total_shares)

    log.info("Monitoring started. Press Ctrl+C to stop without closing position.")

    # ── Monitoring loop ───────────────────────────────────────────────────────
    while True:
        try:
            price = get_price(data_client)
            pct = (price - entry_price) / entry_price

            status = f"${price:.2f}  |  entry ${entry_price:.2f}  |  {pct*100:+.2f}%  |  {total_shares} shares"
            if trailing_active:
                status += f"  |  trail stop ${trailing_stop:.2f}"
            log.info(status)

            # ── Hard stop loss ────────────────────────────────────────────────
            if pct <= -HARD_STOP_PCT:
                log.warning(f"HARD STOP triggered at ${price:.2f} ({pct*100:.2f}%) — selling all {total_shares} shares")
                place_order(client, total_shares, OrderSide.SELL)
                log.info("Position closed. Strategy complete.")
                break

            # ── Ladder in on dips ─────────────────────────────────────────────
            for drop_pct, shares in LADDER_LEVELS:
                if drop_pct not in ladders_triggered and pct <= -drop_pct:
                    log.info(f"LADDER at -{drop_pct*100:.0f}%: buying {shares} more shares @ ${price:.2f}")
                    place_order(client, shares, OrderSide.BUY)
                    total_shares += shares
                    ladders_triggered.add(drop_pct)
                    log.info(f"Total shares now: {total_shares}")

            # ── Trailing stop ─────────────────────────────────────────────────
            if pct >= TRAIL_TRIGGER:
                if not trailing_active:
                    trailing_active = True
                    trailing_stop = price * (1 - TRAIL_OFFSET)
                    peak_price = price
                    log.info(f"TRAILING STOP activated — stop set at ${trailing_stop:.2f}")

                if price > peak_price:
                    peak_price = price
                    trailing_stop = peak_price * (1 - TRAIL_OFFSET)
                    log.info(f"New peak ${peak_price:.2f} — stop raised to ${trailing_stop:.2f}")

                if price <= trailing_stop:
                    log.info(f"TRAILING STOP hit at ${price:.2f} (stop ${trailing_stop:.2f}) — selling all {total_shares} shares")
                    place_order(client, total_shares, OrderSide.SELL)
                    log.info("Position closed. Strategy complete.")
                    break

            time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            log.info("Stopped by user — position left open.")
            break
        except Exception as e:
            log.error(f"Error: {e}")
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
