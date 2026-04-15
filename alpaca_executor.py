import logging
from datetime import date, timedelta
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOptionContractsRequest, LimitOrderRequest, MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce, AssetStatus, ContractType
from config import ALPACA_API_KEY, ALPACA_SECRET_KEY, CONTRACTS

log = logging.getLogger(__name__)


class AlpacaExecutor:
    def __init__(self):
        self.client = None
        self.open_positions = {}  # (ticker, strike, direction) -> contract_symbol

    def connect(self):
        self.client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)
        account = self.client.get_account()
        log.info(f"Connected to Alpaca paper account: {account.account_number}")
        log.info(f"Buying power: ${float(account.buying_power):,.2f}")

    def find_option_symbol(self, ticker, strike, direction):
        contract_type = ContractType.PUT if direction == "PUTS" else ContractType.CALL
        today = date.today()

        for expiry in [today, today + timedelta(days=1), today + timedelta(days=2)]:
            request = GetOptionContractsRequest(
                underlying_symbols=[ticker],
                expiration_date=expiry,
                strike_price_gte=str(strike - 0.5),
                strike_price_lte=str(strike + 0.5),
                type=contract_type,
                status=AssetStatus.ACTIVE
            )
            contracts = self.client.get_option_contracts(request)
            if contracts.option_contracts:
                symbol = contracts.option_contracts[0].symbol
                log.info(f"Found contract: {symbol} (expiry: {expiry})")
                return symbol

        log.error(f"No contract found for {ticker} {strike} {direction}")
        return None

    async def handle_signal(self, signal):
        ticker = signal["ticker"]
        strike = signal["strike"]
        direction = signal["direction"]
        price = signal["price"]
        action = signal["action"]
        key = (ticker, strike, direction)

        if action == "BUY":
            symbol = self.find_option_symbol(ticker, strike, direction)
            if not symbol:
                return
            self.open_positions[key] = symbol

            order = LimitOrderRequest(
                symbol=symbol,
                qty=CONTRACTS,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY,
                limit_price=round(price, 2)
            )

        elif action == "SELL":
            symbol = self.open_positions.get(key)
            if not symbol:
                log.warning(f"No open position for {key} — skipping sell")
                return

            # Use market order to guarantee fill — limit orders can miss if bid is below target
            order = MarketOrderRequest(
                symbol=symbol,
                qty=CONTRACTS,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
            )

        try:
            response = self.client.submit_order(order)
            log.info(f"[ALPACA PAPER] {action} {CONTRACTS}x {ticker} {strike} {direction} @ ${price} — Order ID: {response.id}")
            if action == "SELL":
                del self.open_positions[key]
        except Exception as e:
            log.error(f"Order failed: {e}")

    async def close_position(self, ticker, strike, direction, price=None):
        key = (ticker, strike, direction)
        symbol = self.open_positions.get(key)
        if not symbol:
            log.warning(f"close_position: no open position for {key} — skipping")
            return

        try:
            if price is None:
                order = MarketOrderRequest(
                    symbol=symbol,
                    qty=CONTRACTS,
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY
                )
                log.info(f"[ALPACA PAPER] MARKET close {CONTRACTS}x {ticker} {strike} {direction}")
            else:
                order = LimitOrderRequest(
                    symbol=symbol,
                    qty=CONTRACTS,
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY,
                    limit_price=round(price, 2)
                )
                log.info(f"[ALPACA PAPER] LIMIT close {CONTRACTS}x {ticker} {strike} {direction} @ ${price}")

            response = self.client.submit_order(order)
            log.info(f"Order ID: {response.id}")
            del self.open_positions[key]
        except Exception as e:
            log.error(f"close_position failed: {e}")
