import sys
import logging
from datetime import date, timedelta
from dotenv import load_dotenv
import os
import re

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
ALPACA_BASE_URL = "https://paper-api.alpaca.markets"

# ── Signal parser ────────────────────────────────────────────────────────────

def parse_signal(msg: str):
    pattern = r'(\w{1,5})\s+(\d+(?:\.\d+)?)\s+(PUTS|CALLS)\s+@\s+([\d.]+)'
    match = re.search(pattern, msg.upper())
    if not match:
        return None
    ticker, strike, direction, price = match.groups()
    msg_upper = msg.upper()
    if "ENTRY" in msg_upper:
        action = "BUY"
    elif "TAKE PROFIT" in msg_upper:
        action = "SELL"
    else:
        return None
    return {
        "ticker": ticker,
        "strike": float(strike),
        "direction": direction,
        "price": float(price),
        "action": action
    }

# ── Alpaca order ─────────────────────────────────────────────────────────────

def place_alpaca_paper_order(signal):
    try:
        from alpaca.trading.client import TradingClient
        from alpaca.trading.requests import GetOptionContractsRequest, LimitOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce, AssetStatus, ContractType
    except ImportError:
        log.error("alpaca-py not installed. Run: pip install alpaca-py")
        return

    client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)

    ticker = signal["ticker"]
    strike = signal["strike"]
    direction = signal["direction"]
    price = signal["price"]
    action = signal["action"]
    today = date.today()

    # Find 0DTE option contract
    contract_type = ContractType.PUT if direction == "PUTS" else ContractType.CALL

    request = GetOptionContractsRequest(
        underlying_symbols=[ticker],
        expiration_date=today,
        strike_price_gte=str(strike - 1),
        strike_price_lte=str(strike + 1),
        type=contract_type,
        status=AssetStatus.ACTIVE
    )

    contracts = client.get_option_contracts(request)

    if not contracts.option_contracts:
        log.error(f"No 0DTE contract found for {ticker} {strike} {direction} expiring {today}")
        # Try next trading day (weekends/holidays)
        next_day = today + timedelta(days=1)
        request.expiration_date = next_day
        contracts = client.get_option_contracts(request)
        if not contracts.option_contracts:
            log.error("No contract found for next day either. Check ticker/strike.")
            return

    contract = contracts.option_contracts[0]
    log.info(f"Found contract: {contract.symbol} (strike: {contract.strike_price}, expiry: {contract.expiration_date})")

    # Place limit order
    side = OrderSide.BUY if action == "BUY" else OrderSide.SELL

    order_request = LimitOrderRequest(
        symbol=contract.symbol,
        qty=1,
        side=side,
        time_in_force=TimeInForce.DAY,
        limit_price=price
    )

    order = client.submit_order(order_request)
    log.info(f"Paper order placed!")
    log.info(f"  Order ID : {order.id}")
    log.info(f"  Symbol   : {order.symbol}")
    log.info(f"  Side     : {order.side}")
    log.info(f"  Qty      : {order.qty}")
    log.info(f"  Price    : ${price}")
    log.info(f"  Status   : {order.status}")

# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Accept signal from command line or use default test signal
    if len(sys.argv) > 1:
        raw = " ".join(sys.argv[1:])
    else:
        raw = "🟡 QQQ 580 PUTS @ 1.15 🟡 ## ENTRY"

    print(f"\nTesting signal: {raw}\n")

    signal = parse_signal(raw)
    if not signal:
        print("Could not parse signal. Check format.")
        sys.exit(1)

    print(f"Parsed: {signal}\n")
    place_alpaca_paper_order(signal)
