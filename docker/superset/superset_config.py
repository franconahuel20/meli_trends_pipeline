"""Superset settings for the MeLi Trends platform (loaded from /app/pythonpath).

Superset's own metadata (users, datasets, charts, dashboards) lives in the dedicated
PostgreSQL service `superset-db`, on the named volume `superset_db_data`, so it survives
container restarts, image rebuilds and reboots. The default SQLite file is not used: it
is not safe for several web threads and can be corrupted by an abrupt shutdown.
"""

import os
from urllib.parse import quote

SECRET_KEY = os.environ["SUPERSET_SECRET_KEY"]

SQLALCHEMY_DATABASE_URI = "postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}".format(
    user=quote(os.environ.get("SUPERSET_DB_USER", "superset"), safe=""),
    password=quote(os.environ.get("SUPERSET_DB_PASSWORD", "superset"), safe=""),
    host=os.environ.get("SUPERSET_DB_HOST", "superset-db"),
    port=os.environ.get("SUPERSET_DB_PORT", "5432"),
    db=os.environ.get("SUPERSET_DB_NAME", "superset"),
)
SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

FEATURE_FLAGS = {
    # Dashboard filters on top of the page, like the Revenue Research report.
    "HORIZONTAL_FILTER_BAR": True,
}

# Dashboard filter state and explore drafts are kept on the superset_home volume, shared by
# every web worker and preserved across restarts.
_CACHE_DIR = "/app/superset_home/cache"
FILTER_STATE_CACHE_CONFIG = {
    "CACHE_TYPE": "FileSystemCache",
    "CACHE_DIR": f"{_CACHE_DIR}/filter_state",
    "CACHE_DEFAULT_TIMEOUT": 90 * 24 * 3600,
    "CACHE_THRESHOLD": 0,
}
EXPLORE_FORM_DATA_CACHE_CONFIG = {
    "CACHE_TYPE": "FileSystemCache",
    "CACHE_DIR": f"{_CACHE_DIR}/explore_form_data",
    "CACHE_DEFAULT_TIMEOUT": 7 * 24 * 3600,
    "CACHE_THRESHOLD": 0,
}

ROW_LIMIT = 50000
