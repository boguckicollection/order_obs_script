
# -*- coding: utf-8 -*-
import imaplib
import email
import os
import time
import json
import re
import requests
from datetime import datetime, timedelta
from email.header import decode_header
from email.utils import parsedate_to_datetime
from bs4 import BeautifulSoup


def load_env_file(path: str = ".env") -> None:
    """Load environment variables from a simple .env file."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key, value)

# === KONFIGURACJA ===
load_env_file()

IMAP_SERVER = os.getenv("IMAP_SERVER", "imap.gmail.com")
EMAIL_ACCOUNT = os.getenv("EMAIL_ACCOUNT", "")
PASSWORD = os.getenv("EMAIL_PASSWORD", "")
SEARCH_PHRASE = os.getenv(
    "SEARCH_PHRASE", "twój przedmiot został sprzedany"
).lower()
FOLDER = os.getenv("FOLDER", "Vinted/Sprzedane")
OUTPUT_PATH = os.getenv("OUTPUT_PATH", "orders.json")
CARDS_OUTPUT_PATH = os.getenv("CARDS_OUTPUT_PATH", "latest_order_cards.json")
CARDS_CACHE_PATH = os.getenv("CARDS_CACHE_PATH", "cards_cache.json")
CARDS_HTML_PATH = os.getenv("CARDS_HTML_PATH", "cards_count.html")
ALL_CARDS_PATH = os.getenv("ALL_CARDS_PATH", "all_order_cards.json")
API_KEY = os.getenv("API_KEY", "")
SEARCH_DAYS = int(os.getenv("SEARCH_DAYS", "2"))

def decode_mime_words(s):
    decoded_fragments = decode_header(s)
    return ''.join(
        fragment.decode(encoding or 'utf-8') if isinstance(fragment, bytes) else fragment
        for fragment, encoding in decoded_fragments
    )

def extract_cards_from_body(body):
    soup = BeautifulSoup(body, "html.parser")
    text = soup.get_text()
    pattern = r"(.+?)\s*\((\w+)\s+(\w+)\)"
    matches = re.findall(pattern, text)
    print(f"🔍 Znaleziono {len(matches)} kart w treści e-maila.")
    results = []

    for name, set_code, number in matches:
        name = name.strip()
        query = f'name:"{name}" set.id:{set_code} number:{number}'
        headers = {"X-Api-Key": API_KEY}

        try:
            r = requests.get(
                "https://api.pokemontcg.io/v2/cards",
                headers=headers,
                params={"q": query},
            )
            if r.status_code == 200:
                data = r.json()
                if data["data"]:
                    card = data["data"][0]
                    results.append({
                        "name": card["name"],
                        "set": card["set"]["id"],
                        "number": card["number"],
                        "image": card["images"]["large"]
                    })
                    print(f"✅ Dodano kartę: {card['name']} ({card['set']['id']} {card['number']})")
        except Exception as e:
            print(f"❌ Błąd pobierania karty '{name}': {e}")
    return results

def load_cache():
    if os.path.exists(CARDS_CACHE_PATH):
        try:
            with open(CARDS_CACHE_PATH, 'r', encoding='utf-8') as f:
                cache = json.load(f)
                cache.setdefault("all_cards", [])
                return cache
        except Exception:
            pass
    return {
        "last_uid": 0,
        "order_count": 0,
        "today_count": 0,
        "today_date": datetime.now().strftime("%Y-%m-%d"),
        "cards": {},
        "all_cards": []
    }


def save_cache(cache):
    try:
        cache_dir = os.path.dirname(CARDS_CACHE_PATH)
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)
        cache.setdefault("all_cards", [])
        with open(CARDS_CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"❌ Błąd zapisu cache: {e}")


def write_cards_html(cards):
    try:
        lines = [
            "<!DOCTYPE html>",
            "<html lang=\"pl\">",
            "<head><meta charset=\"UTF-8\"><title>Sprzedane karty</title>",
            "<style>body{font-family:Arial;background:transparent;color:white;}",
            "table{border-collapse:collapse;}td,th{border:1px solid white;padding:4px;}" ,
            "</style></head><body>",
            "<table><tr><th>Karta</th><th>Ilość</th></tr>"
        ]
        for name, count in sorted(cards.items(), key=lambda x: x[0]):
            lines.append(f"<tr><td>{name}</td><td>{count}</td></tr>")
        lines.append("</table></body></html>")
        html_dir = os.path.dirname(CARDS_HTML_PATH)
        if html_dir:
            os.makedirs(html_dir, exist_ok=True)
        with open(CARDS_HTML_PATH, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines))
        print(f"✅ Zapisano {CARDS_HTML_PATH}")
    except Exception as e:
        print(f"❌ Błąd zapisu HTML: {e}")


def get_vinted_orders(cache):
    now = datetime.now().astimezone()
    today = now.date()
    newest_cards = []
    newest_date = None
    new_cards_added = False
    mail = None

    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL_ACCOUNT, PASSWORD)
        mail.select(FOLDER)

        last_uid = cache.get("last_uid", 0)
        since_date = (now - timedelta(days=SEARCH_DAYS)).strftime("%d-%b-%Y")
        status, data = mail.uid("search", None, f"SINCE {since_date}")
        if status != "OK":
            print("❌ Nie można pobrać wiadomości.")
            return cache

        uids = [uid for uid in data[0].split() if int(uid) > last_uid]
        print(f"📬 Nowe wiadomości: {len(uids)}")

        for uid in uids:
            try:
                status, msg_data = mail.uid("fetch", uid, "(RFC822)")
                if status != "OK":
                    continue

                raw_email = msg_data[0][1]
                if not isinstance(raw_email, bytes):
                    continue

                msg = email.message_from_bytes(raw_email)
                subject = decode_mime_words(msg.get("Subject", "")).lower()

                date_header = msg.get("Date", "")
                try:
                    msg_datetime = parsedate_to_datetime(date_header).astimezone()
                    msg_date = msg_datetime.date()
                except Exception:
                    msg_datetime = now
                    msg_date = today

                if SEARCH_PHRASE in subject:
                    cache["order_count"] = cache.get("order_count", 0) + 1

                    if cache.get("today_date") != str(today):
                        cache["today_date"] = str(today)
                        cache["today_count"] = 0
                    if msg_date == today:
                        cache["today_count"] = cache.get("today_count", 0) + 1

                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            content_type = part.get_content_type()
                            if content_type in ["text/plain", "text/html"]:
                                payload = part.get_payload(decode=True)
                                if payload:
                                    body += payload.decode(errors="ignore")
                    else:
                        body = msg.get_payload(decode=True).decode(errors="ignore")

                    cards = extract_cards_from_body(body)
                    if cards:
                        for card in cards:
                            name = card["name"]
                            cache.setdefault("cards", {})
                            cache["cards"][name] = cache["cards"].get(name, 0) + 1
                        cache.setdefault("all_cards", [])
                        cache["all_cards"].extend(cards)
                        new_cards_added = True
                        if newest_date is None or msg_datetime > newest_date:
                            newest_cards = cards
                            newest_date = msg_datetime

                last_uid = max(last_uid, int(uid))

            except Exception as e:
                uid_str = uid.decode() if isinstance(uid, bytes) else str(uid)
                print(f"⚠️ Błąd wiadomości UID {uid_str}: {e}")

        cache["last_uid"] = last_uid

        if newest_cards:
            try:
                cards_dir = os.path.dirname(CARDS_OUTPUT_PATH)
                if cards_dir:
                    os.makedirs(cards_dir, exist_ok=True)
                with open(CARDS_OUTPUT_PATH, 'w', encoding='utf-8') as f:
                    json.dump(newest_cards, f, indent=2, ensure_ascii=False)
                print(f"💾 Zapisano {len(newest_cards)} kart do latest_order_cards.json")
            except Exception as e:
                print(f"❌ Błąd zapisu latest_order_cards.json: {e}")
        else:
            print("⚠️ Nie znaleziono żadnych kart do zapisania.")

        if new_cards_added:
            try:
                all_dir = os.path.dirname(ALL_CARDS_PATH)
                if all_dir:
                    os.makedirs(all_dir, exist_ok=True)
                with open(ALL_CARDS_PATH, 'w', encoding='utf-8') as f:
                    json.dump(cache.get("all_cards", []), f, indent=2, ensure_ascii=False)
                print(f"💾 Zaktualizowano {ALL_CARDS_PATH}")
            except Exception as e:
                print(f"❌ Błąd zapisu {ALL_CARDS_PATH}: {e}")

        return cache

    except Exception as e:
        print("❌ Błąd połączenia z IMAP:", e)
        return cache

    finally:
        if mail:
            try:
                mail.logout()
            except Exception:
                pass

def write_json_from_cache(cache):
    try:
        data = {
            "count": cache.get("order_count", 0),
            "today": cache.get("today_count", 0),
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        output_dir = os.path.dirname(OUTPUT_PATH)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        print("✅ Zapisano orders.json")
    except Exception as e:
        print(f"❌ Błąd zapisu JSON: {e}")

if __name__ == "__main__":
    try:
        cache = load_cache()
        while True:
            print("\n⏳ Sprawdzanie zamówień...")
            cache = get_vinted_orders(cache)
            save_cache(cache)
            write_json_from_cache(cache)
            write_cards_html(cache.get("cards", {}))
            print("⏱ Kolejne sprawdzenie za 60 sekund.\n")
            time.sleep(60)
    except KeyboardInterrupt:
        print("\n🛑 Przerwano ręcznie.")
