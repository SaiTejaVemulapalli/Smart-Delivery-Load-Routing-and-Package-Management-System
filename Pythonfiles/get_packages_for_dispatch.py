import pyodbc
import pandas as pd

# -------------- CONFIG: EDIT THESE TO MATCH db_connect_test.py -----------------
SERVER   = r"DESKTOP-DMD0UKU\MSSQLSERVERSAI"
DATABASE = "DeliveryOptimizationDB"
USE_SQL_AUTH = False                  # True if you use SQL Login, False if Windows Auth

SQL_USERNAME = "your_sql_username"    # only used if USE_SQL_AUTH = True
SQL_PASSWORD = "your_sql_password"    # only used if USE_SQL_AUTH = True
# ------------------------------------------------------------------------------

if USE_SQL_AUTH:
    conn_str = (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        f"SERVER={SERVER};"
        f"DATABASE={DATABASE};"
        f"UID={SQL_USERNAME};"
        f"PWD={SQL_PASSWORD};"
    )
else:
    conn_str = (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        f"SERVER={SERVER};"
        f"DATABASE={DATABASE};"
        "Trusted_Connection=yes;"
    )

def get_connection():
    """Create and return a new DB connection."""
    return pyodbc.connect(conn_str)

def get_packages_for_dispatch(dispatch_id: int) -> pd.DataFrame:
    """
    Returns a DataFrame of all packages assigned to a given Dispatch_id,
    including stop sequence and destination address info.
    """
    conn = get_connection()

    query = """
    SELECT
        p.Package_id,
        p.Address_id,
        p.Weight_lbs,
        p.Length_cm,
        p.Width_cm,
        p.Height_cm,
        p.Fragile_flag,
        p.Status           AS PackageStatus,
        p.Created_ts,
        pa.Stop_id,
        ds.Dispatch_id,
        ds.Sequence        AS StopSequence,
        a.Address_line1,
        a.City,
        a.State,
        a.Postal_code
    FROM wh.Package            AS p
    JOIN wh.PackageAssignment  AS pa ON pa.Package_id = p.Package_id
    JOIN wh.DispatchStop       AS ds ON ds.Stop_id    = pa.Stop_id
    JOIN wh.Dispatch           AS d  ON d.Dispatch_id = ds.Dispatch_id
    JOIN wh.Address            AS a  ON a.Address_id  = p.Address_id
    WHERE d.Dispatch_id = ?
    ORDER BY ds.Sequence, p.Package_id;
    """

    df = pd.read_sql(query, conn, params=[dispatch_id])
    conn.close()
    return df

def main():
    # for now, just hard-code Dispatch 1 to test
    dispatch_id = 1

    print(f"Getting packages for Dispatch {dispatch_id} ...")
    df = get_packages_for_dispatch(dispatch_id)

    print(f"Found {len(df)} packages for Dispatch {dispatch_id}.")
    if not df.empty:
        print(df)
    else:
        print("No packages found for this dispatch.")

if __name__ == "__main__":
    main()
