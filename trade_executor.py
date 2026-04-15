import logging
from datetime import date
from tastytrade import Session, Account
from tastytrade.instruments import Option
from tastytrade.order import (
    NewOrder, OrderAction, OrderTimeInForce,
    OrderType, InstrumentType, Leg
)
from config import TT_USERNAME, TT_API_TOKEN, CONTRACTS

log = logging.getLogger(__name__)

class TradeExecutor:
    def __init__(self):
        self.session = None
        self.account = None
        self.open_positions = {}  # (ticker, strike, direction) -> option_symbol

    def connect(self):
        self.session = Session(TT_USERNAME, remember_token=TT_API_TOKEN)
        accounts = Account.get_accounts(self.session)
        self.account = accounts[0]
        log.info(f"Connected to Tastytrade account: {self.account.account_number}")

    def find_option_symbol(self, ticker, strike, direction):
        option_type = "P" if direction == "PUTS" else "C"
        today = date.today()

        # 0DTE — must expire today
        chain = Option.get_options(self.session, ticker)
        candidates = [
            o for o in chain
            if o.strike_price == strike
            and o.option_type == option_type
            and o.expiration_date == today
        ]

        if not candidates:
            log.error(f"No 0DTE option found: {ticker} {strike} {direction} expiring {today}")
            return None

        symbol = candidates[0].symbol
        log.info(f"Found 0DTE option: {symbol} (expiry: {today})")
        return symbol

    async def handle_signal(self, signal):
        ticker = signal["ticker"]
        strike = signal["strike"]
        direction = signal["direction"]
        price = signal["price"]
        action = signal["action"]
        key = (ticker, strike, direction)

        if action == "BUY":
            option_symbol = self.find_option_symbol(ticker, strike, direction)
            if not option_symbol:
                return
            self.open_positions[key] = option_symbol
            order_action = OrderAction.BUY_TO_OPEN

        elif action == "SELL":
            option_symbol = self.open_positions.get(key)
            if not option_symbol:
                log.warning(f"No open position found for {key} — skipping sell")
                return
            order_action = OrderAction.SELL_TO_CLOSE

        leg = Leg(
            instrument_type=InstrumentType.EQUITY_OPTION,
            symbol=option_symbol,
            quantity=CONTRACTS,
            action=order_action
        )

        order = NewOrder(
            time_in_force=OrderTimeInForce.DAY,
            order_type=OrderType.LIMIT,
            price=price,
            legs=[leg]
        )

        try:
            response = self.account.place_order(self.session, order, dry_run=True)
            log.info(f"[DRY RUN] Order placed: {action} {CONTRACTS}x {ticker} {strike} {direction} @ {price}")
            log.info(f"Order ID: {response.order.id}")

            if action == "SELL":
                del self.open_positions[key]

        except Exception as e:
            log.error(f"Order failed: {e}")

    async def close_position(self, ticker, strike, direction, price=None):
        """Close an open position. price=None means market order."""
        key = (ticker, strike, direction)
        option_symbol = self.open_positions.get(key)
        if not option_symbol:
            log.warning(f"close_position: no open position for {key} — skipping")
            return

        leg = Leg(
            instrument_type=InstrumentType.EQUITY_OPTION,
            symbol=option_symbol,
            quantity=CONTRACTS,
            action=OrderAction.SELL_TO_CLOSE
        )

        order = NewOrder(
            time_in_force=OrderTimeInForce.DAY,
            order_type=OrderType.MARKET if price is None else OrderType.LIMIT,
            price=price,
            legs=[leg]
        )

        try:
            response = self.account.place_order(self.session, order, dry_run=True)
            order_type_str = "MARKET" if price is None else f"LIMIT @ {price}"
            log.info(f"[DRY RUN] Position closed: {CONTRACTS}x {ticker} {strike} {direction} {order_type_str}")
            log.info(f"Order ID: {response.order.id}")
            del self.open_positions[key]
        except Exception as e:
            log.error(f"close_position failed: {e}")
