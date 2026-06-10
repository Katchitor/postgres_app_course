from typing import Final

import psycopg
from psycopg import Connection

DB_NAME: Final[str] = "inventorydb"
DB_USER: Final[str] = "app_user"
DB_PASSWORD: Final[str] = "pass"
DB_HOST: Final[str] = "127.0.0.1"
DB_PORT: Final[int] = 5432

_CONN: Connection | None = None


def connect() -> None:
    global _CONN
    _CONN = psycopg.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
        autocommit=True,
    )


def close() -> None:
    if _CONN is not None:
        _CONN.close()


def get_conn() -> Connection:
    if _CONN is None:
        raise RuntimeError("Database connection has not been established")
    return _CONN
