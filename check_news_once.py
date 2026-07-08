import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any

import requests
from bs4 import BeautifulSoup, Tag

SITES = [
    {
        "name": "Ufficio scolastico territoriale di Modena",
        "url": "https://mo.istruzioneer.gov.it/",
        "emoji": "📍",
    },
    {
        "name": "USR Emilia-Romagna",
        "url": "https://www.istruzioneer.gov.it/",
        "emoji": "🏛️",
    },
]

STATE_FILE = Path("seen_news.json")
USER_AGENT = (
    "Mozilla/5.0 (compatible; TelegramNewsBot/1.0; "
    "+https://github.com/)"
)
TIMEOUT_SECONDS = 25


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_state() -> Dict[str, Any]:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_state(state: Dict[str, Any]) -> None:
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def clean_text(value: str) -> str:
    return " ".join(value.split())


def absolute_url(base_url: str, href: str) -> str:
    return requests.compat.urljoin(base_url, href)


def item_id(url: str, title: str) -> str:
    raw = f"{url}|{title}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def fetch_highlighted_news(site: Dict[str, str]) -> List[Dict[str, str]]:
    response = requests.get(
        site["url"],
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    heading = None
    for candidate in soup.find_all(["h1", "h2", "h3"]):
        if clean_text(candidate.get_text(" ", strip=True)).lower() == "notizie in evidenza":
            heading = candidate
            break

    if heading is None:
        raise RuntimeError(f"Sezione 'Notizie in evidenza' non trovata su {site['url']}")

    items: List[Dict[str, str]] = []

    for node in heading.find_all_next():
        if isinstance(node, Tag) and node.name == "h2" and node is not heading:
            break

        if not isinstance(node, Tag) or node.name != "h3":
            continue

        link = node.find("a", href=True)
        if not link:
            continue

        title = clean_text(link.get_text(" ", strip=True))
        url = absolute_url(site["url"], link["href"])
        if not title or not url:
            continue

        date_text = ""
        cursor = node.find_next_sibling()
        while cursor and isinstance(cursor, Tag) and cursor.name not in {"h2", "h3"}:
            text = clean_text(cursor.get_text(" ", strip=True))
            if text and "continua a leggere" not in text.lower():
                date_text = text
                break
            cursor = cursor.find_next_sibling()

        items.append(
            {
                "id": item_id(url, title),
                "site_name": site["name"],
                "site_url": site["url"],
                "emoji": site.get("emoji", "📰"),
                "title": title,
                "url": url,
                "date": date_text,
            }
        )

    return items


def telegram_send(token: str, chat_id: str, text: str) -> None:
    api_url = f"https://api.telegram.org/bot{token}/sendMessage"
    response = requests.post(
        api_url,
        json={
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": False,
        },
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()


def build_message(item: Dict[str, str]) -> str:
    date_line = f"\nData: {item['date']}" if item.get("date") else ""
    return (
        f"{item.get('emoji', '📰')} Nuova notizia in evidenza\n\n"
        f"Sito: {item['site_name']}\n"
        f"Titolo: {item['title']}"
        f"{date_line}\n\n"
        f"{item['url']}"
    )


def main() -> int:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    send_on_first_run = env_bool("SEND_ON_FIRST_RUN", False)

    if not token or not chat_id:
        print("ERRORE: imposta TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID nei Secrets di GitHub.")
        return 2

    state = load_state()
    already_initialized = bool(state)
    changed = False
    notifications_sent = 0
    errors: List[str] = []

    checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    state.setdefault("_meta", {})["last_checked_at_utc"] = checked_at

    for site in SITES:
        site_key = site["url"]
        site_state = state.setdefault(site_key, {"seen_ids": [], "latest_items": []})
        seen_ids = set(site_state.get("seen_ids", []))

        try:
            items = fetch_highlighted_news(site)
        except Exception as exc:
            error = f"{site['name']}: {exc}"
            print(f"ERRORE: {error}")
            errors.append(error)
            continue

        current_ids = [item["id"] for item in items]
        new_items = [item for item in items if item["id"] not in seen_ids]

        should_notify = already_initialized or send_on_first_run
        if should_notify:
            # Invio dal più vecchio al più nuovo per leggere le notifiche in ordine sensato.
            for item in reversed(new_items):
                telegram_send(token, chat_id, build_message(item))
                notifications_sent += 1
                print(f"Notifica inviata: {item['title']}")
        elif new_items:
            print(
                f"Prima esecuzione: ho memorizzato {len(new_items)} notizie di {site['name']} senza notificare."
            )

        merged_ids = list(dict.fromkeys(current_ids + site_state.get("seen_ids", [])))[:200]
        latest_items = [
            {
                "id": item["id"],
                "title": item["title"],
                "url": item["url"],
                "date": item.get("date", ""),
            }
            for item in items[:20]
        ]

        if merged_ids != site_state.get("seen_ids") or latest_items != site_state.get("latest_items"):
            site_state["seen_ids"] = merged_ids
            site_state["latest_items"] = latest_items
            changed = True

    if errors:
        state.setdefault("_meta", {})["last_errors"] = errors[-10:]
        changed = True
    else:
        state.setdefault("_meta", {}).pop("last_errors", None)

    if changed or state.get("_meta", {}).get("last_checked_at_utc") == checked_at:
        save_state(state)

    print(f"Controllo completato. Notifiche inviate: {notifications_sent}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
