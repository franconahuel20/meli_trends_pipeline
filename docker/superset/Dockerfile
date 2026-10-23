FROM apache/superset:4.1.1

USER root
RUN pip install --no-cache-dir psycopg2-binary==2.9.11
COPY docker/superset/bootstrap.sh /app/docker/meli-bootstrap.sh
# Strip Windows line endings in case the repository was checked out with CRLF.
RUN sed -i 's/\r$//' /app/docker/meli-bootstrap.sh && chmod 0755 /app/docker/meli-bootstrap.sh
USER superset

CMD ["/app/docker/meli-bootstrap.sh"]
