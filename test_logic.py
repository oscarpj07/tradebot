"""
Offline test for discord_watcher signal handling logic.
No Discord or Tastytrade connection needed — mocks the executor.
"""
import asyncio
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

from discord_watcher import parse_signal

# ── Mock executor ─────────────────────────────────────────────────────────────

class MockExecutor:
    def __init__(self):
        self.calls = []

    async def handle_signal(self, signal):
        self.calls.append(('handle_signal', signal.copy()))
        log.info(f"  [MOCK] handle_signal: {signal['action']} {signal['ticker']} {signal['strike']} {signal['direction']} @ {signal['price']}")

    async def close_position(self, ticker, strike, direction, price=None):
        self.calls.append(('close_position', {'ticker': ticker, 'strike': strike, 'direction': direction, 'price': price}))
        order_type = f"LIMIT @ {price}" if price else "MARKET"
        log.info(f"  [MOCK] close_position: {ticker} {strike} {direction} {order_type}")


# ── Signal parser tests ────────────────────────────────────────────────────────

def test_parse_signal():
    print("\n" + "="*60)
    print("TEST 1: parse_signal()")
    print("="*60)

    tests = [
        ("🟡 ENTRY QQQ 480 PUTS @ 1.25", {'type': 'ENTRY', 'ticker': 'QQQ', 'strike': 480.0, 'direction': 'PUTS', 'price': 1.25}),
        ("🟢 TAKE PROFIT QQQ 480 PUTS @ 1.85", {'type': 'TP', 'ticker': 'QQQ', 'strike': 480.0, 'direction': 'PUTS', 'price': 1.85}),
        ("🔴 EXIT QQQ 480 PUTS", {'type': 'EXIT', 'ticker': 'QQQ', 'strike': 480.0, 'direction': 'PUTS', 'price': None}),
        ("random message", None),
        ("🟢 TAKE PROFIT QQQ 490 CALLS @ 2.10", {'type': 'TP', 'ticker': 'QQQ', 'strike': 490.0, 'direction': 'CALLS', 'price': 2.10}),
    ]

    all_pass = True
    for msg, expected in tests:
        result = parse_signal(msg)
        ok = result == expected
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] '{msg[:50]}' => {result}")
        if not ok:
            print(f"         expected: {expected}")
            all_pass = False

    return all_pass


# ── Bot logic tests ────────────────────────────────────────────────────────────

async def test_scenario(name, messages, expected_calls):
    print(f"\n{'='*60}")
    print(f"SCENARIO: {name}")
    print(f"{'='*60}")

    from discord_watcher import TradeBot
    executor = MockExecutor()

    # Manually create bot without Discord connection
    bot = TradeBot.__new__(TradeBot)
    bot.executor = executor
    bot.current_trade = None
    bot.tp_count = 0

    for msg in messages:
        signal = parse_signal(msg)
        print(f"\n  MSG: {msg}")
        if signal:
            print(f"  SIGNAL: {signal}")
            await bot.handle_signal(signal)
        else:
            print(f"  (no signal)")

    print(f"\n  Executor calls made: {len(executor.calls)}")
    for c in executor.calls:
        print(f"    {c}")

    # Check expected
    ok = True
    if len(executor.calls) != len(expected_calls):
        print(f"\n  FAIL: expected {len(expected_calls)} calls, got {len(executor.calls)}")
        ok = False
    else:
        for i, (actual, exp) in enumerate(zip(executor.calls, expected_calls)):
            if actual[0] != exp[0]:
                print(f"\n  FAIL call {i}: expected method {exp[0]}, got {actual[0]}")
                ok = False
            for k, v in exp[1].items():
                if actual[1].get(k) != v:
                    print(f"\n  FAIL call {i} key '{k}': expected {v}, got {actual[1].get(k)}")
                    ok = False

    print(f"\n  Result: {'PASS' if ok else 'FAIL'}")
    return ok


async def run_scenarios():
    results = []

    # Scenario 1: Entry -> TP1 -> TP2 (normal win, exit at TP2)
    results.append(await test_scenario(
        "Normal win: Entry -> TP1 -> TP2",
        [
            "🟡 ENTRY QQQ 480 PUTS @ 1.25",
            "🟢 TAKE PROFIT QQQ 480 PUTS @ 1.85",
            "🟢 TAKE PROFIT QQQ 480 PUTS @ 2.20",
        ],
        [
            ('handle_signal', {'action': 'BUY', 'ticker': 'QQQ', 'strike': 480.0, 'direction': 'PUTS', 'price': 1.25}),
            ('handle_signal', {'action': 'SELL', 'ticker': 'QQQ', 'strike': 480.0, 'direction': 'PUTS', 'price': 2.20}),
        ]
    ))

    # Scenario 2: Entry -> EXIT (full loss, no TPs)
    results.append(await test_scenario(
        "Full loss: Entry -> EXIT (no TP)",
        [
            "🟡 ENTRY QQQ 490 CALLS @ 0.95",
            "🔴 EXIT QQQ 490 CALLS",
        ],
        [
            ('handle_signal', {'action': 'BUY', 'ticker': 'QQQ', 'strike': 490.0, 'direction': 'CALLS', 'price': 0.95}),
            ('close_position', {'ticker': 'QQQ', 'strike': 490.0, 'direction': 'CALLS', 'price': None}),  # market order
        ]
    ))

    # Scenario 3: Entry -> TP1 -> EXIT (breakeven stop)
    results.append(await test_scenario(
        "Breakeven: Entry -> TP1 -> EXIT",
        [
            "🟡 ENTRY QQQ 485 PUTS @ 1.50",
            "🟢 TAKE PROFIT QQQ 485 PUTS @ 2.10",
            "🔴 EXIT QQQ 485 PUTS",
        ],
        [
            ('handle_signal', {'action': 'BUY', 'ticker': 'QQQ', 'strike': 485.0, 'direction': 'PUTS', 'price': 1.50}),
            ('close_position', {'ticker': 'QQQ', 'strike': 485.0, 'direction': 'PUTS', 'price': 1.50}),  # limit at entry
        ]
    ))

    # Scenario 4: New entry while trade open (should close previous first)
    results.append(await test_scenario(
        "New entry while trade open: closes previous first",
        [
            "🟡 ENTRY QQQ 480 PUTS @ 1.20",
            "🟡 ENTRY QQQ 490 CALLS @ 0.80",  # new entry mid-trade
        ],
        [
            ('handle_signal', {'action': 'BUY', 'ticker': 'QQQ', 'strike': 480.0, 'direction': 'PUTS', 'price': 1.20}),
            ('close_position', {'ticker': 'QQQ', 'strike': 480.0, 'direction': 'PUTS', 'price': None}),  # close old
            ('handle_signal', {'action': 'BUY', 'ticker': 'QQQ', 'strike': 490.0, 'direction': 'CALLS', 'price': 0.80}),  # open new
        ]
    ))

    # Scenario 5: TP received with no open trade (should be ignored)
    results.append(await test_scenario(
        "TP with no open trade (ignored)",
        [
            "🟢 TAKE PROFIT QQQ 480 PUTS @ 1.85",
        ],
        []
    ))

    return results


async def main():
    print("\n" + "="*60)
    print("TRADEBOT LOGIC TEST SUITE")
    print("="*60)

    parse_ok = test_parse_signal()

    scenario_results = await run_scenarios()

    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"  parse_signal: {'PASS' if parse_ok else 'FAIL'}")
    for i, r in enumerate(scenario_results):
        print(f"  Scenario {i+1}:   {'PASS' if r else 'FAIL'}")

    all_ok = parse_ok and all(scenario_results)
    print(f"\n  Overall: {'ALL PASS' if all_ok else 'SOME FAILURES'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
