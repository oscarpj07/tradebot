import asyncio
import logging
import os
import sys
from alpaca_executor import AlpacaExecutor
from discord_watcher import TradeBot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

LOCK_FILE = "/tmp/tradebot.lock"

def acquire_lock():
    if os.path.exists(LOCK_FILE):
        with open(LOCK_FILE) as f:
            pid = f.read().strip()
        if pid and os.path.exists(f"/proc/{pid}"):
            print(f"ERROR: Bot is already running (PID {pid}). Exiting.")
            sys.exit(1)
    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))

def release_lock():
    if os.path.exists(LOCK_FILE):
        os.remove(LOCK_FILE)

async def main():
    acquire_lock()
    try:
        executor = AlpacaExecutor()
        executor.connect()
        bot = TradeBot(executor)
        await bot.start_bot()
    finally:
        release_lock()

if __name__ == "__main__":
    asyncio.run(main())
