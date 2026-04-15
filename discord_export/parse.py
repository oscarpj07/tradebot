import json

def get_field(fields, name):
    for f in fields:
        if f['name'] == name:
            return f['value']
    return None

with open('messages.json') as f:
    messages = json.load(f)

signals = []

for msg in messages:
    for embed in msg.get('embeds', []):
        fields = embed.get('fields', [])

        ai_conf_raw = get_field(fields, 'AI Confidence')
        if not ai_conf_raw:
            continue

        # Extract number from "73.41% :rocket:" or "59.11%"
        try:
            confidence = float(ai_conf_raw.split('%')[0].strip())
        except:
            continue

        if confidence < 70:
            continue

        signals.append({
            'timestamp': embed.get('timestamp', ''),
            'symbol': get_field(fields, 'Symbol'),
            'strike': get_field(fields, 'Strike'),
            'expiration': get_field(fields, 'Expiration'),
            'call_put': get_field(fields, 'Call/Put'),
            'buy_sell': get_field(fields, 'Buy/Sell'),
            'ai_confidence': confidence,
            'prems_spent': get_field(fields, 'Prems Spent'),
            'volume': get_field(fields, 'Volume'),
            'oi': get_field(fields, 'OI'),
            'tracking_link': get_field(fields, 'Tracking Link'),
        })

signals.sort(key=lambda x: x['ai_confidence'], reverse=True)

print(f"Total signals: {len(messages)}")
print(f"Signals with 70%+ confidence: {len(signals)}")
print()
print(f"{'Symbol':<8} {'C/P':<6} {'Strike':<8} {'Expiry':<12} {'Confidence':<12} {'Prems':<10} Timestamp")
print("-" * 80)
for s in signals:
    print(f"{s['symbol']:<8} {s['call_put']:<6} {s['strike']:<8} {s['expiration']:<12} {s['ai_confidence']:<12.2f} {s['prems_spent']:<10} {s['timestamp'][:10]}")

with open('signals_75plus.json', 'w') as f:
    json.dump(signals, f, indent=2)

print(f"\nSaved to signals_75plus.json")
