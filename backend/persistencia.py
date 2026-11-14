"""Persistencia opcional de SQLite en un Postgres externo.

El servidor gratuito de Render elimina archivos en cada suspensión o reinicio.
Cuando se configura DATABASE_URL, cada transacción de escritura confirmada
se copia a una tabla de Postgres y la base se restaura al arrancar.

Es una solución sencilla para la demostración; NO reemplaza una migración
a Postgres nativo para un sistema real o con carga elevada.
"""
from __future__ import annotations
import importlib
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

DB_URL = os.environ.get("DATABASE_URL", "").strip()
_SYNC_LOCK = threading.RLock()
_PG = None


def enabled() -> bool:
    return bool(DB_URL)


def postgres():
    """Cargar psycopg cuando hay una URL; Render antiguo no instala dependencias."""
    global _PG
    if _PG is not None:
        return _PG
    if not enabled():
        raise RuntimeError("DATABASE_URL no configurada.")
    try:
        _PG = importlib.import_module("psycopg")
    except ImportError:
        # El buildCommand del servicio existente no instala requirements.txt.
        # Se instala en el entorno Python actual al iniciar, si hace falta.
        subprocess.run([
            sys.executable, "-m", "pip", "install",
            "--disable-pip-version-check", "--quiet", "psycopg[binary]>=3.2,<4"
        ], check=True, timeout=120)
        importlib.invalidate_caches()
        _PG = importlib.import_module("psycopg")
    return _PG


def prepare_remote():
    pg = postgres()
    with pg.connect(DB_URL, connect_timeout=20) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS medicuida_sqlite_snapshots (
                snapshot_id SMALLINT PRIMARY KEY CHECK(snapshot_id=1),
                database_bytes BYTEA NOT NULL,
                saved_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)


def restore_database(path: Path) -> bool:
    """Restaurar antes de abrir SQLite. Falla si Postgres no está disponible."""
    if not enabled():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with _SYNC_LOCK:
        prepare_remote()
        pg = postgres()
        with pg.connect(DB_URL, connect_timeout=20) as conn:
            row = conn.execute(
                "SELECT database_bytes FROM medicuida_sqlite_snapshots WHERE snapshot_id=1"
            ).fetchone()
        if not row:
            print("Base Postgres nueva, sin copia SQLite previa.", flush=True)
            return False
        blob = bytes(row[0])
        if not blob.startswith(b"SQLite format 3"):
            raise RuntimeError("La copia guardada no es una base SQLite válida.")
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".restore-", suffix=".sqlite3", delete=False) as tmp:
            temporary = Path(tmp.name)
            tmp.write(blob)
            tmp.flush()
            os.fsync(tmp.fileno())
        try:
            with sqlite3.connect(temporary) as conn:
                valid = conn.execute("PRAGMA integrity_check").fetchone()
                if not valid or valid[0] != "ok":
                    raise RuntimeError("La copia de SQLite no pasó integrity_check.")
            os.replace(temporary, path)
            print("Base de datos restaurada desde Postgres.", flush=True)
        finally:
            temporary.unlink(missing_ok=True)
        return True


def save_database(path: Path):
    """Copiar un estado transaccional coherente y publicar la copia en Postgres."""
    if not enabled():
        return
    with _SYNC_LOCK:
        if not path.exists():
            raise RuntimeError("Falta la base de datos local que debe copiarse.")
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".backup-", suffix=".sqlite3", delete=False) as tmp:
            temporary = Path(tmp.name)
        try:
            with sqlite3.connect(path, timeout=25) as src, sqlite3.connect(temporary, timeout=25) as dst:
                src.backup(dst)
            blob = temporary.read_bytes()
            if not blob.startswith(b"SQLite format 3"):
                raise RuntimeError("No se generó una copia SQLite válida.")
            pg = postgres()
            with pg.connect(DB_URL, connect_timeout=20) as conn:
                conn.execute("""
                    INSERT INTO medicuida_sqlite_snapshots (snapshot_id,database_bytes,saved_at)
                    VALUES (1,%s,now())
                    ON CONFLICT (snapshot_id) DO UPDATE
                    SET database_bytes=EXCLUDED.database_bytes,saved_at=now()
                """,(blob,))
        finally:
            temporary.unlink(missing_ok=True)


class PersistentConnection(sqlite3.Connection):
    """Conserva la API sqlite3 actual y guarda después de cada commit exitoso."""
    def __enter__(self):
        self._start_changes = self.total_changes
        self._start_schema = self.execute("PRAGMA schema_version").fetchone()[0]
        return super().__enter__()

    def __exit__(self, exc_type, exc_value, tb):
        changed = self.total_changes != getattr(self, "_start_changes",self.total_changes)
        schema_changed = self.execute("PRAGMA schema_version").fetchone()[0] != getattr(self, "_start_schema",0)
        result = super().__exit__(exc_type,exc_value,tb)
        if exc_type is None and (changed or schema_changed):
            save_database(Path(os.environ.get("MEDICUIDA_SQLITE_PATH", __file__)).parent / "medicuida.sqlite3" if os.environ.get("MEDICUIDA_SQLITE_PATH") else _DB_PATH)
        return result


_DB_PATH: Path | None = None


def open_connection(path: Path) -> sqlite3.Connection:
    global _DB_PATH
    _DB_PATH=path
    conn=sqlite3.connect(path, timeout=25, factory=PersistentConnection if enabled() else sqlite3.Connection)
    conn.row_factory=sqlite3.Row
    return conn
