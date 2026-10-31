FROM apache/superset:4.1.1

USER root
RUN pip install --no-cache-dir psycopg2-binary==2.9.11
COPY docker/superset/superset_config.py /app/pythonpath/superset_config.py
COPY docker/superset/bootstrap.sh /app/docker/meli-bootstrap.sh
COPY docker/superset/provision.py /app/docker/meli-provision.py
# Dashboards as code: imported at start-up when missing (superset/build_dashboard.py).
COPY superset/dashboard /app/meli_dashboard
# Strip Windows line endings in case the repository was checked out with CRLF.
RUN sed -i 's/\r$//' /app/docker/meli-bootstrap.sh && chmod 0755 /app/docker/meli-bootstrap.sh \
    && mkdir -p /app/superset_home/cache && chown -R superset:superset /app/superset_home
USER superset

CMD ["/app/docker/meli-bootstrap.sh"]
