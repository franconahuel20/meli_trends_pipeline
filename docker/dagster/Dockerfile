FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DAGSTER_HOME=/opt/dagster/dagster_home \
    DBT_PROFILES_DIR=/opt/dagster/app/dbt/profiles \
    DBT_SEND_ANONYMOUS_USAGE_STATS=false \
    PYTHONPATH=/opt/dagster/app

COPY docker/dagster/requirements.txt docker/dagster/constraints.txt /tmp/
RUN pip install --requirement /tmp/requirements.txt --constraint /tmp/constraints.txt

RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin dagster \
    && mkdir -p /opt/dagster/app "${DAGSTER_HOME}/storage"

WORKDIR /opt/dagster/app
COPY docker/dagster/dagster.yaml docker/dagster/workspace.yaml ${DAGSTER_HOME}/
COPY pyproject.toml ./
COPY meli_trends_pipeline ./meli_trends_pipeline
COPY dbt ./dbt
COPY data/input ./data/input
COPY tests ./tests
RUN chown -R dagster:dagster /opt/dagster

USER dagster
# Ship the dbt manifest with the image and fail the build if the code location cannot load.
RUN dbt parse --project-dir dbt --profiles-dir dbt/profiles --quiet \
    && python -c "import meli_trends_pipeline.definitions"

EXPOSE 3000 4000
