- Przeniesienie cache nonce HMAC z pamieci procesu do Redis (`SET NX EX`).
- Gwarancja ochrony replay na wielu instancjach API.
- Zastapienie limitera in-memory wersja rozproszona (algorytm fixed/sliding window).
- Spojne limity niezaleznie od liczby instancji API.
- Progi bezpieczenstwa dla liczby jobow `queued/running`.
- Odrzucanie nowych zadan (`429` lub `503`) przy przeciazeniu.
- Twardsze timeouty i retry policy dla Redis/Celery.
- Rozszerzone metryki i alerty (rate-limited/rejected/error burst).
- Wymuszenie TLS i auth dla Redis/Celery (tam gdzie wspierane).
- Przeglad rotacji sekretow (`HMAC_SECRET`, tokeny API sinka).

1. Nonce HMAC do Redis
2. Rozproszony rate limiter w Redis
3. Backpressure na kolejki
4. Runtime timeouts/retry + alerting
5. Finalny przeglad security transport/sekrety
