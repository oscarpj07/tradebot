import re
import logging
import discord
from config import DISCORD_TOKEN, DISCORD_CHANNEL_ID
from trade_executor import TradeExecutor

log = logging.getLogger(__name__)


def parse_signal(msg: str):
    """Parse a Discord message and return signal type + details."""
    content = msg.strip()

    # Entry: 🟡
    entry_match = re.search(
        r'🟡.*?(\w{1,5})\s+(\d+(?:\.\d+)?)\s+(PUTS|CALLS)\s+@\s+([\d.]+)',
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

    # Take profit: 🟢
    tp_match = re.search(
        r'🟢.*?(\w{1,5})\s+(\d+(?:\.\d+)?)\s+(PUTS|CALLS)\s+@\s+([\d.]+)',
        content, re.IGNORECASE
    )
    if tp_match and 'TAKE PROFIT' in content.upper():
        return {
            'type': 'TP',
            'ticker': tp_match.group(1).upper(),
            'strike': float(tp_match.group(2)),
            'direction': tp_match.group(3).upper(),
            'price': float(tp_match.group(4)),
        }

    # Exit: 🔴
    exit_match = re.search(
        r'🔴.*?(\w{1,5})\s+(\d+(?:\.\d+)?)\s+(PUTS|CALLS)',
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


class TradeBot(discord.Client):
    def __init__(self, executor: TradeExecutor):
        super().__init__()
        self.executor = executor

        # Track current open trade state
        self.current_trade = None  # dict with trade info
        self.tp_count = 0          # number of TPs received for current trade

    async def on_ready(self):
        log.info(f"Logged in as {self.user}")
        log.info(f"Watching channel ID: {DISCORD_CHANNEL_ID}")

    async def on_message(self, message):
        if message.channel.id != DISCORD_CHANNEL_ID:
            return

        signal = parse_signal(message.content)
        if not signal:
            return

        log.info(f"Signal detected: {signal}")
        await self.handle_signal(signal)

    async def handle_signal(self, signal):
        sig_type = signal['type']

        if sig_type == 'ENTRY':
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
            await self.executor.handle_signal({
                'ticker': signal['ticker'],
                'strike': signal['strike'],
                'direction': signal['direction'],
                'price': signal['price'],
                'action': 'BUY',
            })

        elif sig_type == 'TP':
            if not self.current_trade:
                log.warning("TP received but no open trade — ignoring")
                return

            self.tp_count += 1
            log.info(f"TP #{self.tp_count} received @ ${signal['price']}")

            if self.tp_count >= 2:
                # Exit FULL position on TP2
                log.info(f"TP2 hit — closing full position @ ${signal['price']}")
                await self.executor.handle_signal({
                    'ticker': self.current_trade['ticker'],
                    'strike': self.current_trade['strike'],
                    'direction': self.current_trade['direction'],
                    'price': signal['price'],
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

    async def start_bot(self):
        await self.start(DISCORD_TOKEN)
