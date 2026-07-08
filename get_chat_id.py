import os
import time
import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

if not TOKEN:
    print("Inserisci TELEGRAM_BOT_TOKEN nel file .env oppure come variabile d'ambiente.")
    raise SystemExit(1)

print("Apri Telegram, cerca il tuo bot e scrivigli /start")
print("Aspetto un messaggio... Premi CTRL+C per uscire.\n")

offset = None
while True:
    params = {"timeout": 30}
    if offset is not None:
        params["offset"] = offset

    response = requests.get(
        f"https://api.telegram.org/bot{TOKEN}/getUpdates",
        params=params,
        timeout=35,
    )
    response.raise_for_status()
    data = response.json()

    for update in data.get("result", []):
        offset = update["update_id"] + 1
        message = update.get("message") or update.get("edited_message")
        if not message:
            continue
        chat = message.get("chat", {})
        chat_id = chat.get("id")
        first_name = chat.get("first_name", "")
        username = chat.get("username", "")
        print("Trovato!")
        print(f"TELEGRAM_CHAT_ID={chat_id}")
        if first_name or username:
            print(f"Utente: {first_name} @{username}".strip())
        raise SystemExit(0)

    time.sleep(2)
