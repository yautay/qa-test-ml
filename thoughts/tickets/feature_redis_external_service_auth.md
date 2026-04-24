---
type: feature
priority: high
created: 2026-04-24T12:00:00Z
status: reviewed
tags: [redis, configuration, security, tls, celery, fastapi]
keywords: [redis, rediss, env configuration, redis auth, redis username, redis password, startup validation, celery redis, job store redis, retry, timeout, logger]
patterns: [settings loading from env, redis client initialization, startup fail-fast validation, runtime error logging, secret masking in logs, celery/redis integration, docker-compose env wiring, .env.example maintenance]
---

# FEATURE-001: Konfigurowalne polaczenie do zewnetrznego Redis z auth i TLS

## Description
Wprowadzic mozliwosc konfiguracji polaczenia do wskazanego zewnetrznego zasobu Redis przez `.env`, z uwierzytelnianiem `username/password` oraz wsparciem `rediss://` (TLS). Zmiana ma umozliwic odejscie od domyslnego zalozenia Redis uruchamianego lokalnie w Docker na rzecz niezaleznej uslugi na osobnej maszynie.

## Context
Aktualnie produkcyjnie wykorzystywany jest Redis uruchamiany w Docker. Docelowy model zaklada zewnetrzna usluge Redis, co ma poprawic maintenance i security. Funkcja konfiguracyjna jest przeznaczona dla konfiguracji przez `.env` (bez osobnego UI).

## Requirements
Zmiana ma byc kompatybilna z obecnym mechanizmem PMS: bez refaktoryzacji logiki kolejek/jobow, tylko rozszerzenie konfiguracji Redis i obslugi polaczenia.

### Functional Requirements
- Konfiguracja Redis przez `.env` z mozliwoscia wskazania zewnetrznego hosta/uslugi.
- Uwierzytelnianie do Redis przez `username/password`.
- Wsparcie TLS na poziomie polaczenia (`rediss://`) wraz z walidacja konfiguracji.
- Jeden wspolny Redis dla wszystkich komponentow aplikacji (brak rozdzielnych endpointow per komponent).
- Walidacja konfiguracji przy starcie aplikacji (fail-fast) z czytelnym wyjatkiem startupowym i logiem.
- W runtime bledy polaczenia/operacyjne maja byc logowane do istniejacego loggera aplikacyjnego.
- Konfigurowalne timeouty i retry przez `.env`.
- Retry zachowuje obecna semantyke aplikacji: jesli mechanizm retry juz istnieje, ma objac nowa konfiguracje; jesli nie istnieje, nie dodajemy nowego mechanizmu.
- Aktualizacja dokumentacji do stanu docelowego oraz aktualizacja przykladowych konfiguracji (`.env.example`, konfiguracja lokalna/testowa).

### Non-Functional Requirements
- Security: maskowanie danych wrazliwych (haslo/uzytkownik) w logach i komunikatach bledow.
- Reliability: timeout i retry parametryzowane przez `.env`.
- Compatibility: lokalne i testowe srodowiska (np. docker-compose) pozostaja dzialajace po zmianach konfiguracyjnych.
- Scope constraint: brak zmian w semantyce przetwarzania PMS/Celery poza warstwa konfiguracji Redis.

## Current State
Redis jest uzywany produkcyjnie w modelu kontenerowym (Docker). Konfiguracja nie pokrywa w pelni docelowego scenariusza zewnetrznej uslugi Redis z auth `username/password` i `rediss://`.

## Desired State
Aplikacja PMS moze laczyc sie do zewnetrznego Redis konfigurowanego przez `.env`, z auth i TLS, z walidacja startupowa, kontrolowanym logowaniem bledow runtime, maskowaniem sekretow oraz zaktualizowana dokumentacja i przyklady konfiguracji.

## Research Context
Badanie powinno potwierdzic konkretne punkty integracji Redis w kodzie (API/JobStore/Celery), obecny mechanizm retry, sposob ladowania ustawien z `.env` oraz miejsca logowania bledow i sanitizacji danych.

### Keywords to Search
- `app/core/config` - zrodlo ladowania konfiguracji z `.env`.
- `redis` - miejsca inicjalizacji klienta i polaczen Redis.
- `JobStore` - komponenty zapisujace statusy jobow.
- `Celery` - konfiguracja broker/backend z Redis.
- `rediss://` - potencjalne wsparcie TLS i walidacja URI.
- `timeout` - obecne parametry timeoutu dla klienta Redis.
- `retry` - aktualny mechanizm ponawiania i jego zasieg.
- `logger` - wzorce logowania bledow runtime.
- `.env.example` - aktualny kontrakt konfiguracji dla srodowisk.
- `docker-compose` - lokalne/testowe mapowanie zmiennych srodowiskowych.

### Patterns to Investigate
- Ladowanie ustawien aplikacji z env (Pydantic Settings / config module).
- Tworzenie i wspoldzielenie klienta Redis miedzy warstwami.
- Strategia fail-fast przy starcie vs obsluga bledow runtime.
- Wzorce sanitizacji logow dla danych wrazliwych.
- Integracja Celery z Redis w obecnej architekturze.
- Wzorce aktualizacji dokumentacji i przykladowych envow w repo.

### Key Decisions Made
- Ticket typu `feature` i priorytet `high` - krytyczne dla modelu docelowego infrastruktury.
- Konfiguracja tylko przez `.env` - bez dodatkowego interfejsu konfiguracyjnego.
- Jeden wspolny Redis dla calej aplikacji - brak podzialu endpointow.
- Auth: tylko `username/password`.
- TLS: tylko `rediss://` + walidacja (bez dodatkowej obslugi certyfikatow klienta).
- Brak fallbacku na inny Redis - pojedynczy docelowy tryb konfiguracji.
- Fail-fast przy starcie + logowanie bledow runtime.
- Retry: bez zmiany semantyki (reuse istniejacego mechanizmu, bez dodawania nowego jezeli nie istnieje).
- Rotacja sekretow bez restartu jest out of scope.
- Zakres obejmuje kod i dokumentacje (w tym przykladowe konfiguracje).
- Ticket pozostaje pojedynczy (nie dzielimy na pod-tickety).

## Success Criteria
Zmiana jest uznana za kompletna, gdy serwis PMS poprawnie dziala z zewnetrznym Redis (auth + TLS), konfiguracja jest walidowana na starcie, bledy runtime sa logowane bez wycieku sekretow, a dokumentacja i przyklady env sa aktualne.

### Automated Verification
- [ ] `pytest -q`
- [ ] `ruff check .`
- [ ] `black --check .`
- [ ] Testy integracyjne potwierdzaja polaczenie z Redis auth + `rediss://`.
- [ ] Test walidacji startupowej dla brakujacych/blednych env konczy sie czytelnym wyjatkiem.

### Manual Verification
- [ ] Ustawienie nowego zewnetrznego Redis przez `.env` umozliwia poprawny start i prace PMS.
- [ ] Brak fallbacku: przy blednej konfiguracji tryb docelowy nie przechodzi na alternatywne zrodlo.
- [ ] Bledy runtime Redis sa widoczne w loggerze aplikacji.
- [ ] Logi nie zawieraja jawnych sekretow (`password`, wrazliwe dane auth).
- [ ] Lokalny/testowy setup po aktualizacji envow nadal daje sie uruchomic.

## Related Information
- Wejscie z `ticket_001.md` (kontekst migracji Redis z Docker do zewnetrznej uslugi).
- Architektura repo: FastAPI + Celery + Redis (JobStore i task processing).

## Notes
- W razie wykrycia niezgodnosci nazw zmiennych env z istniejacym standardem repo, nalezy zachowac kompatybilnosc tam, gdzie to mozliwe.
- Jezeli wymagane sa migracje konfiguracji, maja zostac ujete w implementacji i dokumentacji finalnego stanu.
