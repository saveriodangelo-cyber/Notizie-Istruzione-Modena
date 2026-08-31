import hashlib
import json
import os
import re
import smtplib
import sys
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Dict, List, Any

import requests
from bs4 import BeautifulSoup, Tag

SITES = [
    {
        "name": "Ufficio scolastico territoriale di Modena",
        "url": "https://mo.istruzioneer.gov.it/",
        "category_url": "https://mo.istruzioneer.gov.it/category/notizie-in-evidenza/",
        "emoji": "📍",
    },
    {
        "name": "Ufficio scolastico territoriale di Reggio Emilia",
        "url": "https://re.istruzioneer.gov.it/",
        "category_url": "https://re.istruzioneer.gov.it/category/notizie-in-evidenza/",
        "emoji": "📌",
    },
    {
        "name": "USR Emilia-Romagna",
        "url": "https://www.istruzioneer.gov.it/",
        "category_url": "https://www.istruzioneer.gov.it/category/notizie-in-evidenza/",
        "emoji": "🏛️",
    },
]

STATE_FILE = Path("seen_news.json")
USER_AGENT = (
    "Mozilla/5.0 (compatible; TelegramNewsBot/1.1; "
    "+https://github.com/saveriodangelo-cyber/Notizie-Istruzione-Modena)"
)
TIMEOUT_SECONDS = 60
RETRY_ATTEMPTS = 3


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


def request_page(url: str) -> requests.Response:
    last_error: Exception | None = None

    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            response = requests.get(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as exc:
            last_error = exc
            if attempt < RETRY_ATTEMPTS:
                time.sleep(5 * attempt)

    assert last_error is not None
    raise last_error


def short_request_error(url: str, exc: Exception) -> str:
    if isinstance(exc, (requests.exceptions.ConnectTimeout, requests.exceptions.ReadTimeout, requests.exceptions.Timeout)):
        return f"{url}: timeout"
    if isinstance(exc, requests.exceptions.HTTPError):
        status = exc.response.status_code if exc.response is not None else "HTTP"
        return f"{url}: errore HTTP {status}"

    message = re.sub(r" at 0x[0-9a-fA-F]+", "", str(exc))
    message = clean_text(message)
    if len(message) > 180:
        message = message[:177] + "..."
    return f"{url}: {exc.__class__.__name__}: {message}"


def make_item(site: Dict[str, str], base_url: str, title: str, url: str, date_text: str = "") -> Dict[str, str]:
    return {
        "id": item_id(url, title),
        "site_name": site["name"],
        "site_url": site["url"],
        "emoji": site.get("emoji", "📰"),
        "title": title,
        "url": url,
        "date": date_text,
    }


def extract_date_after_heading(node: Tag) -> str:
    cursor = node.find_next_sibling()
    checked = 0

    while cursor and checked < 6:
        checked += 1
        if isinstance(cursor, Tag) and cursor.name in {"h1", "h2", "h3", "article"}:
            break

        if isinstance(cursor, Tag):
            text = clean_text(cursor.get_text(" ", strip=True))
            lower = text.lower()
            if text and "continua a leggere" not in lower and "leggi tutto" not in lower:
                return text[:160]

        cursor = cursor.find_next_sibling()

    return ""


def parse_homepage_news(soup: BeautifulSoup, site: Dict[str, str], source_url: str) -> List[Dict[str, str]]:
    heading = None
    for candidate in soup.find_all(["h1", "h2", "h3"]):
        if clean_text(candidate.get_text(" ", strip=True)).lower() == "notizie in evidenza":
            heading = candidate
            break

    if heading is None:
        return []

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
        url = absolute_url(source_url, link["href"])
        if not title or not url:
            continue

        items.append(make_item(site, source_url, title, url, extract_date_after_heading(node)))

    return items


def parse_archive_news(soup: BeautifulSoup, site: Dict[str, str], source_url: str) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    seen_urls = set()

    for node in soup.find_all(["h2", "h3"]):
        link = node.find("a", href=True)
        if not link:
            continue

        title = clean_text(link.get_text(" ", strip=True))
        url = absolute_url(source_url, link["href"])
        lower_title = title.lower()

        if not title or not url:
            continue
        if "articoli meno recenti" in lower_title:
            continue
        if url in seen_urls:
            continue

        seen_urls.add(url)
        items.append(make_item(site, source_url, title, url, extract_date_after_heading(node)))

        if len(items) >= 20:
            break

    return items


def fetch_highlighted_news(site: Dict[str, str]) -> List[Dict[str, str]]:
    urls_to_try = [
        site.get("category_url", "").strip(),
        site["url"],
    ]
    urls_to_try = [url for url in urls_to_try if url]

    errors: List[str] = []

    for url in urls_to_try:
        try:
            response = request_page(url)
            soup = BeautifulSoup(response.text, "html.parser")

            if "/category/notizie-in-evidenza" in url:
                items = parse_archive_news(soup, site, url)
            else:
                items = parse_homepage_news(soup, site, url)

            if items:
                return items

            errors.append(f"{url}: nessuna notizia trovata nella pagina")
        except Exception as exc:
            errors.append(short_request_error(url, exc))

    raise RuntimeError(" | ".join(errors))


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


def email_configured() -> bool:
    required = ["SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "EMAIL_TO"]
    return all(os.getenv(name, "").strip() for name in required)


def email_send(subject: str, body: str) -> None:
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587").strip() or "587")
    smtp_username = os.getenv("SMTP_USERNAME", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip()
    email_from = os.getenv("EMAIL_FROM", smtp_username).strip() or smtp_username
    email_to = os.getenv("EMAIL_TO", "").strip()

    if not email_configured():
        raise RuntimeError(
            "Configurazione email incompleta. Servono SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD e EMAIL_TO."
        )

    message = EmailMessage()
    message["From"] = email_from
    message["To"] = email_to
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP(smtp_host, smtp_port, timeout=TIMEOUT_SECONDS) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(smtp_username, smtp_password)
        server.send_message(message)


def notify(token: str, chat_id: str, item: Dict[str, str]) -> None:
    message = build_message(item)

    if token and chat_id:
        telegram_send(token, chat_id, message)

    if email_configured():
        subject = f"Nuova notizia in evidenza - {item['site_name']}"
        email_send(subject, message)


def build_message(item: Dict[str, str]) -> str:
    date_line = f"\nData: {item['date']}" if item.get("date") else ""
    return (
        f"{item.get('emoji', '📰')} Nuova notizia in evidenza\n\n"
        f"Sito: {item['site_name']}\n"
        f"Titolo: {item['title']}"
        f"{date_line}\n\n"
        f"{item['url']}"
    )


def build_error_message(errors: List[str]) -> str:
    details = "\n".join(f"- {error}" for error in errors)
    return (
        "⚠️ Bot notizie istruzione: controllo non riuscito\n\n"
        "Non sono riuscito a controllare uno o più siti. "
        "Se l'errore resta uguale, non ti mando questo avviso ogni volta.\n\n"
        f"{details}"
    )


def main() -> int:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    send_on_first_run = env_bool("SEND_ON_FIRST_RUN", False)

    telegram_configured = bool(token and chat_id)
    mail_configured = email_configured()

    if not telegram_configured and not mail_configured:
        print(
            "ERRORE: configura Telegram oppure l'email nei Secrets di GitHub. "
            "Per Telegram servono TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID. "
            "Per email servono SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD e EMAIL_TO."
        )
        return 2

    state = load_state()
    already_initialized = bool(state)
    previous_errors = state.get("_meta", {}).get("last_errors", [])

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
            error = f"{site['name']}: {clean_text(str(exc))}"
            print(f"ERRORE: {error}")
            errors.append(error)
            continue

        current_ids = [item["id"] for item in items]
        new_items = [item for item in items if item["id"] not in seen_ids]

        should_notify = already_initialized or send_on_first_run
        if should_notify:
            # Invio dal più vecchio al più nuovo per leggere le notifiche in ordine sensato.
            for item in reversed(new_items):
                notify(token, chat_id, item)
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

        # Avvisa solo quando il tipo di errore cambia, così non spammiamo Telegram.
        if telegram_configured and errors[-10:] != previous_errors:
            try:
                telegram_send(token, chat_id, build_error_message(errors[-10:]))
                print("Avviso errore inviato su Telegram.")
            except Exception as exc:
                print(f"ERRORE: impossibile inviare avviso errore Telegram: {exc}")
    else:
        if state.setdefault("_meta", {}).pop("last_errors", None) is not None:
            changed = True

    if changed or state.get("_meta", {}).get("last_checked_at_utc") == checked_at:
        save_state(state)

    print(f"Controllo completato. Notifiche inviate: {notifications_sent}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
