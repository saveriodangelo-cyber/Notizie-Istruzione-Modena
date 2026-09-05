import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

CIRCOLARI_URL = "https://www.convittocorreggio.edu.it/circolare/"
SITE_NAME = "Convitto Nazionale Rinaldo Corso - Correggio"
STATE_FILE = Path("seen_circolari.json")
USER_AGENT = (
    "Mozilla/5.0 (compatible; CircolariConvittoBot/1.0; "
    "+https://github.com/saveriodangelo-cyber/Notizie-Istruzione-Modena)"
)
TIMEOUT_SECONDS = 60
RETRY_ATTEMPTS = 3


def clean_text(value: str) -> str:
    return " ".join((value or "").split())


def canonical_url(base_url: str, href: str) -> str:
    absolute = urljoin(base_url, href)
    parts = urlsplit(absolute)
    # Rimuove query/fragment (per esempio ?pdf=true) per evitare duplicati.
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def item_id(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def request_page(url: str) -> requests.Response:
    last_error = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            response = requests.get(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_error = exc
            if attempt < RETRY_ATTEMPTS:
                time.sleep(5 * attempt)
    raise last_error


def extract_date(text: str) -> str:
    text = clean_text(text)
    patterns = [
        r"(?:Pubblicato il:?\s*)?(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"(?:Pubblicato il:?\s*)?(\d{1,2}\s+(?:gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)\s+\d{4})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def extract_number(text: str) -> str:
    match = re.search(r"circolare\s+(?:n(?:\.|°)?|numero)?\s*(\d+)", text, flags=re.IGNORECASE)
    return match.group(1) if match else ""


def parse_circolari(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    found = []
    seen_urls = set()

    # Primo tentativo: blocchi/article della pagina elenco.
    containers = soup.find_all(["article", "li", "div"])
    for container in containers:
        links = container.find_all("a", href=True)
        for link in links:
            url = canonical_url(CIRCOLARI_URL, link.get("href", ""))
            parts = urlsplit(url)
            if parts.netloc.lower() != "www.convittocorreggio.edu.it":
                continue
            if not parts.path.startswith("/circolare/") or parts.path.rstrip("/") == "/circolare":
                continue
            if url in seen_urls:
                continue

            title = clean_text(link.get_text(" ", strip=True))
            if not title or title.lower() in {"leggi tutto", "continua a leggere", "read more", "download"}:
                heading = container.find(["h1", "h2", "h3", "h4"])
                if heading:
                    title = clean_text(heading.get_text(" ", strip=True))
            if not title:
                continue

            context = clean_text(container.get_text(" ", strip=True))
            found.append(
                {
                    "id": item_id(url),
                    "title": title,
                    "url": url,
                    "date": extract_date(context),
                    "number": extract_number(context + " " + title),
                }
            )
            seen_urls.add(url)

            # La pagina elenco normalmente mostra poche decine di elementi: bastano i più recenti.
            if len(found) >= 40:
                return found

    # Fallback: qualsiasi link che punti a /circolare/<slug>/.
    if not found:
        for link in soup.find_all("a", href=True):
            url = canonical_url(CIRCOLARI_URL, link.get("href", ""))
            parts = urlsplit(url)
            if parts.netloc.lower() != "www.convittocorreggio.edu.it":
                continue
            if not parts.path.startswith("/circolare/") or parts.path.rstrip("/") == "/circolare":
                continue
            if url in seen_urls:
                continue
            title = clean_text(link.get_text(" ", strip=True))
            if not title:
                continue
            found.append(
                {
                    "id": item_id(url),
                    "title": title,
                    "url": url,
                    "date": "",
                    "number": extract_number(title),
                }
            )
            seen_urls.add(url)
            if len(found) >= 40:
                break

    return found


def telegram_send(token: str, chat_id: str, text: str) -> None:
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": False,
        },
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()


def build_message(item: dict) -> str:
    number = f" n. {item['number']}" if item.get("number") else ""
    date = f"\nData: {item['date']}" if item.get("date") else ""
    return (
        f"🏫 Nuova circolare{number} — Rinaldo Corso\n\n"
        f"{item['title']}"
        f"{date}\n\n"
        f"{item['url']}"
    )


def main() -> int:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    send_on_first_run = os.getenv("SEND_ON_FIRST_RUN", "false").strip().lower() in {
        "1", "true", "yes", "on"
    }

    if not token or not chat_id:
        print("ERRORE: mancano TELEGRAM_BOT_TOKEN e/o TELEGRAM_CHAT_ID nei Secrets GitHub.")
        return 2

    state = load_state()
    initialized = bool(state.get("initialized"))
    seen_ids = set(state.get("seen_ids", []))

    response = request_page(CIRCOLARI_URL)
    items = parse_circolari(response.text)
    if not items:
        raise RuntimeError("Nessuna circolare trovata nella pagina: struttura del sito forse cambiata.")

    current_ids = [item["id"] for item in items]
    new_items = [item for item in items if item["id"] not in seen_ids]

    notifications_sent = 0
    if initialized or send_on_first_run:
        # Dal più vecchio al più nuovo, nel caso siano state pubblicate più circolari tra due controlli.
        for item in reversed(new_items):
            telegram_send(token, chat_id, build_message(item))
            notifications_sent += 1
            print(f"Notifica inviata: {item['title']}")
    else:
        print(f"Prima esecuzione: memorizzo {len(items)} circolari correnti senza notificare lo storico.")

    merged_ids = list(dict.fromkeys(current_ids + state.get("seen_ids", [])))[:500]
    state.update(
        {
            "initialized": True,
            "source": CIRCOLARI_URL,
            "last_checked_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "seen_ids": merged_ids,
            "latest_items": items[:40],
        }
    )
    save_state(state)

    print(f"Controllo completato. Notifiche inviate: {notifications_sent}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
