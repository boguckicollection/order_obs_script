# order_obs_script

Skrypt monitoruje skrzynkę e‑mail i zlicza zamówienia z serwisu **Vinted**. Dane są zapisywane w formacie JSON, a dołączone pliki HTML mogą być użyte jako widżety w programie OBS.

## Wymagania

- Python 3.8 lub nowszy
- biblioteki `requests` oraz `beautifulsoup4`

Instalacja zależności:

```bash
pip install requests beautifulsoup4
```

## Konfiguracja

1. Skopiuj plik `.env.example` do `.env` i uzupełnij wymagane dane:

```env
IMAP_SERVER=imap.gmail.com
EMAIL_ACCOUNT=twoj-email@gmail.com
EMAIL_PASSWORD=twoje-haslo
SEARCH_PHRASE=twój przedmiot został sprzedany
FOLDER=Vinted/Sprzedane
OUTPUT_PATH=/sciezka/do/orders.json
CARDS_OUTPUT_PATH=/sciezka/do/latest_order_cards.json
CARDS_CACHE_PATH=/sciezka/do/cards_cache.json
CARDS_HTML_PATH=/sciezka/do/cards_count.html
ALL_CARDS_PATH=/sciezka/do/all_order_cards.json
API_KEY=klucz-do-api
SEARCH_DAYS=10
YT_API_KEY=klucz-youtube
YT_CHANNEL_ID=id-kanalu
VIDEOS_OUTPUT_PATH=/sciezka/do/videos.json
```

Wartość `SEARCH_DAYS` określa liczbę dni wstecz, z których pobierane są
wiadomości. Ustaw `0`, aby przeszukać całą skrzynkę bez ograniczenia daty.

2. Pliki wyjściowe (JSON/HTML) zostaną zapisane w lokalizacjach podanych w konfiguracji.

## Uruchomienie

Po przygotowaniu konfiguracji uruchom skrypt:

```bash
python vinted_orders.py
```

Skrypt będzie cyklicznie sprawdzał nowe wiadomości e‑mail i aktualizował pliki JSON oraz HTML.

### Aktualizacja filmów z YouTube

Do pobrania najnowszych filmów z własnego kanału można użyć skryptu `youtube_videos.py`:

```bash
python youtube_videos.py
```

Wymagane są zmienne `YT_API_KEY` oraz `YT_CHANNEL_ID` w pliku `.env`. Wynik zostanie zapisany do `videos.json` (ścieżkę można zmienić w `VIDEOS_OUTPUT_PATH`).

## Widżety OBS

- **widget.html** – prosty licznik zamówień oraz licznik dzienny.
- **alert.html** – odtwarza plik *Transition.webm* w momencie pojawienia się nowego zamówienia.
- **karty.html** – wyświetla nazwy i grafiki kart Pokémon z najnowszego zamówienia.

Do wyszukiwania kart wykorzystywany jest teraz identyfikator `set.id`, dzięki czemu możliwe jest odnalezienie kart z zagranicznych wersji zestawów.

Pliki te można dodać jako źródło przeglądarki w OBS.

## Licencja

Projekt udostępniony jest bez gwarancji jakiejkolwiek przydatności. Korzystasz na własną odpowiedzialność.
