import os
import sys

from check_news_once import SITES, fetch_highlighted_news, telegram_send, build_message

TARGET_DATE_ISO = "2026/09/04"
TARGET_DATE_TEXT = "4 settembre 2026"


def is_target(item: dict) -> bool:
    url = (item.get("url") or "").lower()
    date = (item.get("date") or "").lower()
    return f"/{TARGET_DATE_ISO}/" in url or TARGET_DATE_TEXT in date


def main() -> int:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("ERRORE: TELEGRAM_BOT_TOKEN e/o TELEGRAM_CHAT_ID mancanti.")
        return 2

    found = []
    errors = []

    for site in SITES:
        try:
            items = fetch_highlighted_news(site)
        except Exception as exc:
            errors.append(f"{site['name']}: {exc}")
            continue
        for item in items:
            if is_target(item):
                found.append(item)

    telegram_send(
        token,
        chat_id,
        "🧪 TEST bot USR/UST — notifiche del 4 settembre 2026\n\n"
        f"Notizie trovate: {len(found)}. Ora te le reinvio come se fossero nuove."
    )

    for item in found:
        telegram_send(token, chat_id, "🧪 TEST\n\n" + build_message(item))

    if errors:
        telegram_send(
            token,
            chat_id,
            "⚠️ Durante il test non sono riuscito a leggere uno o più siti:\n\n" + "\n".join(f"- {e}" for e in errors),
        )

    if not found:
        telegram_send(token, chat_id, "ℹ️ Test completato: nessuna notizia del 4 settembre trovata nelle attuali 'Notizie in evidenza'.")

    print(f"Test completato. Notifiche di ieri inviate: {len(found)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
