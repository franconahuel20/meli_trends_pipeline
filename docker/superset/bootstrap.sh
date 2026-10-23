#!/usr/bin/env bash
# Initializes Superset (idempotent) and registers the analytics database, then serves.
set -euo pipefail

superset db upgrade

superset fab create-admin \
  --username "${SUPERSET_ADMIN_USERNAME}" \
  --password "${SUPERSET_ADMIN_PASSWORD}" \
  --firstname Superset \
  --lastname Admin \
  --email admin@example.com || true

superset init

# Register the PostgreSQL warehouse so datasets can be created right away.
ANALYTICS_URI="$(python - <<'PY'
import os
from urllib.parse import quote
print(
    "postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}".format(
        user=quote(os.environ["ANALYTICS_DB_USER"], safe=""),
        password=quote(os.environ["ANALYTICS_DB_PASSWORD"], safe=""),
        host=os.environ["ANALYTICS_DB_HOST"],
        port=os.environ["ANALYTICS_DB_PORT"],
        db=os.environ["ANALYTICS_DB_NAME"],
    )
)
PY
)"
superset set-database-uri --database_name "${ANALYTICS_DB_DISPLAY_NAME}" --uri "${ANALYTICS_URI}" \
  || echo "WARNING: could not register the analytics database; add it from the Superset UI."

exec /usr/bin/run-server.sh
