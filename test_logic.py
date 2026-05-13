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

from discord_watcher import parse_embed_signal, parse_message_signal, parse_signal

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


class FakeField:
    def __init__(self, name, value):
        self.name = name
        self.value = value


class FakeEmbed:
    def __init__(self, title='', description='', fields=None):
        self.title = title
        self.description = description
        self.fields = [FakeField(name, value) for name, value in (fields or [])]


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


def test_parse_embed_signal():
    print("\n" + "="*60)
    print("TEST 2: parse_embed_signal()")
    print("="*60)

    tests = [
        (
            FakeEmbed(
                title="LIVE ENTRY — MegaGrid Low DD Champion",
                description="@admin\n**📉 PUT** position opened on **SPY $373.0** strike",
                fields=[
                    ("Strike", "$373.0"),
                    ("Type", "PUT"),
                    ("Entry Price", "$1.80"),
                    ("Quantity", "1 contract"),
                    ("Take Profit", "+100% ($3.60)"),
                    ("Stop Loss", "-20% ($1.44)"),
                    ("Model ID", "MG_LowDD"),
                    ("Source", "0DTE_V3_MegaGrid"),
                ],
            ),
            {'type': 'ENTRY', 'ticker': 'SPY', 'strike': 373.0, 'direction': 'PUTS', 'price': 1.80, 'qty': 1, 'take_profit_price': 3.60, 'stop_loss_price': 1.44, 'model_id': 'MG_LowDD', 'source_name': '0DTE_V3_MegaGrid', 'source': 'LIVE_ENTRY_EMBED'},
        ),
        (
            FakeEmbed(
                title="LIVE EXIT — MegaGrid Risk-Adjusted",
                description="@admin\nTIMED OUT after 60 min — gained 72.7% ($+133.00)",
                fields=[
                    ("Exit Reason", "Max Hold Time Reached"),
                    ("Strike", "$373.0 PUT"),
                    ("Entry Price", "$1.83"),
                    ("Exit Price", "$3.16"),
                    ("Qty", "1 contract"),
                    ("SPY at Exit", "$734.27"),
                    ("Model ID", "MG_RiskAdj"),
                    ("Source", "0DTE_V3_MegaGrid"),
                ],
            ),
            {'type': 'EXIT', 'ticker': 'SPY', 'strike': 373.0, 'direction': 'PUTS', 'price': 3.16, 'qty': 1, 'model_id': 'MG_RiskAdj', 'source_name': '0DTE_V3_MegaGrid', 'source': 'LIVE_EXIT_EMBED'},
        ),
        (
            FakeEmbed(
                title="LIVE ENTRY — Most Stable MultiConf",
                description="@admin\n**📈 CALL** position opened on **SPY $740.0** strike",
                fields=[
                    ("Strike", "$740.0"),
                    ("Type", "CALL"),
                    ("Entry Price", "$0.78"),
                    ("Quantity", "3 contracts"),
                    ("Take Profit", "+100% ($1.56)"),
                    ("Stop Loss", "-80% ($0.16)"),
                    ("Model ID", "MSP_TripleEMA"),
                    ("Source", "0DTE_Most_Stable_Profitable"),
                ],
            ),
            {'type': 'ENTRY', 'ticker': 'SPY', 'strike': 740.0, 'direction': 'CALLS', 'price': 0.78, 'qty': 3, 'take_profit_price': 1.56, 'stop_loss_price': 0.16, 'model_id': 'MSP_TripleEMA', 'source_name': '0DTE_Most_Stable_Profitable', 'source': 'LIVE_ENTRY_EMBED'},
        ),
    ]

    all_pass = True
    for embed, expected in tests:
        result = parse_embed_signal(embed)
        ok = result == expected
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] '{embed.title}' => {result}")
        if not ok:
            print(f"         expected: {expected}")
            all_pass = False

    return all_pass


async def test_embed_scenario():
    print(f"\n{'='*60}")
    print("SCENARIO: Embed entry -> partial live exit")
    print(f"{'='*60}")

    from discord_watcher import TradeBot
    executor = MockExecutor()

    bot = TradeBot.__new__(TradeBot)
    bot.executor = executor
    bot.current_trade = None
    bot.tp_count = 0
    bot.open_embed_trades = {}
    bot._save_open_embed_trades = lambda: None

    class FakeMessage:
        content = ''

        def __init__(self, embed):
            self.embeds = [embed]

    entry = FakeEmbed(
        title="LIVE ENTRY — Most Stable MultiConf",
        description="@admin\n**📈 CALL** position opened on **SPY $740.0** strike",
        fields=[
            ("Strike", "$740.0"),
            ("Type", "CALL"),
            ("Entry Price", "$0.78"),
            ("Quantity", "3 contracts"),
            ("Take Profit", "+100% ($1.56)"),
            ("Stop Loss", "-80% ($0.16)"),
            ("Model ID", "MSP_TripleEMA"),
            ("Source", "0DTE_Most_Stable_Profitable"),
        ],
    )
    exit_embed = FakeEmbed(
        title="LIVE EXIT — Most Stable MultiConf",
        description="@admin\nTIMED OUT after 60 min — gained 5.2% ($+12.00)",
        fields=[
            ("Exit Reason", "Max Hold Time Reached"),
            ("Strike", "$740.0 CALL"),
            ("Entry Price", "$0.77"),
            ("Exit Price", "$0.81"),
            ("Qty", "2 contracts"),
            ("SPY at Exit", "$740.14"),
            ("Model ID", "MSP_TripleEMA"),
            ("Source", "0DTE_Most_Stable_Profitable"),
        ],
    )

    for embed in (entry, exit_embed):
        signal = parse_message_signal(FakeMessage(embed))
        print(f"  SIGNAL: {signal}")
        await bot.handle_signal(signal)

    trade_id = ('SPY', 740.0, 'CALLS', 'MSP_TripleEMA', '0DTE_Most_Stable_Profitable')
    expected_calls = [
        ('handle_signal', {'action': 'BUY', 'ticker': 'SPY', 'strike': 740.0, 'direction': 'CALLS', 'price': 0.78, 'qty': 3, 'take_profit_price': 1.56, 'stop_loss_price': 0.16, 'trade_id': trade_id}),
        ('handle_signal', {'action': 'SELL', 'ticker': 'SPY', 'strike': 740.0, 'direction': 'CALLS', 'price': 0.81, 'qty': 2, 'trade_id': trade_id}),
    ]

    open_trade = bot.open_embed_trades.get(trade_id)
    ok = executor.calls == expected_calls and open_trade and open_trade.get('qty') == 1
    print(f"\n  Executor calls made: {len(executor.calls)}")
    for c in executor.calls:
        print(f"    {c}")
    print(f"  Remaining bot qty: {open_trade.get('qty') if open_trade else None}")
    print(f"\n  Result: {'PASS' if ok else 'FAIL'}")
    if not ok:
        print(f"  Expected: {expected_calls}, remaining qty 1")
    return ok


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
    embed_parse_ok = test_parse_embed_signal()

    scenario_results = await run_scenarios()
    embed_scenario_ok = await test_embed_scenario()

    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"  parse_signal: {'PASS' if parse_ok else 'FAIL'}")
    print(f"  parse_embed_signal: {'PASS' if embed_parse_ok else 'FAIL'}")
    for i, r in enumerate(scenario_results):
        print(f"  Scenario {i+1}:   {'PASS' if r else 'FAIL'}")
    print(f"  Embed scenario: {'PASS' if embed_scenario_ok else 'FAIL'}")

    all_ok = parse_ok and embed_parse_ok and all(scenario_results) and embed_scenario_ok
    print(f"\n  Overall: {'ALL PASS' if all_ok else 'SOME FAILURES'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
