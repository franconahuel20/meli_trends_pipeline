"""Dagster resources for PostgreSQL, MinIO (S3) and the Mercado Libre API."""

from __future__ import annotations

import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

import boto3
import psycopg2
import requests
from botocore.config import Config
from botocore.exceptions import ClientError
from dagster import ConfigurableResource, Failure
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_PLACEHOLDER_MARKERS = ("REPLACE_WITH", "your_real", "changeme")


class PostgresResource(ConfigurableResource):
    host: str
    port: int = 5432
    database: str
    user: str
    password: str

    @contextmanager
    def connection(self) -> Iterator[psycopg2.extensions.connection]:
        """Yield a connection; the caller commits. Uncommitted work is rolled back."""
        conn = psycopg2.connect(
            host=self.host,
            port=self.port,
            dbname=self.database,
            user=self.user,
            password=self.password,
            connect_timeout=15,
            application_name="meli_trends_pipeline",
        )
        try:
            yield conn
        finally:
            conn.close()


class MinioResource(ConfigurableResource):
    endpoint_url: str
    access_key: str
    secret_key: str
    bucket: str
    region: str = "us-east-1"

    def _client(self):
        return boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                retries={"max_attempts": 5, "mode": "standard"},
            ),
        )

    def ensure_bucket(self) -> None:
        client = self._client()
        try:
            client.head_bucket(Bucket=self.bucket)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code not in {"404", "NoSuchBucket", "NotFound"}:
                raise
            client.create_bucket(Bucket=self.bucket)

    def put_bytes(self, key: str, body: bytes, content_type: str) -> str:
        self.ensure_bucket()
        self._client().put_object(Bucket=self.bucket, Key=key, Body=body, ContentType=content_type)
        return f"s3://{self.bucket}/{key}"

    def get_bytes(self, key: str) -> bytes:
        response = self._client().get_object(Bucket=self.bucket, Key=key)
        return response["Body"].read()

    def list_keys(self, prefix: str) -> list[str]:
        self.ensure_bucket()
        paginator = self._client().get_paginator("list_objects_v2")
        return [
            obj["Key"]
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix)
            for obj in page.get("Contents", [])
        ]


@dataclass(frozen=True)
class TrendsResponse:
    status_code: int
    items: list[dict]
    error: str | None = None


class MercadoLibreClient:
    """Thread-safe client: one HTTP session per thread, one shared access token."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        grant_type: str,
        base_url: str,
        timeout_seconds: float,
        max_retries: int,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._grant_type = grant_type
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._retry = Retry(
            total=max_retries,
            connect=max_retries,
            read=max_retries,
            status=max_retries,
            backoff_factor=1.0,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "POST"}),
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        self._local = threading.local()
        self._token: str | None = None
        self._token_lock = threading.Lock()

    def _session(self) -> requests.Session:
        session = getattr(self._local, "session", None)
        if session is None:
            session = requests.Session()
            adapter = HTTPAdapter(max_retries=self._retry)
            session.mount("https://", adapter)
            session.mount("http://", adapter)
            session.headers.update({"Accept": "application/json"})
            self._local.session = session
        return session

    def access_token(self, refresh: bool = False) -> str:
        with self._token_lock:
            if self._token is None or refresh:
                response = self._session().post(
                    f"{self._base_url}/oauth/token",
                    data={
                        "grant_type": self._grant_type,
                        "client_id": self._client_id,
                        "client_secret": self._client_secret,
                    },
                    timeout=self._timeout,
                )
                if response.status_code != 200:
                    raise Failure(
                        description=(
                            "Mercado Libre rejected the credentials "
                            f"(HTTP {response.status_code}): {response.text[:300]}. "
                            "Check ML_CLIENT_ID, ML_CLIENT_SECRET and ML_GRANT_TYPE in .env."
                        )
                    )
                token = response.json().get("access_token")
                if not token:
                    raise Failure(description="Mercado Libre token response has no access_token.")
                self._token = token
            return self._token

    def trends(self, site_id: str, category_id: str) -> TrendsResponse:
        url = f"{self._base_url}/trends/{site_id}/{category_id}"
        token = self.access_token()
        for attempt in range(2):
            try:
                response = self._session().get(
                    url, headers={"Authorization": f"Bearer {token}"}, timeout=self._timeout
                )
            except requests.RequestException as exc:
                return TrendsResponse(status_code=0, items=[], error=f"{type(exc).__name__}: {exc}")
            if response.status_code == 401 and attempt == 0:
                token = self.access_token(refresh=True)
                continue
            break
        if response.status_code == 404:
            return TrendsResponse(status_code=404, items=[])
        if response.status_code != 200:
            return TrendsResponse(
                status_code=response.status_code, items=[], error=response.text[:300]
            )
        try:
            payload = response.json()
        except ValueError:
            return TrendsResponse(status_code=200, items=[], error="response is not JSON")
        if not isinstance(payload, list):
            return TrendsResponse(status_code=200, items=[], error=f"unexpected payload: {str(payload)[:200]}")
        return TrendsResponse(status_code=200, items=[i for i in payload if isinstance(i, dict)])


class MercadoLibreResource(ConfigurableResource):
    client_id: str
    client_secret: str
    grant_type: str = "client_credentials"
    base_url: str = "https://api.mercadolibre.com"
    timeout_seconds: float = 30.0
    max_retries: int = 5

    def create_client(self) -> MercadoLibreClient:
        for name, value in (("ML_CLIENT_ID", self.client_id), ("ML_CLIENT_SECRET", self.client_secret)):
            if not value or any(marker.lower() in value.lower() for marker in _PLACEHOLDER_MARKERS):
                raise Failure(
                    description=(
                        f"{name} is not configured. Set your Mercado Libre application "
                        "credentials in .env and run `docker compose up -d` again."
                    )
                )
        return MercadoLibreClient(
            client_id=self.client_id,
            client_secret=self.client_secret,
            grant_type=self.grant_type,
            base_url=self.base_url,
            timeout_seconds=self.timeout_seconds,
            max_retries=self.max_retries,
        )
