---
type: debt
priority: high
created: 2026-04-24T15:35:22Z
status: implemented
tags: [redis, job-store, retention, maxmemory, runtime, observability, prometheus]
keywords: [maxmemory, RedisJobStore, MemoryJobStore, JobStore, JOB_RETENTION_SEC, expired, retention, cleanup, compare jobs, HTTP 410, prometheus]
patterns: [ttl-based retention, backend parity between memory and redis, expired-job API contract, stale index pruning, runtime cleanup scheduling, structured logging by outcome, prometheus cleanup instrumentation, safe backward-compatible retention rollout]
---

# DEBT-002: Ujednolicona retencja jobow dla odpornosci na Redis maxmemory

## Description
Rozszerzyc obecna obsluge retencji jobow tak, aby cala aplikacja miala spojne zasady wygasania i cleanupu, wspierajace odpornosc runtime przy ograniczeniach pamieci Redis oraz konfiguracji `maxmemory` po stronie infrastruktury. Zmiana ma objac jednolita retencje danych joba i artefaktow, dedykowana obsluge jobow wygaslych, logowanie i metryki operacyjne oraz testy automatyczne.

## Context
Impulsem do ticketu jest zalecenie DevOps zwiazane z ochrona Redis przed przeladowaniem zasobow, zwlaszcza gdy pojawiaja sie porzucone lub dawno nieuzywane joby. Obecnie aplikacja ma juz czesciowa retencje po stronie Redis, ale nie jest ona opisana jako spojny kontrakt calej aplikacji. `RedisJobStore` utrzymuje retencje przez `JOB_RETENTION_SEC`, a `list_jobs()` usuwa stale wpisy indeksu z Redis. Jednoczesnie `MemoryJobStore` nie mial analogicznej retencji, API zwracalo zwykle `404` dla brakujacego joba bez rozroznienia stanu `expired`, a observability nie opisywalo cleanupu i wygasania jako pierwszorzednego scenariusza operacyjnego.

## Requirements
Ticket pozostaje pojedynczy i dotyczy warstwy aplikacyjnej, nie zmian infrastrukturalnych Redis. Mechanizm cleanupu nie jest jeszcze przesadzony i ma zostac dobrany po researchu, ale efekt koncowy musi byc wspolny dla backendow `redis` i `memory`, bez rozjazdu zachowania miedzy `dev` i `prod`.

### Functional Requirements
- Wprowadzic jeden spojny kontrakt retencji jobow dla calej aplikacji, obejmujacy co najmniej backendy `redis` i `memory`.
- Dodac jeden wspolny konfigurowalny czas retencji, bez podzialu per srodowisko; wstepny default to `24h`.
- Po uplywie retencji usuwac caly stan joba, w tym wynik, status, metadane oraz artefakty typu heatmap.
- Zachowac cleanup struktur pomocniczych backendu, takich jak indeksy jobow lub inne odniesienia, tak aby nie zostawaly osierocone wpisy.
- Dodac dedykowana obsluge API dla joba wygaslego, odrozniac go od zwyklego `not found`; preferowany jest osobny status HTTP, np. `410 Gone`, o ile research nie wykaze lepszego zgodnego kontraktu.
- Dodac porzadne logowanie poziomami `INFO/DEBUG/WARNING/ERROR` dla tworzenia, cleanupu, wygasania, prob odczytu wygaslych jobow oraz bledow cleanupu.
- Dodac metryki Prometheusa lub inna zgodna z obecna warstwa observability instrumentacje pokazujaca liczbe cleanupow, wygasnietych jobow i ewentualnych bledow cleanupu.
- Dobrac mechanizm cleanupu na podstawie researchu; dopuszczalne sa minimalne rozwiazania typu lazy cleanup, cleanup przy odczycie/zapisie albo zadanie okresowe/cron uruchamiane po stronie aplikacji.
- Dodac testy automatyczne obejmujace retencje, cleanup, kontrakt `expired` i observability.

### Non-Functional Requirements
- Zmiana ma byc bezpieczna wstecznie: poza nowymi zabezpieczeniami i dedykowana obsluga `expired` nie powinna wprowadzac niekontrolowanej zmiany zachowania.
- Zachowanie ma byc spojne miedzy `dev` i `prod`; jeden wspolny model konfiguracji i retencji.
- Implementacja ma uzupelniac zabezpieczenia Redis po stronie infrastruktury, a nie zastepowac konfiguracji `maxmemory` ani polityk eviction poza aplikacja.
- Cleanup i retencja nie moga powodowac cichych awarii glownego flow tworzenia i odczytu jobow.
- Logi musza byc uzyteczne operacyjnie i nie moga ujawniac danych wrazliwych.

## Current State
`RedisJobStore` ma retencje danych joba i heatmapy przez `JOB_RETENTION_SEC` (domyslnie `86400`) oraz usuwa stale wpisy indeksu podczas `list_jobs()`. `MemoryJobStore` przechowuje joby i heatmapy bez retencji czasowej. API w `app/api/routes/compare.py` zwraca `404` dla brakujacego joba lub heatmapy i nie ma jawnego kontraktu `expired`/`410`. Schemat `JobStatusName` dopuszcza tylko `queued`, `running`, `done`, `error`. Warstwa metryk Prometheusa istnieje, ale nie opisuje cleanupu ani wygasania jobow jako osobnych sygnalow.

## Desired State
Aplikacja ma jeden jawny, konfigurowalny i przetestowany model retencji jobow, ktory ogranicza dlug zycia danych i artefaktow niezaleznie od backendu, wspiera odpornosc przy limitach pamieci Redis i pozwala operatorom obserwowac cleanup oraz wygasanie. Klient API dostaje kontrolowana odpowiedz dla joba, ktory istnial, ale wygasl. Observability obejmuje logi i metryki cleanupu, a zmiana nie wymaga roznych konfiguracji zachowania dla `dev` i `prod`.

## Research Context
Research powinien potwierdzic, jak daleko siega juz obecna retencja w `JobStore`, jak najlepiej zachowac parity miedzy backendami, czy dla `expired` potrzebny jest nowy status domenowy czy wystarczy odroznienie na poziomie odpowiedzi HTTP, oraz jaki mechanizm cleanupu najmniej narusza obecna architekture FastAPI + Celery + Redis.

### Keywords to Search
- `app/core/job_store.py` - glowna implementacja backendow `memory` i `redis`, TTL i cleanup indeksow.
- `RedisJobStore` - obecne TTL, `ttl()`, `zadd`, `zrem`, zachowanie przy wygaslych kluczach.
- `MemoryJobStore` - brak retencji i miejsce na parity z Redis.
- `JOB_RETENTION_SEC` - kanoniczny kontrakt czasu zycia joba i artefaktu heatmapy.
- `list_jobs` - istniejacy wzorzec prune stale index entries.
- `app/api/routes/compare.py` - odpowiedzi `404`, kontrakt odczytu joba i heatmapy.
- `JobStatusName` - ograniczenia domenowego statusu joba.
- `app/core/metrics.py` - obecna warstwa Prometheusa i miejsce na nowe sygnaly cleanupu.
- `tests/test_job_store.py` - istniejace testy TTL/startupu i wzorce fake Redis.
- `tests/test_jobs_api.py` - testy kontraktu API jobow i heatmap.
- `maxmemory` - powod biznesowo-operacyjny i slowo kluczowe do przejrzenia komentarzy, envow lub dokumentacji.

### Patterns to Investigate
- Spojna retencja czasowa dla wielu backendow storage przy jednym kontrakcie aplikacyjnym.
- Rozroznienie `expired` vs `not found` bez nadmiernego rozszerzania publicznego API.
- Cleanup osieroconych indeksow i artefaktow przy TTL po stronie Redis.
- Minimalny mechanizm cleanupu dla backendu in-memory bez dokladania zbednej infrastruktury.
- Structured logging dla scenariuszy retencji i degradacji runtime.
- Prometheus instrumentation dla cleanupu/expired bez psucia semantyki istniejacych licznikow.
- Retencja danych joba vs retencja agregowanych metryk Prometheus; trzeba sprawdzic, czy wymaganie "usuwania metryk" da sie spelnic bez naruszenia modelu observability.

### Key Decisions Made
- Ticket typu `debt` i priorytet `high` - dotyczy odpornosci runtime i zalecen operacyjnych DevOps.
- Zakres dotyczy calej aplikacji, nie tylko backendu Redis.
- Retencja ma byc spojna miedzy backendami `redis` i `memory`.
- Jeden wspolny config retencji ma obowiazywac tak samo w `dev` i `prod`.
- Wstepny default retencji to `24h`.
- Po retencji usuwany jest caly stan joba wraz z artefaktami.
- Dla wygaslych jobow potrzebna jest dedykowana odpowiedz API, rozna od zwyklego `404`.
- Ticket ma objac logowanie `INFO/DEBUG/WARNING/ERROR`, metryki Prometheusa i testy automatyczne.
- Mechanizm cleanupu pozostaje otwarty do decyzji po researchu; nie narzucamy z gory cron vs lazy cleanup.
- Zmiana ma pozostac bezpieczna wstecznie i nie obejmuje dokumentacji operacyjnej.

## Success Criteria
Ticket jest kompletny, gdy aplikacja egzekwuje jeden model retencji jobow dla wszystkich backendow, cleanup usuwa dane i artefakty po czasie retencji, API rozroznia `expired` od `not found`, a operator widzi cleanup i wygasanie w logach oraz metrykach. Dodatkowo testy automatyczne potwierdzaja zachowanie na poziomie `JobStore` i API.

### Automated Verification
- [ ] `pytest -q`
- [ ] `ruff check .`
- [ ] `black --check .`
- [ ] `mypy .`
- [ ] Testy jednostkowe pokrywaja retencje i cleanup dla `RedisJobStore`.
- [ ] Testy jednostkowe pokrywaja parity retencji i cleanupu dla `MemoryJobStore`.
- [ ] Testy API potwierdzaja dedykowany kontrakt odpowiedzi dla wygaslego joba i wygaslej heatmapy.
- [ ] Testy potwierdzaja emisje logow/metryk cleanupu lub co najmniej ich glownych sygnalow integracyjnych.

### Manual Verification
- [ ] Utworzenie joba i odczyt przed uplywem retencji dziala bez regresji.
- [ ] Po uplywie retencji job i jego artefakty nie sa juz dostepne.
- [ ] Odczyt wygaslego joba zwraca dedykowana odpowiedz zgodna z nowym kontraktem API.
- [ ] Logi pozwalaja odroznic zwykle `not found`, wygasanie i blad cleanupu.
- [ ] Metryki/observability pokazuje cleanup i wygasanie w sposob uzyteczny operacyjnie.
- [ ] Zachowanie jest takie samo przy backendzie `memory` i `redis`, poza naturalnymi roznicami implementacyjnymi.

## Related Information
- `app/core/job_store.py` - obecna implementacja retencji i backendow store.
- `app/api/routes/compare.py` - aktualny kontrakt API dla odczytu joba i heatmapy.
- `app/schemas/compare.py` - statusy jobow i modele odpowiedzi.
- `app/core/metrics.py` - aktualna warstwa Prometheus.
- `tests/test_job_store.py` - obecne testy dla RedisJobStore.
- `tests/test_jobs_api.py` - obecne testy flow jobow i heatmap.

## Notes
- Out of scope: zmiana samej konfiguracji infrastrukturalnej Redis (`maxmemory`, `maxmemory-policy`, provisioning, helm, compose tuning), chyba ze research wykaze minimalna konieczna korekte aplikacyjnego runtime wiring.
- Out of scope: rozne czasy retencji per srodowisko albo osobne polityki dla `dev` i `prod`.
- Out of scope: aktualizacja dokumentacji operacyjnej.
- Otwarte pytanie do researchu: czy wymaganie "usuwania metryk po czasie" powinno byc zrealizowane jako cleanup danych powiazanych z jobem i nowe metryki cleanupu, zamiast TTL dla agregowanych licznikow/histogramow Prometheus.
