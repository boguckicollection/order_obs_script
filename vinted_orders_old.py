# -*- coding: utf-8 -*-
import imaplib
import email
import os
import time
import json
from datetime import datetime
from email.header import decode_header
from email.utils import parsedate_to_datetime




# === KONFIGURACJA ===
IMAP_SERVER = 'imap.gmail.com'
EMAIL_ACCOUNT = 'boguckicollection@gmail.com'
PASSWORD = 'tbitweuhanpcbbji'
SEARCH_PHRASE = 'twój przedmiot został sprzedany'
FOLDER = 'Vinted/Sprzedane'
OUTPUT_PATH = r"E:\MOJE PRIV\skrypt\vinted_counter\orders.json"

def decode_mime_words(s):
    decoded_fragments = decode_header(s)
    return ''.join(
        fragment.decode(encoding or 'utf-8') if isinstance(fragment, bytes) else fragment
        for fragment, encoding in decoded_fragments
    )

def get_vinted_orders():
    today = datetime.now().date()
    count = 0
    today_count = 0

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
            if i % 100 == 0 or i == len(message_ids) - 1:
                print(f"🔄 Przetwarzanie: {i + 1}/{len(message_ids)}")

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
                    msg_date = parsedate_to_datetime(date_header).date()
                except:
                    msg_date = today  # awaryjnie przypisujemy dzisiaj

                if SEARCH_PHRASE in subject:
                    count += 1
                    if msg_date == today:
                        today_count += 1

            except Exception as e:
                print(f"⚠️ Błąd wiadomości {i + 1}: {e}")

        print(f"✅ Zamówienia ogółem: {count}")
        print(f"📅 Zamówienia dziś: {today_count}")
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
        os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
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
            time.sleep(60)  # co minutę
    except KeyboardInterrupt:
        print("\n🛑 Przerwano ręcznie.")

