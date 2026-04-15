import requests
import json
import time

TOKEN = "YOUR_DISCORD_TOKEN_HERE"
CHANNEL_ID = "1441026525981049018"

headers = {
    "Authorization": TOKEN,
    "Content-Type": "application/json"
}

def fetch_messages():
    messages = []
    last_id = None

    print("Fetching messages...")

    while True:
        url = f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages?limit=100"
        if last_id:
            url += f"&before={last_id}"

        response = requests.get(url, headers=headers)

        if response.status_code != 200:
            print(f"Error: {response.status_code} - {response.text}")
            break

        batch = response.json()

        if not batch:
            break

        messages.extend(batch)
        last_id = batch[-1]["id"]
        print(f"Fetched {len(messages)} messages so far...")

        time.sleep(1)  # avoid rate limiting

    return messages

messages = fetch_messages()

with open("messages4.json", "w") as f:
    json.dump(messages, f, indent=2)

print(f"Done! Saved {len(messages)} messages to messages4.json")
