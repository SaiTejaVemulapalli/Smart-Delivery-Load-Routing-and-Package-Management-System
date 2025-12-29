# db.py  -- shared database helper

import pyodbc
import pandas as pd

# --------------------------------------------------------------------
# CONNECTION SETTINGS  (adjust only if your server / DB name change)
# --------------------------------------------------------------------
SERVER = r"DESKTOP-DMD0UKU\MSSQLSERVERSAI"
DATABASE = "DeliveryOptimizationDB"

# If you ever switch to SQL login, set USE_SQL_AUTH = True
USE_SQL_AUTH = False
SQL_USERNAME = "your_sql_username"
SQL_PASSWORD = "your_sql_password"

if USE_SQL_AUTH:
    CONN_STR = (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        f"SERVER={SERVER};"
        f"DATABASE={DATABASE};"
        f"UID={SQL_USERNAME};PWD={SQL_PASSWORD};"
    )
else:
    # Windows Authentication (what you're using now)
    CONN_STR = (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        f"SERVER={SERVER};"
        f"DATABASE={DATABASE};"
        "Trusted_Connection=yes;"
    )


# --------------------------------------------------------------------
# Low-level connection
# --------------------------------------------------------------------
def get_conn():
    """Return a new pyodbc connection."""
    return pyodbc.connect(CONN_STR)


# --------------------------------------------------------------------
# High-level helpers
# --------------------------------------------------------------------
def get_df(sql: str, params=None) -> pd.DataFrame:
    """Run a SELECT and return a pandas DataFrame."""
    with get_conn() as conn:
        return pd.read_sql(sql, conn, params=params)


def read(sql: str, params=None) -> pd.DataFrame:
    """
    Backwards-compatible alias for get_df(), so old code using
    db.read(...) still works.
    """
    return get_df(sql, params=params)


def exec(sql: str, params=None) -> None:
    """Run a non-query (INSERT/UPDATE/DELETE) once."""
    with get_conn() as conn:
        cur = conn.cursor()
        if params is None:
            cur.execute(sql)
        else:
            cur.execute(sql, params)
        conn.commit()


def executemany(sql: str, rows) -> None:
    """Run the same non-query for many rows."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.executemany(sql, list(rows))
        conn.commit()


def execmany(sql: str, rows) -> None:
    """
    Backwards-compatible alias so code calling db.execmany(...)
    still works. Internally uses executemany().
    """
    executemany(sql, rows)


def scalar(sql: str, params=None):
    """Run a query that returns a single value."""
    with get_conn() as conn:
        cur = conn.cursor()
        if params is None:
            cur.execute(sql)
        else:
            cur.execute(sql, params)
        row = cur.fetchone()
        return row[0] if row else None
