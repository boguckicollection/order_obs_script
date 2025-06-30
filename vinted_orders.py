
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
SEARCH_DAYS = int(os.getenv("SEARCH_DAYS", "10"))

def decode_mime_words(s):
    decoded_fragments = decode_header(s)
    return ''.join(
        fragment.decode(encoding or 'utf-8') if isinstance(fragment, bytes) else fragment
        for fragment, encoding in decoded_fragments
    )


def search_card_in_api(name, number, set_code=None):
    """Search for a card in the API using a normalized name and number.

    Optionally a set code can be provided to narrow down the results.
    """
    # Preserve possible set prefixes in the card number (e.g. "SV21", "SWSH105")
    # while removing spaces and any trailing set size like "119/198".
    number = number.strip().lstrip("#")
    number = number.replace(" ", "")
    if "/" in number:
        number = number.split("/")[0]
    name = name.strip()

    queries = []
    if set_code:
        queries.append(f"set.id:{set_code} number:{number}")
    queries.append(f'name:"{name}" number:{number}')

    headers = {"X-Api-Key": API_KEY}

    for query in queries:
        print(f"🔎 Zapytanie: {query}")
        try:
            r = requests.get(
                "https://api.pokemontcg.io/v2/cards",
                headers=headers,
                params={"q": query}
            )
            if r.status_code != 200:
                print(f"⚠️ API zwróciło status {r.status_code}")
                continue

            data = r.json()
            if data.get("data"):
                card = data["data"][0]
                return {
                    "name": card["name"],
                    "set": card["set"]["id"],
                    "number": card["number"],
                    "image": card["images"]["large"]
                }
        except Exception as e:
            print(f"❌ Błąd API ({name} {number}): {e}")
            return None

    return None


def clean_card_name(name: str) -> str:
    """Try to remove user names or quantities from the card name."""
    name = name.strip()
    # Remove quantity like "1x "
    name = re.sub(r'^\d+x\s*', '', name, flags=re.IGNORECASE)
    # Remove phrases like "aleks1515 kupił(a)"
    name = re.sub(r'^.*kupi\S*\s+', '', name, flags=re.IGNORECASE)
    # If a colon is present, take text after it
    if ':' in name:
        name = name.split(':')[-1]
    return name.strip()

def extract_cards_from_body(body):
    soup = BeautifulSoup(body, "html.parser")
    text = soup.get_text()
    # W treści wiadomości karty mogą mieć format np.
    # "Hydreigon ex (SVP 119)" lub "Hydreigon ex (SVP 119/198)".
    # Dotychczasowy wzorzec nie obsługiwał znaków takich jak "-" czy "/".
    # Some Pokémon names contain letters with diacritics (e.g. "Pokémon").
    # Allow a broader range of unicode letters so such names are detected.
    pattern = (
        r"([\wÀ-ÖØ-öø-ÿ][\wÀ-ÖØ-öø-ÿ ':,-]*[\wÀ-ÖØ-öø-ÿ])\s*"
        r"\(([A-Za-z0-9-]+)\s+#?([A-Za-z0-9/]+)\)"
    )
    matches = re.findall(pattern, text, flags=re.IGNORECASE)
    print(f"🔍 Znaleziono {len(matches)} kart w treści e-maila.")
    results = []

    for name, set_code, number in matches:
        clean_name = clean_card_name(name)
        card = search_card_in_api(clean_name, number, set_code)
        if card:
            results.append(card)
            print(f"✅ Dodano kartę: {card['name']} ({card['set']} {card['number']})")
        else:
            print(
                f"❌ Nie znaleziono karty {clean_name} ({set_code} {number}). "
                "Sprawdź set.id i numer."
            )
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


def write_cards_html(cards, all_cards=None):
    """Write a small summary HTML with total sold cards and top 3 list."""
    try:
        if all_cards:
            counts = {}
            for card in all_cards:
                full = f"{card['name']} ({card['set']} {card['number']})"
                counts[full] = counts.get(full, 0) + 1
        else:
            counts = dict(cards)

        total = sum(counts.values())
        top = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:3]

        lines = [
            "<!DOCTYPE html>",
            "<html lang=\"pl\">",
            "<head>",
            "<meta charset=\"UTF-8\">",
            "<title>Sprzedane karty</title>",
            (
                "<link rel=\"preconnect\" href=\"https://fonts.googleapis.com\">"
                "<link rel=\"preconnect\" href=\"https://fonts.gstatic.com\" crossorigin>"
                "<link href=\"https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600&display=swap\" rel=\"stylesheet\">"
                "<style>body{margin:0;padding:0;background:transparent;color:white;font-family:'Montserrat',Arial,sans-serif;}"
                "#container{padding:20px;border-radius:16px;background:rgba(0,0,0,0.4);backdrop-filter:blur(8px);display:inline-block;}"
                ".total{font-size:28px;margin-bottom:8px;font-weight:600;text-align:center;}"
                "ol{margin:0;padding-left:20px;font-size:22px;}li{margin-bottom:4px;}"
                "</style>"
            ),
            "</head><body>",
            f"<div id=\"container\"><div class=\"total\">Łącznie sprzedanych kart: {total}</div><ol>"
        ]

        for name, count in top:
            lines.append(f"<li>{name} – {count}</li>")

        lines.append("</ol></div></body></html>")

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
        if SEARCH_DAYS > 0:
            since_date = (now - timedelta(days=SEARCH_DAYS)).strftime("%d-%b-%Y")
            status, data = mail.uid("search", None, f"SINCE {since_date}")
        else:
            status, data = mail.uid("search", None, "ALL")
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
            write_cards_html(cache.get("cards", {}), cache.get("all_cards", []))
            print("⏱ Kolejne sprawdzenie za 60 sekund.\n")
            time.sleep(60)
    except KeyboardInterrupt:
        print("\n🛑 Przerwano ręcznie.")
