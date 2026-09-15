# config.py
# ---------------------------------------------------------------------------
# Central configuration for the MPAC Plant Energy & Process Dashboard.
# ---------------------------------------------------------------------------

# Set to False once you're ready to point the app at your real SQL Server.
# In demo mode the app generates realistic-looking live data in memory so you
# can preview the whole UI without a database connection.
DEMO_MODE = True

# Your SQL Server connection string (from the .txt you provided).
# Requires the "ODBC Driver 17 for SQL Server" (or 18) to be installed.
# Install pyodbc: pip install pyodbc
SQL_SERVER_CONN_STR = (
    r"DRIVER={ODBC Driver 17 for SQL Server};"
    r"SERVER=DESKTOP-JRNQ4AM\SQLEXPRESS;"
    r"DATABASE=MyDB;"
    r"Trusted_Connection=yes;"
    r"TrustServerCertificate=yes;"
)

DATABASE_NAME = "MyDB"

# Number of meters per LT station (from the KWH/Live column lists you sent)
LT_STATION_METERS = {
    "LT1": 11,   # LT1M01 .. LT1M11
    "LT2": 8,    # LT2M01 .. LT2M08
    "LT3": 8,    # LT3M01 .. LT3M08
    "LT4": 8,    # LT4M01 .. LT4M08
}

# Colors used consistently for each station across charts
STATION_COLORS = {
    "LT1": "#2F8FE0",
    "LT2": "#E0A72F",
    "LT3": "#9B6BE0",
    "LT4": "#35C48C",
}

# Flow meters (Flow table: F1..F4, each with instantaneous + totalizer)
FLOW_METERS = ["F1", "F2", "F3", "F4"]

# Boilers available (Boiler1 always present; Boiler2 optional / same tag shape)
BOILERS = [1, 2]

# How often the browser polls the live endpoints, in milliseconds
LIVE_POLL_INTERVAL_MS = 5000
