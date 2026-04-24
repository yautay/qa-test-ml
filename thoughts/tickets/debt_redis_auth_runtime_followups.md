---
type: debt
priority: high
created: 2026-04-24T12:30:00Z
status: implemented
tags: [redis, fastapi, startup, lifespan, integration-tests, job-store, celery]
keywords: [JobStore, lifespan, app.on_event, startup validation, redis auth, REDIS_URL, REDIS_HOST, REDIS_USERNAME, REDIS_PASSWORD, health, celery, integration test, docker compose]
patterns: [FastAPI lifespan migration, startup dependency initialization, fail-fast validation, auth-enabled Redis integration testing, negative auth test coverage, pytest markers for integration tests, health contract behavior, compose-based local verification]
---

# DEBT-001: Domkniecie follow-upow po review Redis auth runtime

## Description
Wdrozyc zalecenia z `thoughts/reviews/feature_redis_external_service_auth_review.md` po wdrozeniu wsparcia dla zewnetrznego Redis z auth. Zakres obejmuje dodanie zautomatyzowanego testu integracyjnego dla realnego Redis z uwierzytelnianiem, przeniesienie tworzenia `JobStore` do sciezki `lifespan/startup`, migracje z `@app.on_event("startup")` do FastAPI lifespan oraz aktualizacje dokumentacji i lokalnych instrukcji uruchomienia.

## Context
Review potwierdzil, ze podstawowe wdrozenie Redis auth/TLS zostalo zrealizowane, ale pozostaly trzy follow-upy: brak testu integracyjnego z prawdziwym Redis auth, tworzenie `JobStore` nadal moze failowac juz podczas `create_app()`, oraz standardowy startup API korzysta z deprecowanego `@app.on_event("startup")`. Ticket ma domknac ten dlug techniczny i usunac warningi deprecacyjne z typowego uruchomienia testow.

## Requirements
Ticket pozostaje pojedynczy, ale obejmuje powiazane zmiany w API, `JobStore`, testach integracyjnych i dokumentacji. Zakres moze objac analogiczne poprawki startup/lifespan poza `app/main.py`, jezeli beda potrzebne do zachowania spojnosc implementacji, natomiast dodatkowe znaleziska poza bezposrednim przeplywem Redis/API nalezy odnotowac jako follow-up.

### Functional Requirements
- Dodac zautomatyzowany test integracyjny dla realnego Redis z auth obejmujacy tryb `REDIS_URL`.
- Dodac zautomatyzowany test integracyjny dla realnego Redis z auth obejmujacy tryb split-vars: `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, `REDIS_USERNAME`, `REDIS_PASSWORD`.
- Test integracyjny ma obejmowac pelny przeplyw: start aplikacji, `/health`, utworzenie joba i odczyt wyniku.
- Dodac zautomatyzowany scenariusz negatywny z blednymi danymi logowania, potwierdzajacy fail-fast oraz brak wycieku hasla w logach/komunikatach.
- Przeniesc tworzenie `JobStore` tak, aby bledy kontraktu Redis i problemy inicjalizacji wystepowaly w sciezce `lifespan/startup`, a nie juz przy `create_app()`.
- Zastapic `@app.on_event("startup")` handlerami FastAPI lifespan.
- Sprawdzic analogiczne wzorce startup/lifespan w repo i, jesli to konieczne dla spojnosci lub eliminacji warningow, uwzglednic minimalne powiazane zmiany.
- Zachowac lub uproscic semantyke `/health`; dopuszczalna jest niewielka zmiana zachowania lub komunikatow, jesli upraszcza implementacje i pozostaje kontrolowana.
- Zaktualizowac dokumentacje istniejaca lub dodac nowa instrukcje opisujaca lokalne uruchamianie testow integracyjnych.

### Non-Functional Requirements
- Test integracyjny nie musi byc wpiety do CI; wystarczy lokalna, powtarzalna sciezka uruchomienia.
- Dopuszczalne sa oba lokalne warianty uruchomienia testow: przez `docker compose` i przez inny opisany, powtarzalny mechanizm lokalny.
- Testy integracyjne powinny miec osobny marker/kategorie, aby nie mieszaly sie z domyslnym `pytest -q`.
- Standardowy przebieg testow w obszarze objetych zmian nie powinien emitowac warningow deprecacyjnych FastAPI zwiazanych z `@app.on_event(...)`.
- Logi i komunikaty bledow musza nadal maskowac dane wrazliwe Redis auth.
- Lokalna kompatybilnosc `docker compose` pozostaje wymagana jako walidacja pomocnicza, ale nie jako glowny mechanizm implementacyjny.

## Current State
Obecne wdrozenie zapewnia konfiguracje Redis auth oraz startup validation, ale brak mu testu end-to-end z realnym Redis auth. `JobStore` jest nadal tworzony przed startup hookiem, przez co fail-fast moze zajsc podczas `create_app()`. API nadal uzywa `@app.on_event("startup")`, co powoduje warningi deprecacyjne w `pytest`.

## Desired State
Repo zawiera lokalnie uruchamialny, zautomatyzowany test integracyjny dla Redis auth w obu trybach konfiguracji, `JobStore` inicjalizuje sie w `lifespan/startup`, startup API nie korzysta juz z deprecowanego `@app.on_event(...)`, warningi znikaja ze standardowego przebiegu testow, a dokumentacja opisuje jak odtworzyc i zweryfikowac scenariusze lokalnie.

## Research Context
Research powinien potwierdzic rzeczywiste punkty inicjalizacji `JobStore` i zaleznosci startupowych, aktualny ksztalt kontraktu `/health`, istniejace wzorce testow integracyjnych i fixture'ow, sposob uruchamiania lokalnych uslug pomocniczych oraz ewentualne inne uzycia `@app.on_event(...)` w repo.

### Keywords to Search
- `JobStore` - miejsce tworzenia i zycia zaleznosci Redis.
- `create_app` - punkt, w ktorym obecnie moze dochodzic do przedwczesnej inicjalizacji.
- `lifespan` - docelowy wzorzec startup/shutdown w FastAPI.
- `@app.on_event` - wszystkie deprecowane handlery do przegladu.
- `startup` - logika fail-fast i zaleznosci inicjalizowane przy starcie.
- `REDIS_URL` - sciezka konfiguracji URL-based dla auth.
- `REDIS_HOST` - sciezka konfiguracji split-vars.
- `REDIS_USERNAME` - auth contract dla Redis.
- `REDIS_PASSWORD` - maskowanie sekretow i scenariusz negatywny.
- `/health` - kontrakt i zachowanie po zmianie inicjalizacji.
- `pytest.mark` - wzorce wydzielenia testow integracyjnych.
- `docker-compose` - lokalne uruchamianie zaleznosci testowych.
- `Celery` - analogiczne wzorce startupowe, jesli beda wymagaly korekty.

### Patterns to Investigate
- Migracja startup hooks FastAPI do lifespan.
- Inicjalizacja zaleznosci infrastrukturalnych dopiero podczas startup, a nie podczas konstrukcji aplikacji.
- Wzorce integracyjnych testow z realnym serwisem infrastrukturalnym i izolacja przez markery.
- Automatyzacja scenariuszy negatywnych auth bez wycieku sekretow do asercji/logow.
- Zachowanie kontraktu `/health` przy leniwej lub startupowej inicjalizacji zaleznosci.
- Lokalne instrukcje developerskie dla testow wymagajacych kontenerow lub zewnetrznych serwisow.

### Key Decisions Made
- Ticket typu `debt` i priorytet `high` - domyka istotne zaleglosci po review.
- Jeden wspolny ticket obejmuje wszystkie trzy rekomendacje z review.
- Test integracyjny ma pokrywac oba tryby konfiguracji auth: `REDIS_URL` i split-vars.
- Zakres testu integracyjnego obejmuje pelny flow, nie tylko startup i `/health`.
- Scenariusz negatywny z blednymi credentialami ma byc zautomatyzowany.
- `JobStore` musi zostac przeniesiony do `lifespan/startup`; to wymog twardy.
- Migracja z `@app.on_event("startup")` do lifespan jest wymagana i ma usunac warningi deprecacyjne ze standardowych testow.
- Dopuszczalne sa minimalne zmiany analogicznych wzorcow w repo, jesli sa potrzebne do spojnosci; dalsze znaleziska maja trafic do follow-upu.
- Niewielka zmiana semantyki `/health` jest dopuszczalna, jesli upraszcza implementacje.
- Dokumentacja ma zostac zaktualizowana; mozna dodac nowy dokument, jesli obecne README nie wystarcza.
- Test integracyjny pozostaje lokalny i nie wymaga wdrozenia w CI w ramach tego ticketu.
- TLS/`rediss://`, CI wiring oraz wieksze zmiany kontraktu API sa jawnie out of scope.

## Success Criteria
Ticket jest kompletny, gdy lokalnie mozna uruchomic zautomatyzowane testy integracyjne dla Redis auth w obu trybach konfiguracji, scenariusz negatywny jest objety automatyzacja, `JobStore` tworzy sie w `lifespan/startup`, standardowe testy nie emituja juz deprecacji FastAPI zwiazanych z `@app.on_event(...)`, a dokumentacja opisuje jak odtworzyc i zweryfikowac caly przeplyw.

### Automated Verification
- [ ] `pytest -q`
- [ ] `ruff check .`
- [ ] `black --check .`
- [ ] Dedykowany test integracyjny/marker dla Redis auth w trybie `REDIS_URL` przechodzi lokalnie.
- [ ] Dedykowany test integracyjny/marker dla Redis auth w trybie split-vars przechodzi lokalnie.
- [ ] Zautomatyzowany scenariusz negatywny z blednymi credentialami przechodzi i potwierdza fail-fast bez wycieku hasla.
- [ ] Standardowy przebieg testow nie emituje deprecacji FastAPI zwiazanych z `@app.on_event(...)`.

### Manual Verification
- [ ] Lokalnie da sie uruchomic Redis z auth do testow jednym z opisanych sposobow.
- [ ] `/health` raportuje oczekiwany stan po zmianie inicjalizacji `JobStore`.
- [ ] Pelny flow utworzenia i odczytu joba dziala przy auth Redis w obu trybach konfiguracji.
- [ ] Przy blednych danych logowania aplikacja nie zaczyna obslugiwac ruchu.
- [ ] Logi nie ujawniaja `REDIS_PASSWORD` ani innych wrazliwych danych.
- [ ] Lokalna kompatybilnosc `docker compose` pozostaje zachowana.

## Related Information
- `thoughts/reviews/feature_redis_external_service_auth_review.md` - zrodlo zaleceń i manualnych scenariuszy weryfikacyjnych.
- `thoughts/tickets/feature_redis_external_service_auth.md` - ticket bazowy dla pierwotnego wdrozenia Redis auth/TLS.
- `thoughts/plans/feature_redis_external_service_auth_implementation.md` - plan wdrozenia poprzedniego etapu.

## Notes
- Out of scope: TLS/`rediss://`, wdrozenie testu integracyjnego do CI, oraz wieksze zmiany kontraktu API poza niezbedna, kontrolowana korekta zachowania `/health`.
- Jesli podczas researchu zostana znalezione inne uzycia `@app.on_event(...)` niezwiazane bezposrednio z przeplywem Redis/API, nalezy odnotowac je jako follow-up zamiast rozszerzac ten ticket.
