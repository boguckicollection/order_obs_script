# -*- coding: utf-8 -*-
"""Simplified Vinted order monitor.

This script checks a mailbox for new Vinted orders and fetches
Pokémon card data from the Pokémon TCG API.  Latest order cards are
stored in ``latest_order_cards.json`` and the order counter is written
to ``orders.json``.  Use the included HTML files to display the video
alert and card list in OBS.
"""

from __future__ import annotations

import email
import imaplib
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.header import decode_header
from typing import Dict, List

import requests


@dataclass
class Config:
    imap_server: str
    email_account: str
    password: str
    search_phrase: str
    folder: str
    api_key: str
    orders_path: str = "orders.json"
    cards_path: str = "latest_order_cards.json"
    cache_path: str = "cache.json"
    search_days: int = 10
    interval: int = 60  # seconds


def load_env(path: str = ".env") -> None:
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


def read_config() -> Config:
    load_env()
    return Config(
        imap_server=os.getenv("IMAP_SERVER", "imap.gmail.com"),
        email_account=os.getenv("EMAIL_ACCOUNT", ""),
        password=os.getenv("EMAIL_PASSWORD", ""),
        search_phrase=os.getenv("SEARCH_PHRASE", "twój przedmiot został sprzedany"),
        folder=os.getenv("FOLDER", "INBOX"),
        api_key=os.getenv("API_KEY", ""),
        orders_path=os.getenv("OUTPUT_PATH", "orders.json"),
        cards_path=os.getenv("CARDS_OUTPUT_PATH", "latest_order_cards.json"),
        cache_path=os.getenv("CARDS_CACHE_PATH", "cache.json"),
        search_days=int(os.getenv("SEARCH_DAYS", "10")),
        interval=int(os.getenv("CHECK_INTERVAL", "60")),
    )


def decode_subject(s: str) -> str:
    parts = decode_header(s)
    return "".join(
        p.decode(enc or "utf-8") if isinstance(p, bytes) else p
        for p, enc in parts
    )


def load_cache(path: str) -> Dict:
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"last_uid": 0, "count": 0}


def save_cache(path: str, cache: Dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)


def parse_cards(body: str, api_key: str) -> List[Dict[str, str]]:
    pattern = r"(.+?)\s*\((\w+)\s+(\w+)\)"
    cards = []
    for name, set_code, number in re.findall(pattern, body):
        query = f'name:"{name.strip()}" set.id:{set_code} number:{number}'
        r = requests.get(
            "https://api.pokemontcg.io/v2/cards",
            headers={"X-Api-Key": api_key},
            params={"q": query},
        )
        if r.status_code == 200:
            data = r.json().get("data")
            if data:
                card = data[0]
                cards.append({
                    "name": card["name"],
                    "set": card["set"]["id"],
                    "number": card["number"],
                    "image": card["images"]["large"],
                })
    return cards


def fetch_new_orders(cfg: Config, cache: Dict) -> List[Dict[str, str]]:
    mail = None
    newest_cards: List[Dict[str, str]] = []
    try:
        mail = imaplib.IMAP4_SSL(cfg.imap_server)
        mail.login(cfg.email_account, cfg.password)
        mail.select(cfg.folder)

        since = (datetime.now() - timedelta(days=cfg.search_days)).strftime("%d-%b-%Y")
        status, data = mail.uid("search", None, f"SINCE {since}")
        if status != "OK":
            return []

        last_uid = cache.get("last_uid", 0)
        uids = [uid for uid in data[0].split() if int(uid) > last_uid]
        for uid in uids:
            status, msg_data = mail.uid("fetch", uid, "(RFC822)")
            if status != "OK" or not msg_data:
                continue
            raw = msg_data[0][1]
            if not isinstance(raw, bytes):
                continue
            msg = email.message_from_bytes(raw)
            subject = decode_subject(msg.get("Subject", "")).lower()
            if cfg.search_phrase.lower() not in subject:
                last_uid = max(last_uid, int(uid))
                continue

            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    ct = part.get_content_type()
                    if ct in ("text/plain", "text/html"):
                        payload = part.get_payload(decode=True)
                        if payload:
                            body += payload.decode(errors="ignore")
            else:
                payload = msg.get_payload(decode=True)
                if payload:
                    body = payload.decode(errors="ignore")

            cards = parse_cards(body, cfg.api_key)
            if cards:
                newest_cards = cards
                cache["count"] = cache.get("count", 0) + 1
            last_uid = max(last_uid, int(uid))

        cache["last_uid"] = last_uid
        return newest_cards
    finally:
        if mail:
            try:
                mail.logout()
            except Exception:
                pass


def write_orders(path: str, count: int) -> None:
    data = {
        "count": count,
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def write_cards(path: str, cards: List[Dict[str, str]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cards, f, indent=2, ensure_ascii=False)


def main() -> None:
    cfg = read_config()
    cache = load_cache(cfg.cache_path)

    while True:
        print("Checking for new orders...")
        cards = fetch_new_orders(cfg, cache)
        save_cache(cfg.cache_path, cache)
        write_orders(cfg.orders_path, cache.get("count", 0))
        if cards:
            write_cards(cfg.cards_path, cards)
            print(f"Found order with {len(cards)} card(s).")
        time.sleep(cfg.interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Stopped by user.")

