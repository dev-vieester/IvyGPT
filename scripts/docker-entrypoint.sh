#!/usr/bin/env sh
set -e

python - <<'PY'
import time

from psycopg import OperationalError, connect
from redis import Redis
from redis.exceptions import RedisError

from ivy_gpt.config import settings

for attempt in range(1, 31):
    try:
        with connect(settings.postgres_checkpoint_url, connect_timeout=3):
            break
    except OperationalError:
        if attempt == 30:
            raise
        time.sleep(2)

redis_client = Redis.from_url(settings.redis_url)

for attempt in range(1, 31):
    try:
        redis_client.ping()
        break
    except RedisError:
        if attempt == 30:
            raise
        time.sleep(2)
PY

if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
    alembic upgrade head
fi

exec "$@"
