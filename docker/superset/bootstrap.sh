#!/usr/bin/env bash
# Initializes Superset (idempotent), registers the analytics database, imports the
# versioned dashboards when they are missing, then serves.
set -euo pipefail

superset db upgrade

superset fab create-admin \
  --username "${SUPERSET_ADMIN_USERNAME}" \
  --password "${SUPERSET_ADMIN_PASSWORD}" \
  --firstname Superset \
  --lastname Admin \
  --email admin@example.com || true

superset init

# A provisioning problem must not keep Superset down: report it loudly and serve anyway.
python /app/docker/meli-provision.py \
  || echo "ERROR: dashboard provisioning failed; see the messages above. Superset starts without it."

exec /usr/bin/run-server.sh
