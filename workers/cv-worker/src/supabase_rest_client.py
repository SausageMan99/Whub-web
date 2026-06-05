import logging
import json
import urllib3
from types import SimpleNamespace
from typing import Any, Optional
from .config import settings

log = logging.getLogger(__name__)

RESP_API_BASE = settings.supabase_url + "/rest/v1"
_http = urllib3.PoolManager()

# Use service_role_key for database operations (bypasses RLS).
# The anon key is used only for storage operations.
_svc_key = settings.supabase_anon_key  # fallback if service key not available
if settings.supabase_service_role_key:
    _svc_key = settings.supabase_service_role_key

_headers = {
    "apikey": _svc_key,
    "Authorization": f"Bearer {_svc_key}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}


class _RESTQueryBuilder:
    """
    REST-based replacement for _QueryBuilder (psycopg2).
    Builds PostgREST queries and executes them via HTTP.
    """

    def __init__(self, table_name: str):
        self._table = table_name
        self._cols: str = "*"
        self._filters: list[tuple[str, str, Any]] = []
        self._order_col: str | None = None
        self._order_desc: bool = False
        self._limit_val: int | None = None
        self._insert_payload: dict | None = None
        self._update_payload: dict | None = None

    def select(self, columns: str = "*"):
        self._cols = columns
        return self

    def insert(self, payload: dict):
        self._insert_payload = payload
        return self

    def update(self, payload: dict):
        self._update_payload = payload
        return self

    def eq(self, column: str, value: Any):
        self._filters.append(("eq", column, value))
        return self

    def order(self, column: str, *, desc: bool = False):
        self._order_col = column
        self._order_desc = desc
        return self

    def limit(self, n: int):
        self._limit_val = n
        return self

    def execute(self) -> SimpleNamespace:
        method = "GET"
        url = f"{RESP_API_BASE}/{self._table}?select={self._cols}"

        if self._insert_payload:
            method = "POST"
            body = json.dumps(self._insert_payload).encode()
            r = _http.request(method, url, body=body, headers={**_headers, "Prefer": "return=representation"})
        elif self._update_payload:
            method = "PATCH"
            body = json.dumps(self._update_payload).encode()
            for ftype, col, val in self._filters:
                url += f"&{col}={ftype}.{val}" if "?" in url else f"?{col}={ftype}.{val}"
            r = _http.request(method, url, body=body, headers={**_headers, "Prefer": "return=representation"})
        else:
            # SELECT
            for ftype, col, val in self._filters:
                if isinstance(val, str):
                    url += f"&{col}={ftype}.{val}"
                else:
                    url += f"&{col}={ftype}.{val}"
            if self._order_col:
                direction = "desc" if self._order_desc else "asc"
                url += f"&order={self._order_col}.{direction}"
            if self._limit_val:
                url += f"&limit={self._limit_val}"
            r = _http.request(method, url, headers={**_headers})

        if r.status >= 400:
            log.warning("REST query failed (%s %s): %s", method, url[:200], r.data.decode()[:200])
            return SimpleNamespace(data=[])

        data = json.loads(r.data) if r.data else []
        return SimpleNamespace(data=data)


class _RESTRpcCall:
    """REST-based RPC call via POST /rest/v1/rpc/{name}"""

    def __init__(self, name: str, params: dict[str, Any]):
        self._name = name
        self._params = params

    def execute(self) -> SimpleNamespace:
        url = f"{RESP_API_BASE}/rpc/{self._name}"
        body = json.dumps(self._params).encode()
        r = _http.request("POST", url, body=body, headers=_headers)

        if r.status >= 400:
            log.warning("RPC %s failed (%d): %s", self._name, r.status, r.data.decode()[:200])
            return SimpleNamespace(data=[])

        try:
            data = json.loads(r.data) if r.data else []
        except json.JSONDecodeError:
            # scalar return (e.g. boolean, string)
            data = [{"result": r.data.decode()}] if r.data else []
        return SimpleNamespace(data=data)


class _RESTDatabaseClient:
    """
    REST API-based database client. Replaces the psycopg2-based
    _WorkerDatabaseClient when worker_database_url is not available.
    """

    def __init__(self, supabase_url: str = "", supabase_anon_key: str = ""):
        self._storage = None
        self._supabase_url = supabase_url

        # Init storage client if we have the URL
        if supabase_url and supabase_anon_key:
            try:
                from storage3 import create_client as create_storage_client
                self._storage = create_storage_client(
                    url=f"{supabase_url}/storage/v1",
                    headers={
                        "apikey": supabase_anon_key,
                        "Authorization": f"Bearer {supabase_anon_key}",
                    },
                    is_async=False,
                )
                log.info("REST client: storage initialised for %s", supabase_url)
            except Exception as exc:
                log.warning("REST client: storage init failed: %s", exc)

    def table(self, name: str) -> _RESTQueryBuilder:
        return _RESTQueryBuilder(name)

    def rpc(self, name: str, params: dict[str, Any]) -> _RESTRpcCall:
        return _RESTRpcCall(name, params)

    @property
    def storage(self):
        if self._storage is None:
            raise RuntimeError("Storage client not initialised")
        return self._storage


# ── Module-level client ──

if settings.supabase_url and settings.supabase_anon_key:
    client = _RESTDatabaseClient(
        supabase_url=settings.supabase_url,
        supabase_anon_key=settings.supabase_anon_key,
    )
    log.info(
        "worker REST database client initialised (no direct psycopg2 connection)"
    )
else:
    raise RuntimeError(
        "SUPABASE_URL and SUPABASE_ANON_KEY are required in REST mode"
    )

__all__ = ["client", "_RESTDatabaseClient"]
