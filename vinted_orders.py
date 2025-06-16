
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
)
FOLDER = os.getenv("FOLDER", "Vinted/Sprzedane")
OUTPUT_PATH = os.getenv("OUTPUT_PATH", "orders.json")
CARDS_OUTPUT_PATH = os.getenv("CARDS_OUTPUT_PATH", "latest_order_cards.json")
API_KEY = os.getenv("API_KEY", "")

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
        url = f'https://api.pokemontcg.io/v2/cards?q={query}'
        headers = { "X-Api-Key": API_KEY }

        try:
            r = requests.get(url, headers=headers)
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

def get_vinted_orders():
    now = datetime.now().astimezone()
    count = 0
    today_count = 0
    newest_cards = []
    newest_date = None

    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL_ACCOUNT, PASSWORD)
        mail.select(FOLDER)

        status, data = mail.search(None, "ALL")
        if status != "OK":
            print("❌ Nie można pobrać wiadomości.")
            return 0, 0

        message_ids = data[0].split()
        print(f"📬 Wiadomości do sprawdzenia: {len(message_ids)}")

        for i, msg_id in enumerate(message_ids):
            try:
                status, msg_data = mail.fetch(msg_id, "(RFC822)")
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
                except:
                    continue

                if SEARCH_PHRASE in subject:
                    count += 1
                    if msg_date == now.date():
                        today_count += 1

                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            content_type = part.get_content_type()
                            if content_type in ["text/plain", "text/html"]:
                                body += part.get_payload(decode=True).decode(errors="ignore")
                    else:
                        body = msg.get_payload(decode=True).decode(errors="ignore")

                    cards = extract_cards_from_body(body)
                    if cards:
                        if newest_date is None or msg_datetime > newest_date:
                            newest_cards = cards
                            newest_date = msg_datetime

            except Exception as e:
                print(f"⚠️ Błąd wiadomości {i + 1}: {e}")

        print(f"✅ Zamówienia ogółem: {count}")
        print(f"📅 Zamówienia dziś: {today_count}")

        if newest_cards:
            try:
                cards_dir = os.path.dirname(CARDS_OUTPUT_PATH)
                if cards_dir:
                    os.makedirs(cards_dir, exist_ok=True)
                with open(CARDS_OUTPUT_PATH, 'w', encoding='utf-8') as f:
                    json.dump(newest_cards, f, indent=2)
                print(f"💾 Zapisano {len(newest_cards)} kart do latest_order_cards.json")
            except Exception as e:
                print(f"❌ Błąd zapisu latest_order_cards.json: {e}")
        else:
            print("⚠️ Nie znaleziono żadnych kart do zapisania.")

        return count, today_count

    except Exception as e:
        print("❌ Błąd połączenia z IMAP:", e)
        return 0, 0

def write_json(order_count, today_count):
    try:
        data = {
            "count": order_count,
            "today": today_count,
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
        while True:
            print("\n⏳ Sprawdzanie zamówień...")
            count, today = get_vinted_orders()
            write_json(count, today)
            print("⏱ Kolejne sprawdzenie za 60 sekund.\n")
            time.sleep(60)
    except KeyboardInterrupt:
        print("\n🛑 Przerwano ręcznie.")
