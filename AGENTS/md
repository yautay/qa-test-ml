# AGENTS Playbook

Ten dokument definiuje zasady pracy agentow (AI i developerow) dla repozytorium `qa-test-pms`.
Cele: szybsza realizacja zadan, nizsze zuzycie tokenow oraz spojnosc techniczna kodu.

## 1) Kontekst systemu

Projekt to usluga FastAPI do porownywania obrazow (LPIPS/DISTS), z przetwarzaniem asynchronicznym przez Celery i wspolnym stanem w Redis.

Przeplyw high-level:
1. API (`app/api/routes`) przyjmuje zlecenie i waliduje dane (`app/schemas`).
2. Job jest zapisywany w `JobStore` (`app/core/job_store.py`).
3. Celery task (`app/tasks/compare_tasks.py`) wykonuje obliczenia metryk (`app/metrics`).
4. Wynik i status wracaja do Redis; API zwraca status klientowi.

## 2) Zasady architektury

1. Separacja warstw:
   - `app/api/*`: transport HTTP, bez logiki domenowej.
   - `app/schemas/*`: kontrakty wejscia/wyjscia.
   - `app/core/*`: konfiguracja, infrastruktura, mechanizmy wspolne.
   - `app/metrics/*`: czysta logika metryk.
   - `app/tasks/*`: orkiestracja przetwarzania asynchronicznego.

2. Kierunek zaleznosci:
   - API moze uzywac `schemas`, `core`, `tasks`.
   - `metrics` nie zalezy od `api`.
   - Kod domenowy nie importuje endpointow.

3. Rozszerzanie funkcjonalnosci:
   - Nowy endpoint: dodaj route + schema + test API.
   - Nowa metryka: dodaj implementacje w `app/metrics`, rejestracje w `app/core/registry.py`, testy jednostkowe i integracyjne.
   - Nowy backend infrastrukturalny: izoluj za interfejsem w `app/core`.

4. Stabilnosc i observability:
   - Kazda sciezka bledna musi zwracac kontrolowany blad i log z kontekstem.
   - Metryki runtime utrzymuj zgodne z Prometheus naming i etykietami istniejacymi w projekcie.

## 3) Styl kodowania

1. Python 3.12, pelne type hints dla nowego kodu.
2. Format i lint:
   - `black` (line length 120)
   - `ruff`
   - `mypy` dla modulow modyfikowanych
3. Czytelnosc:
   - Male funkcje, jedna odpowiedzialnosc.
   - Brak ukrytych efektow ubocznych.
   - Nazwy jawne, bez skrotow biznesowych niezdefiniowanych w domenie.
4. Bledy i walidacja:
   - Waliduj dane na granicy systemu (schema/route).
   - Uzywaj jawnych wyjatkow i jednolitego mapowania na odpowiedzi API.
5. Logowanie:
   - Logi strukturalne i neutralne (bez danych wrazliwych, tokenow, sekretow).
   - Poziom logowania dobrany do istotnosci (`DEBUG` tylko diagnostyka).

## 4) Standard testow

1. Zmiana kodu produkcyjnego wymaga adekwatnych testow.
2. Priorytet:
   - unit test dla logiki metryk/core,
   - integration/API test dla kontraktow endpointow,
   - test scenariusza bledu dla nowych warunkow brzegowych.
3. Minimalny check przed oddaniem:
   - `pytest -q`
   - `ruff check .`
   - `black --check .`

## 5) Zasady pracy agenta (optymalizacja tokenow)

1. Zanim cokolwiek zmienisz, czytaj tylko pliki konieczne do zadania.
2. Uzywaj precyzyjnego wyszukiwania (`glob`, `grep`) zamiast szerokiego skanowania repo.
3. Unikaj powtarzania tych samych odczytow i dlugich cytatow kodu.
4. Wprowadzaj najmniejszy mozliwy patch, zgodny z istniejacym stylem.
5. Komunikuj rezultat krotko: co zmieniono, gdzie, jak zweryfikowano.

## 6) Konwencja commitow

Stosuj klarowne komunikaty w stylu:
- `docs: add agent guidelines for architecture and coding standards`
- `feat: add <funkcja> to <modul> to support <cel biznesowy>`
- `fix: prevent <problem> in <obszar>`

Kazdy commit powinien opisywac intencje (dlaczego), nie tylko liste zmian.

## 7) Definition of Done

Zmiana jest gotowa, gdy:
1. Architektonicznie pasuje do warstw i kierunku zaleznosci.
2. Przechodzi lint/format/testy dla zmodyfikowanego zakresu.
3. Jest opisana zrozumialym commitem.
4. Nie pogarsza czytelnosci i nie wprowadza duplikacji.
