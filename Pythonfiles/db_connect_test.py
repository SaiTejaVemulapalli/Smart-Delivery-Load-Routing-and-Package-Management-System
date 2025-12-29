import pyodbc

# -------------- CONFIG: EDIT THESE -----------------
SERVER   = r"DESKTOP-DMD0UKU\MSSQLSERVERSAI"
DATABASE = "DeliveryOptimizationDB"
USE_SQL_AUTH = False                  # True if you use SQL Login, False if Windows Auth

SQL_USERNAME = "your_sql_username"    # only used if USE_SQL_AUTH = True
SQL_PASSWORD = "your_sql_password"    # only used if USE_SQL_AUTH = True
# ---------------------------------------------------

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

def main():
    print("Connecting to SQL Server...")
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()

    # Simple test query: list dispatches
    cursor.execute("""
        SELECT Dispatch_id, Truck_id, Service_date, Status
        FROM wh.Dispatch
        ORDER BY Dispatch_id;
    """)

    rows = cursor.fetchall()
    print("Dispatches in DB:")
    for r in rows:
        print(f"  Dispatch {r.Dispatch_id}: Truck {r.Truck_id}, Date={r.Service_date}, Status={r.Status}")

    conn.close()
    print("Connection test successful.")

if __name__ == "__main__":
    main()
