# Integration Testing Guide

This guide covers opt-in integration tests that require external services.

## Redis Auth Integration Suite

The Redis auth suite lives in `tests/test_redis_auth_integration.py` and is marked with `redis_integration`.

- Default `pytest -q` remains the standard fast path.
- Redis integration tests are opt-in and require explicit environment setup.

Required env vars:

```bash
export RUN_REDIS_INTEGRATION=1
export PMS_REDIS_AUTH_URL='redis://:pms-secret@127.0.0.1:6380/0'
```

`PMS_REDIS_AUTH_URL` must point to an auth-enabled Redis instance.

## Option 1: Docker Compose (recommended)

Prepare runtime env file if needed:

```bash
cp tools/runtime/.env.example tools/runtime/.env
```

Start local auth-enabled Redis:

```bash
docker compose -f tools/runtime/docker-compose.yml --profile redis-auth up -d redis-auth
```

Run integration tests (marker/file scoped):

```bash
pytest -q -m redis_integration tests/test_redis_auth_integration.py
```

Or run scenarios individually:

```bash
pytest -q -m redis_integration tests/test_redis_auth_integration.py -k url
pytest -q -m redis_integration tests/test_redis_auth_integration.py -k split
pytest -q -m redis_integration tests/test_redis_auth_integration.py -k invalid
```

Tear down:

```bash
docker compose -f tools/runtime/docker-compose.yml --profile redis-auth down
```

## Option 2: Standalone Local Redis (repeatable alternative)

Run a local auth-enabled Redis container directly:

```bash
docker run --rm -d --name pms-redis-auth -p 6380:6379 redis:7.2-alpine \
  redis-server --appendonly yes --requirepass pms-secret
```

Use the same test commands as above, then stop the container:

```bash
docker stop pms-redis-auth
```

## Expected Behavior

- URL mode and split-vars mode both pass full API flow (`/health`, create job, read job back).
- Invalid credentials fail during app startup.
- Failure output must not expose raw Redis password values.
