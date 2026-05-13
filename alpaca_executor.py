import logging
from datetime import date, timedelta
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    GetOptionContractsRequest,
    LimitOrderRequest,
    MarketOrderRequest,
    StopOrderRequest,
    StopLossRequest,
    TakeProfitRequest,
)
from alpaca.trading.enums import OrderSide, TimeInForce, AssetStatus, ContractType, OrderClass
from config import ALPACA_API_KEY, ALPACA_SECRET_KEY, CONTRACTS
from state_store import load_state, save_state_section

log = logging.getLogger(__name__)


class AlpacaExecutor:
    def __init__(self):
        self.client = None
        self.open_positions = self._load_open_positions()

    def _load_open_positions(self):
        positions = {}
        for item in load_state().get("open_positions", []):
            key = tuple(item["key"]) if isinstance(item.get("key"), list) else item.get("key")
            positions[key] = item["position"]
        return positions

    def _save_open_positions(self):
        items = []
        for key, position in self.open_positions.items():
            items.append({
                "key": list(key) if isinstance(key, tuple) else key,
                "position": position,
            })
        save_state_section("open_positions", items)

    def _position_key(self, ticker, strike, direction, trade_id=None):
        return trade_id or (ticker, strike, direction)

    def connect(self):
        self.client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)
        account = self.client.get_account()
        log.info(f"Connected to Alpaca paper account: {account.account_number}")
        log.info(f"Buying power: ${float(account.buying_power):,.2f}")
        self._refresh_all_exit_orders()

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

    def _stop_group(self, position):
        if not isinstance(position, dict) or not position.get("stop_loss_price"):
            return None
        return (position["symbol"], round(float(position["stop_loss_price"]), 2))

    def _exit_group(self, position):
        if not isinstance(position, dict):
            return None
        symbol = position.get("symbol")
        stop_loss_price = position.get("stop_loss_price")
        take_profit_price = position.get("take_profit_price")
        if not symbol or not stop_loss_price:
            return None
        return (
            symbol,
            round(float(stop_loss_price), 2),
            round(float(take_profit_price), 2) if take_profit_price else None,
        )

    def _matching_exit_keys(self, symbol, stop_loss_price, take_profit_price=None):
        group = (
            symbol,
            round(float(stop_loss_price), 2),
            round(float(take_profit_price), 2) if take_profit_price else None,
        )
        return [
            key for key, position in self.open_positions.items()
            if (
                self._exit_group(position) == group or
                (
                    take_profit_price is None and
                    isinstance(position, dict) and
                    position.get("symbol") == symbol and
                    position.get("stop_loss_price") and
                    round(float(position["stop_loss_price"]), 2) == group[1]
                )
            )
        ]

    def _held_qty(self, symbol):
        try:
            position = self.client.get_open_position(symbol)
            return int(float(position.qty))
        except Exception:
            return 0

    def _cancel_exit_order_group(self, symbol, stop_loss_price, take_profit_price=None):
        keys = self._matching_exit_keys(symbol, stop_loss_price, take_profit_price)
        order_ids = {
            self.open_positions[key].get(order_id_field)
            for key in keys
            for order_id_field in ("exit_order_id", "stop_order_id", "take_profit_order_id")
            if isinstance(self.open_positions.get(key), dict) and self.open_positions[key].get(order_id_field)
        }

        for order_id in order_ids:
            try:
                self.client.cancel_order_by_id(order_id)
                log.info(f"Cancelled exit order {order_id} for {symbol}")
            except Exception as e:
                log.warning(f"Could not cancel exit order {order_id} for {symbol}: {e}")

        for key in keys:
            self.open_positions[key]["exit_order_id"] = None
            self.open_positions[key]["stop_order_id"] = None
            self.open_positions[key]["take_profit_order_id"] = None
        if keys:
            self._save_open_positions()

    def _submit_exit_order_group(self, symbol, stop_loss_price, take_profit_price=None):
        keys = self._matching_exit_keys(symbol, stop_loss_price, take_profit_price)
        state_qty = sum(int(self.open_positions[key]["qty"]) for key in keys)
        held_qty = self._held_qty(symbol)
        qty = min(state_qty, held_qty)
        if qty <= 0:
            for key in keys:
                del self.open_positions[key]
            if keys:
                self._save_open_positions()
            log.warning(f"No Alpaca position found for {symbol}; removed stale stop-loss state")
            return
        if state_qty > held_qty:
            log.warning(f"State qty {state_qty} for {symbol} exceeds Alpaca held qty {held_qty}; capping exit orders to {qty}")

        try:
            if take_profit_price:
                order = LimitOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY,
                    limit_price=round(take_profit_price, 2),
                    order_class=OrderClass.OCO,
                    take_profit=TakeProfitRequest(limit_price=round(take_profit_price, 2)),
                    stop_loss=StopLossRequest(stop_price=round(stop_loss_price, 2)),
                )
                response = self.client.submit_order(order)
                for key in keys:
                    self.open_positions[key]["exit_order_id"] = str(response.id)
                    self.open_positions[key]["take_profit_order_id"] = str(response.id)
                    self.open_positions[key]["stop_order_id"] = None
                self._save_open_positions()
                log.info(
                    f"[ALPACA PAPER] TAKE PROFIT / STOP LOSS placed {qty}x {symbol} "
                    f"TP ${take_profit_price} / SL ${stop_loss_price} — Order ID: {response.id}"
                )
                return

            order = StopOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
                stop_price=round(stop_loss_price, 2),
            )
            response = self.client.submit_order(order)
            for key in keys:
                self.open_positions[key]["exit_order_id"] = str(response.id)
                self.open_positions[key]["stop_order_id"] = str(response.id)
            self._save_open_positions()
            log.info(
                f"[ALPACA PAPER] STOP LOSS placed {qty}x {symbol} "
                f"@ ${stop_loss_price} — Order ID: {response.id}"
            )
        except Exception as e:
            log.error(f"Exit order failed for {symbol} TP ${take_profit_price} / SL ${stop_loss_price}: {e}")
            if take_profit_price:
                log.warning(f"Falling back to stop-loss only for {symbol} @ ${stop_loss_price}")
                self._submit_exit_order_group(symbol, stop_loss_price, None)

    def _refresh_exit_order_group(self, symbol, stop_loss_price, take_profit_price=None):
        self._cancel_exit_order_group(symbol, stop_loss_price, take_profit_price)
        self._submit_exit_order_group(symbol, stop_loss_price, take_profit_price)

    def _refresh_all_exit_orders(self):
        groups = {
            self._exit_group(position)
            for position in self.open_positions.values()
            if self._exit_group(position)
        }
        for symbol, stop_loss_price, take_profit_price in groups:
            self._refresh_exit_order_group(symbol, stop_loss_price, take_profit_price)

    def _cancel_exit_orders_for_position(self, key):
        position = self.open_positions.get(key)
        group = self._exit_group(position)
        if not group:
            return
        self._cancel_exit_order_group(*group)

    async def handle_signal(self, signal):
        ticker = signal["ticker"]
        strike = signal["strike"]
        direction = signal["direction"]
        price = signal["price"]
        action = signal["action"]
        qty = int(signal.get("qty") or CONTRACTS)
        stop_loss_price = signal.get("stop_loss_price")
        take_profit_price = signal.get("take_profit_price")
        key = self._position_key(ticker, strike, direction, signal.get("trade_id"))

        if action == "BUY":
            symbol = self.find_option_symbol(ticker, strike, direction)
            if not symbol:
                return
            self.open_positions[key] = {
                "symbol": symbol,
                "qty": qty,
                "take_profit_price": take_profit_price,
                "stop_loss_price": stop_loss_price,
                "exit_order_id": None,
                "take_profit_order_id": None,
                "stop_order_id": None,
            }
            self._save_open_positions()

            order = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY,
            )

        elif action == "SELL":
            position = self.open_positions.get(key)
            if not position:
                log.warning(f"No open position for {key} — skipping sell")
                return
            symbol = position["symbol"] if isinstance(position, dict) else position
            open_qty = int(position.get("qty", qty)) if isinstance(position, dict) else qty
            held_qty = self._held_qty(symbol)
            qty = min(qty, open_qty, held_qty)
            if qty <= 0:
                log.warning(f"No Alpaca position left for {symbol}; clearing local state for {key}")
                del self.open_positions[key]
                self._save_open_positions()
                return
            exit_group = self._exit_group(position)
            self._cancel_exit_orders_for_position(key)

            # Use market order to guarantee fill — limit orders can miss if bid is below target
            order = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
            )

        try:
            response = self.client.submit_order(order)
            log.info(f"[ALPACA PAPER] {action} {qty}x {ticker} {strike} {direction} @ ${price} — Order ID: {response.id}")
            if action == "BUY":
                position = self.open_positions.get(key)
                group = self._exit_group(position)
                if group:
                    self._refresh_exit_order_group(*group)
            elif action == "SELL":
                if isinstance(self.open_positions.get(key), dict):
                    remaining = self.open_positions[key]["qty"] - qty
                    if remaining > 0:
                        self.open_positions[key]["qty"] = remaining
                        self._save_open_positions()
                    else:
                        del self.open_positions[key]
                        self._save_open_positions()
                    if exit_group:
                        self._submit_exit_order_group(*exit_group)
                else:
                    del self.open_positions[key]
                    self._save_open_positions()
        except Exception as e:
            log.error(f"Order failed: {e}")

    async def close_position(self, ticker, strike, direction, price=None):
        key = (ticker, strike, direction)
        position = self.open_positions.get(key)
        if not position:
            log.warning(f"close_position: no open position for {key} — skipping")
            return
        symbol = position["symbol"] if isinstance(position, dict) else position
        qty = int(position.get("qty", CONTRACTS)) if isinstance(position, dict) else CONTRACTS
        held_qty = self._held_qty(symbol)
        qty = min(qty, held_qty)
        if qty <= 0:
            log.warning(f"close_position: no Alpaca position left for {symbol}; clearing local state")
            del self.open_positions[key]
            self._save_open_positions()
            return
        self._cancel_exit_orders_for_position(key)

        try:
            if price is None:
                order = MarketOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY
                )
                log.info(f"[ALPACA PAPER] MARKET close {qty}x {ticker} {strike} {direction}")
            else:
                order = LimitOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY,
                    limit_price=round(price, 2)
                )
                log.info(f"[ALPACA PAPER] LIMIT close {qty}x {ticker} {strike} {direction} @ ${price}")

            response = self.client.submit_order(order)
            log.info(f"Order ID: {response.id}")
            del self.open_positions[key]
            self._save_open_positions()
        except Exception as e:
            log.error(f"close_position failed: {e}")
