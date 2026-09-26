#!/usr/bin/env sh
set -e

python - <<'PY'
import time

from psycopg import OperationalError, connect

from ivy_gpt.config import settings

dsn = settings.postgres_checkpoint_url

for attempt in range(1, 31):
    try:
        with connect(dsn, connect_timeout=3):
            break
    except OperationalError:
        if attempt == 30:
            raise
        time.sleep(2)
PY

if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
    alembic upgrade head
fi

exec "$@"
