"""
supabase_client.py — Worker's database client

Replaces the previous Supabase REST-API client (which used the
service_role_key, granting full admin access) with a lightweight
wrapper around a direct psycopg2 PostgreSQL connection using the
dedicated 'whub_worker' role.

The wrapper mimics the subset of the Supabase client API that the
worker uses:
    client.rpc(name, params).execute()
                                   — call a function
    client.table(name).select()    — build SELECT queries
    client.table(name).insert()    — build INSERT queries
    client.table(name).update()    — build UPDATE queries
           .eq(col, val)           — WHERE filter
           .order(col, desc=True)  — ORDER BY
           .limit(n)               — LIMIT
           .execute()              — run the query, return {data: [...]}
    client.storage.from_(bucket)   — Supabase Storage API
           .upload(path, data, opts)

The storage sub-client still uses the Supabase Storage REST API
(via the storage3 library) with the anon key and the service URL.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Optional

import psycopg2
import psycopg2.extras
from storage3 import create_client as create_storage_client
from storage3 import SyncStorageClient

from .config import settings

log = logging.getLogger("whub-cv-worker.db")

# ─────────────────────────────────────────────────────────────────────
#  Query builder
# ─────────────────────────────────────────────────────────────────────


class _QueryBuilder:
    """Lightweight query builder that mirrors supabase-py's chainable API.

    Builds raw SQL strings to avoid depending on psycopg2.sql.Composable
    (which requires a real connection for .as_string()).
    """

    def __init__(self, table_name: str, conn_provider):
        self._table = table_name
        self._conn_provider = conn_provider
        self._verb: str | None = None
        self._columns: str = "*"
        self._payload: dict | None = None
        self._filters: list[tuple[str, Any]] = []  # (col, value) for WHERE
        self._order_col: str | None = None
        self._order_desc: bool = False
        self._limit_val: int | None = None

    # ── Verb setters (chainable) ────────────────────────────────────

    def select(self, columns: str = "*") -> _QueryBuilder:
        self._verb = "select"
        self._columns = columns
        return self

    def insert(self, payload: dict) -> _QueryBuilder:
        self._verb = "insert"
        self._payload = payload
        return self

    def update(self, payload: dict) -> _QueryBuilder:
        self._verb = "update"
        self._payload = payload
        return self

    # ── Filter / clause chain ───────────────────────────────────────

    def eq(self, column: str, value: Any) -> _QueryBuilder:
        self._filters.append((column, value))
        return self

    def order(self, column: str, *, desc: bool = False) -> _QueryBuilder:
        self._order_col = column
        self._order_desc = desc
        return self

    def limit(self, n: int) -> _QueryBuilder:
        self._limit_val = n
        return self

    # ── SQL compilation ─────────────────────────────────────────────

    def _compile_and_params(self) -> tuple[str, list[Any]]:
        """Return (sql_string, params_list)."""
        verb = self._verb or "select"
        if verb == "select":
            return self._compile_select()
        elif verb == "insert":
            return self._compile_insert()
        elif verb == "update":
            return self._compile_update()
        else:
            raise ValueError(f"Unsupported verb: {verb}")

    def _quote_ident(self, name: str) -> str:
        """Quote an identifier safely for PostgreSQL."""
        # Simple quoting: double-quote and escape internal double-quotes
        return f'"{name.replace(chr(34), chr(34) + chr(34))}"'

    def _compile_select(self) -> tuple[str, list[Any]]:
        cols = self._columns.strip()
        parts = [f"SELECT {cols} FROM {self._quote_ident(self._table)}"]
        params: list[Any] = []

        if self._filters:
            clauses = []
            for col, val in self._filters:
                clauses.append(f"{self._quote_ident(col)} = %s")
                params.append(val)
            parts.append("WHERE " + " AND ".join(clauses))

        if self._order_col:
            direction = "DESC" if self._order_desc else "ASC"
            parts.append(
                f"ORDER BY {self._quote_ident(self._order_col)} {direction}"
            )

        if self._limit_val is not None:
            parts.append(f"LIMIT %s")
            params.append(self._limit_val)

        return " ".join(parts), params

    def _compile_insert(self) -> tuple[str, list[Any]]:
        if not self._payload:
            raise ValueError("INSERT requires a payload dict")

        cols = list(self._payload.keys())
        quoted_cols = ", ".join(self._quote_ident(c) for c in cols)
        placeholders = ", ".join(["%s"] * len(cols))

        values: list[Any] = []
        for c in cols:
            v = self._payload[c]
            if isinstance(v, (dict, list)):
                v = json.dumps(v, ensure_ascii=False, default=str)
            elif isinstance(v, datetime):
                v = v.isoformat()
            values.append(v)

        sql = (
            f"INSERT INTO {self._quote_ident(self._table)} "
            f"({quoted_cols}) VALUES ({placeholders}) RETURNING *"
        )
        return sql, values

    def _compile_update(self) -> tuple[str, list[Any]]:
        if not self._payload:
            raise ValueError("UPDATE requires a payload dict")

        set_clauses: list[str] = []
        values: list[Any] = []
        for col, val in self._payload.items():
            v = val
            if isinstance(v, (dict, list)):
                v = json.dumps(v, ensure_ascii=False, default=str)
            elif isinstance(v, datetime):
                v = v.isoformat()
            set_clauses.append(f"{self._quote_ident(col)} = %s")
            values.append(v)

        parts = [
            f"UPDATE {self._quote_ident(self._table)} "
            f"SET {', '.join(set_clauses)}"
        ]

        if self._filters:
            clauses = []
            for col, val in self._filters:
                clauses.append(f"{self._quote_ident(col)} = %s")
                values.append(val)
            parts.append("WHERE " + " AND ".join(clauses))

        parts.append("RETURNING *")
        return " ".join(parts), values

    # ── Execution ───────────────────────────────────────────────────

    def execute(self) -> SimpleNamespace:
        sql, params = self._compile_and_params()
        conn = self._conn_provider()
        log.debug("SQL: %s  params=%s", sql[:200], params)
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            conn.commit()
            rows = cur.fetchall()
            data = [dict(r) for r in rows] if rows else []
            return SimpleNamespace(data=data)


class _RpcCall:
    """Supabase-like RPC call builder backed by PostgreSQL."""

    def __init__(self, name: str, params: dict[str, Any], conn_provider):
        self._name = name
        self._params = params or {}
        self._conn_provider = conn_provider

    def execute(self) -> SimpleNamespace:
        """
        Call a PostgreSQL function (RPC).
        SELECT * FROM function_name(arg1 := val1, arg2 := val2)
        """
        params = self._params
        if params:
            arg_pairs = ", ".join(f"{k} := %s" for k in params)
            values = list(params.values())
        else:
            arg_pairs = ""
            values = []

        sql = f"SELECT * FROM {self._name}({arg_pairs})"
        log.debug("RPC: %s  params=%s", sql[:200], params)

        conn = self._conn_provider()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, values)
            conn.commit()
            rows = cur.fetchall()
            data = [dict(r) for r in rows] if rows else []
            return SimpleNamespace(data=data)


# ─────────────────────────────────────────────────────────────────────
#  Database client wrapper
# ─────────────────────────────────────────────────────────────────────


class _WorkerDatabaseClient:
    """
    Minimal Supabase-client-compatible wrapper backed by a direct
    psycopg2 connection to PostgreSQL.  Exposes only the methods
    that the worker actually uses: .rpc(), .table(), .storage.
    """

    def __init__(self, db_url: str, supabase_url: str = "", supabase_anon_key: str = ""):
        self.db_url = db_url
        self._conn: psycopg2.extensions.connection | None = None
        self._storage: SyncStorageClient | None = None

        # Initialise storage sub-client (for file uploads).
        # Uses anon key (public) — storage operations are protected
        # by RLS policies on storage.objects.
        self._supabase_url = supabase_url
        if supabase_url and supabase_anon_key:
            try:
                self._storage = create_storage_client(
                    url=f"{supabase_url}/storage/v1",
                    headers={
                        "apikey": supabase_anon_key,
                        "Authorization": f"Bearer {supabase_anon_key}",
                    },
                    is_async=False,
                )
                log.info(
                    "storage client initialised for %s", supabase_url
                )
            except Exception as exc:
                log.warning(
                    "storage client init failed (uploads will fail): %s",
                    exc,
                )

    # ── Connection management ───────────────────────────────────────

    @property
    def conn(self) -> psycopg2.extensions.connection:
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(self.db_url)
            self._conn.autocommit = False
            log.info("connected to postgresql via whub_worker role")
        return self._conn

    # ── Table query builder ─────────────────────────────────────────

    def table(self, name: str) -> _QueryBuilder:
        return _QueryBuilder(name, conn_provider=lambda: self.conn).select("*")

    # ── RPC (function calls) ────────────────────────────────────────

    def rpc(self, name: str, params: dict[str, Any]) -> _RpcCall:
        return _RpcCall(name, params, conn_provider=lambda: self.conn)

    # ── Storage (proxy to storage3) ─────────────────────────────────

    @property
    def storage(self) -> SyncStorageClient:
        if self._storage is None:
            raise RuntimeError(
                "Storage client not initialised. "
                "Set supabase_url and supabase_anon_key in config."
            )
        return self._storage


# ─────────────────────────────────────────────────────────────────────
#  Module-level client — used by main.py, storage.py, events.py
# ─────────────────────────────────────────────────────────────────────

if settings.worker_db_url:
    client = _WorkerDatabaseClient(
        db_url=settings.worker_db_url,
        supabase_url=settings.supabase_url,
        supabase_anon_key=settings.supabase_anon_key,
    )
    log.info(
        "worker database client initialised with dedicated role "
        "(no service_role_key)"
    )
else:
    raise RuntimeError(
        "WORKER_DB_URL is required. The worker must use the dedicated "
        "whub_worker database role; service_role_key fallback is disabled."
    )


__all__ = ["client", "_WorkerDatabaseClient"]