import re
import logging
import discord
from config import DISCORD_TOKEN, DISCORD_CHANNEL_ID
from trade_executor import TradeExecutor

log = logging.getLogger(__name__)


def _parse_price(value):
    match = re.search(r'\$?([+-]?\d+(?:\.\d+)?)', value or '')
    return float(match.group(1)) if match else None


def _plural_direction(value):
    direction = (value or '').upper()
    if direction in ('PUT', 'PUTS'):
        return 'PUTS'
    if direction in ('CALL', 'CALLS'):
        return 'CALLS'
    return None


def _parse_qty(value):
    match = re.search(r'(\d+)', value or '')
    return int(match.group(1)) if match else None


def _clean_field_value(value):
    return str(value or '').strip().strip('`').strip()


def _field_map(embed):
    fields = {}
    for field in getattr(embed, 'fields', []):
        name = re.sub(r'[^A-Za-z ]+', '', getattr(field, 'name', '')).strip().upper()
        fields[name] = _clean_field_value(getattr(field, 'value', ''))
    return fields


def _embed_trade_key(signal):
    return (
        signal.get('ticker'),
        signal.get('strike'),
        signal.get('direction'),
        signal.get('model_id'),
        signal.get('source_name'),
    )


def parse_signal(msg: str):
    """Parse a Discord message and return signal type + details."""
    content = msg.strip()

    # Legacy plain-text entry.
    entry_match = re.search(
        r'(\w{1,5})\s+(\d+(?:\.\d+)?)\s+(PUTS|CALLS)\s+@\s+([\d.]+)',
        content, re.IGNORECASE
    )
    if entry_match and 'ENTRY' in content.upper():
        return {
            'type': 'ENTRY',
            'ticker': entry_match.group(1).upper(),
            'strike': float(entry_match.group(2)),
            'direction': entry_match.group(3).upper(),
            'price': float(entry_match.group(4)),
        }

    # Legacy plain-text take profit.
    if 'TAKE PROFIT' in content.upper():
        price_match = re.search(r'@\s+([\d.]+)', content)
        details_match = re.search(
            r'(\w{1,5})\s+(\d+(?:\.\d+)?)\s+(PUTS|CALLS)',
            content, re.IGNORECASE
        )
        price = float(price_match.group(1)) if price_match else None
        signal = {'type': 'TP', 'price': price}
        if details_match:
            signal.update({
                'ticker': details_match.group(1).upper(),
                'strike': float(details_match.group(2)),
                'direction': details_match.group(3).upper(),
            })
        return signal

    # Legacy plain-text exit.
    exit_match = re.search(
        r'(\w{1,5})\s+(\d+(?:\.\d+)?)\s+(PUTS|CALLS)',
        content, re.IGNORECASE
    )
    if exit_match and 'EXIT' in content.upper():
        return {
            'type': 'EXIT',
            'ticker': exit_match.group(1).upper(),
            'strike': float(exit_match.group(2)),
            'direction': exit_match.group(3).upper(),
            'price': None,
        }

    return None


def parse_embed_signal(embed):
    """Parse trade signals from Discord embeds like 0DTE Live Apex posts."""
    title = str(getattr(embed, 'title', '') or '')
    description = str(getattr(embed, 'description', '') or '')
    fields = _field_map(embed)
    haystack = f"{title}\n{description}".upper()

    if 'LIVE ENTRY' in haystack or 'POSITION OPENED' in haystack:
        plain_description = re.sub(r'[*_`]', '', description)
        desc_match = re.search(r'\b(CALL|PUT)\b', plain_description, re.IGNORECASE)
        ticker_match = re.search(
            r'\bon\s+([A-Z]{1,5})\s+\$?(\d+(?:\.\d+)?)\s+strike',
            plain_description,
            re.IGNORECASE,
        )

        ticker = ticker_match.group(1).upper() if ticker_match else None
        strike = _parse_price(fields.get('STRIKE')) or (float(ticker_match.group(2)) if ticker_match else None)
        direction = _plural_direction(fields.get('TYPE')) or (
            _plural_direction(desc_match.group(1)) if desc_match else None
        )
        price = _parse_price(fields.get('ENTRY PRICE'))
        qty = _parse_qty(fields.get('QUANTITY') or fields.get('QTY'))
        model_id = fields.get('MODEL ID')
        source_name = fields.get('SOURCE')

        if ticker and strike and direction and price:
            return {
                'type': 'ENTRY',
                'ticker': ticker,
                'strike': strike,
                'direction': direction,
                'price': price,
                'qty': qty,
                'model_id': model_id,
                'source_name': source_name,
                'source': 'LIVE_ENTRY_EMBED',
            }

    if 'LIVE EXIT' in haystack or 'EXIT REASON' in fields:
        strike_match = re.search(
            r'\$?(\d+(?:\.\d+)?)\s+(PUT|PUTS|CALL|CALLS)',
            fields.get('STRIKE', ''),
            re.IGNORECASE
        )
        ticker = None
        for field_name in fields:
            ticker_match = re.match(r'([A-Z]{1,5}) AT EXIT$', field_name)
            if ticker_match:
                ticker = ticker_match.group(1)
                break
        model_id = fields.get('MODEL ID')
        source_name = fields.get('SOURCE')

        if strike_match:
            return {
                'type': 'EXIT',
                'ticker': ticker,
                'strike': float(strike_match.group(1)),
                'direction': _plural_direction(strike_match.group(2)),
                'price': _parse_price(fields.get('EXIT PRICE')),
                'qty': _parse_qty(fields.get('QTY') or fields.get('QUANTITY')),
                'model_id': model_id,
                'source_name': source_name,
                'source': 'LIVE_EXIT_EMBED',
            }

    return None


def parse_message_signal(message):
    signal = parse_signal(message.content or '')
    if signal:
        return signal

    for embed in getattr(message, 'embeds', []):
        signal = parse_embed_signal(embed)
        if signal:
            return signal

    return None


class TradeBot(discord.Client):
    def __init__(self, executor: TradeExecutor):
        super().__init__()
        self.executor = executor

        # Track current open trade state
        self.current_trade = None  # dict with trade info
        self.tp_count = 0          # number of TPs received for current trade
        self.open_embed_trades = {}

    async def on_ready(self):
        log.info(f"Logged in as {self.user}")
        log.info(f"Watching channel ID: {DISCORD_CHANNEL_ID}")

    async def on_message(self, message):
        if message.channel.id != DISCORD_CHANNEL_ID:
            return

        signal = parse_message_signal(message)
        if not signal:
            if getattr(message, 'embeds', None):
                titles = [getattr(embed, 'title', '') for embed in message.embeds]
                log.info(f"Message had embeds but no parseable trade signal: {titles}")
            return

        log.info(f"Signal detected: {signal}")
        await self.handle_signal(signal)

    async def handle_signal(self, signal):
        sig_type = signal['type']

        if signal.get('source') in ('LIVE_ENTRY_EMBED', 'LIVE_EXIT_EMBED'):
            await self.handle_live_embed_signal(signal)
            return

        if sig_type == 'ENTRY':
            # Skip duplicate entry for the same trade already open
            if self.current_trade and (
                self.current_trade['ticker'] == signal['ticker'] and
                self.current_trade['strike'] == signal['strike'] and
                self.current_trade['direction'] == signal['direction']
            ):
                log.warning(f"Duplicate ENTRY for {signal['ticker']} {signal['strike']} {signal['direction']} — ignoring")
                return

            # If there's an open trade that never hit TP2, close it at market first
            if self.current_trade:
                log.warning(f"New entry while trade open — closing previous position at market")
                await self.executor.close_position(
                    self.current_trade['ticker'],
                    self.current_trade['strike'],
                    self.current_trade['direction'],
                    price=None  # market order
                )

            # Open new trade
            self.current_trade = signal
            self.tp_count = 0
            order_signal = {
                'ticker': signal['ticker'],
                'strike': signal['strike'],
                'direction': signal['direction'],
                'price': signal['price'],
                'action': 'BUY',
            }
            if signal.get('qty'):
                order_signal['qty'] = signal['qty']
            await self.executor.handle_signal(order_signal)

        elif sig_type == 'TP':
            if not self.current_trade:
                log.warning("TP received but no open trade — ignoring")
                return

            self.tp_count += 1
            price = signal.get('price') or self.current_trade['price']
            log.info(f"TP #{self.tp_count} received @ ${price}")

            if self.tp_count >= 2:
                # Exit FULL position on TP2
                log.info(f"TP2 hit — closing full position @ ${price}")
                await self.executor.handle_signal({
                    'ticker': self.current_trade['ticker'],
                    'strike': self.current_trade['strike'],
                    'direction': self.current_trade['direction'],
                    'price': price,
                    'action': 'SELL',
                })
                self.current_trade = None
                self.tp_count = 0
            else:
                log.info(f"TP1 received — holding position, waiting for TP2")

        elif sig_type == 'EXIT':
            if not self.current_trade:
                log.warning("EXIT received but no open trade — ignoring")
                return

            if signal.get('source') == 'LIVE_EXIT_EMBED':
                qty = signal.get('qty')
                price = signal.get('price') or self.current_trade['price']
                log.info(f"LIVE EXIT received — selling {qty or 'remaining'} contract(s) @ ${price}")

                sell_signal = {
                    'ticker': self.current_trade['ticker'],
                    'strike': self.current_trade['strike'],
                    'direction': self.current_trade['direction'],
                    'price': price,
                    'action': 'SELL',
                }
                if qty:
                    sell_signal['qty'] = qty

                await self.executor.handle_signal(sell_signal)

                if qty and self.current_trade.get('qty'):
                    remaining = self.current_trade['qty'] - qty
                    if remaining > 0:
                        self.current_trade['qty'] = remaining
                        return

                self.current_trade = None
                self.tp_count = 0
                return

            if self.tp_count == 0:
                # Full loss — exit at market
                log.info(f"EXIT before any TP — closing at market (full loss)")
            else:
                # Hit breakeven after TP1 — close at entry price
                log.info(f"EXIT after {self.tp_count} TPs — closing at breakeven")

            await self.executor.close_position(
                self.current_trade['ticker'],
                self.current_trade['strike'],
                self.current_trade['direction'],
                price=self.current_trade['price'] if self.tp_count > 0 else None
            )
            self.current_trade = None
            self.tp_count = 0

    async def handle_live_embed_signal(self, signal):
        key = _embed_trade_key(signal)

        if signal['type'] == 'ENTRY':
            if key in self.open_embed_trades:
                log.warning(f"Duplicate LIVE ENTRY for {key} — ignoring")
                return

            self.open_embed_trades[key] = signal.copy()
            order_signal = {
                'ticker': signal['ticker'],
                'strike': signal['strike'],
                'direction': signal['direction'],
                'price': signal['price'],
                'action': 'BUY',
                'trade_id': key,
            }
            if signal.get('qty'):
                order_signal['qty'] = signal['qty']

            log.info(f"LIVE ENTRY — buying {order_signal.get('qty', 'configured')} contract(s) for {key}")
            await self.executor.handle_signal(order_signal)
            return

        if signal['type'] == 'EXIT':
            trade = self.open_embed_trades.get(key)
            if not trade:
                log.warning(f"LIVE EXIT received but no matching open embed trade for {key} — ignoring")
                return

            qty = signal.get('qty') or trade.get('qty')
            price = signal.get('price') or trade['price']
            sell_signal = {
                'ticker': trade['ticker'],
                'strike': trade['strike'],
                'direction': trade['direction'],
                'price': price,
                'action': 'SELL',
                'trade_id': key,
            }
            if qty:
                sell_signal['qty'] = qty

            log.info(f"LIVE EXIT — selling {qty or 'remaining'} contract(s) for {key} @ ${price}")
            await self.executor.handle_signal(sell_signal)

            if qty and trade.get('qty'):
                remaining = trade['qty'] - qty
                if remaining > 0:
                    trade['qty'] = remaining
                    return

            del self.open_embed_trades[key]

    async def start_bot(self):
        await self.start(DISCORD_TOKEN)
