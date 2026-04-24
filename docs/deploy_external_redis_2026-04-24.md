# Deployment session: external Redis switch (2026-04-24)

## Goal
Switch running app on `feature/NN-23952-pms-obsluzyc-w-kodzie-auth-dla-redis` to external Redis and start services.

## Executed steps and commands
1. Stop app services and containers before branch/runtime changes:
   - `sudo systemctl stop qa-test-ml-api.service qa-test-ml-worker-gpu.service`
   - `sudo docker ps -q | xargs -r docker stop`

2. Update runtime env in `/home/dpo/qa-test-ml/.env`:
   - backup: `cp .env .env.backup.$(date +%Y%m%d_%H%M%S)`
   - set keys:
     - `JOB_STORE_BACKEND=redis`
     - `REDIS_URL=`
     - `REDIS_HOST=10.21.69.238`
     - `REDIS_PORT=6379`
     - `REDIS_DB=0`
     - `REDIS_USERNAME=qa-test-ml`
     - `REDIS_PASSWORD=<redacted>`
     - `REDIS_TLS=false`
     - `REDIS_PREFIX=qa-test-ml`
     - `CELERY_BROKER_URL=`
     - `CELERY_RESULT_BACKEND=`

3. Start services:
   - `sudo systemctl start qa-test-ml-api.service qa-test-ml-worker-gpu.service`

4. Validate service/health:
   - `systemctl is-active qa-test-ml-api.service qa-test-ml-worker-gpu.service`
   - `curl http://127.0.0.1:8080/health`
   - `journalctl -u qa-test-ml-api.service -n 80`

5. Redis ACL probe with app credentials (python redis client):
   - `PING` -> denied
   - `SET/GET/DEL` on `qa-test-ml:acl_probe` -> allowed

6. Stop services due startup failure:
   - `sudo systemctl stop qa-test-ml-api.service qa-test-ml-worker-gpu.service`

## Outcome
- API startup fails on feature branch because startup validation does `PING` and Redis ACL for user `qa-test-ml` blocks `PING`.
- Error seen in logs: `NoPermissionError: this user has no permissions to run the 'ping' command`.
- Key read/write appears allowed, but app remains down because fail-fast startup requires successful `PING`.

## Current status
- `qa-test-ml-api.service`: inactive
- `qa-test-ml-worker-gpu.service`: inactive
- `.env` is already prepared for external Redis credentials and prefix.

## Required fix on Redis side
Grant `PING` permission for ACL user `qa-test-ml` (or provide credentials for a user that can run `PING`).
Example ACL shape (to be applied by Redis admin, exact policy per security rules):
- include command category or command allowing ping (e.g. `+ping`)
- preserve key pattern constraints for `qa-test-ml:*`

## Follow-up: startup check mode rollout
After adding configurable startup check in code, the following runtime change was applied:

- `.env`: `REDIS_STARTUP_CHECK_MODE=rw`

Commands executed:

- `sudo systemctl restart qa-test-ml-api.service qa-test-ml-worker-gpu.service`
- `sudo systemctl is-active qa-test-ml-api.service qa-test-ml-worker-gpu.service`
- `curl -fsS http://127.0.0.1:8080/health`

Result:

- Services are `active`.
- API health is `status=ok`.
- `job_store.available=true` with external Redis ACL profile that does not allow `PING`.

