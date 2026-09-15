# MPAC Plant Energy & Process Dashboard

A multi-page Flask dashboard for 4 LT stations (35 energy meters), 2 boilers,
and 4 flow meters, styled after the InduSoft-style reference screenshot.

## Pages
- **Overview** (`/`) — plant-wide KPIs, system diagram, today's energy by
  station bar chart, top-5 consuming meters, live flow snapshot.
- **LT Station 1–4** (`/lt/LT1` … `/lt/LT4`) — live V/I/P/PF/Hz table per
  meter (11 meters on LT1, 8 each on LT2–LT4), today's consumption bar chart.
- **Boiler 1 / 2** (`/boiler/1`, `/boiler/2`) — live process tag table +
  key readings (steam temp, steam flow, drum pressure, drum level).
- **Flow Meters** (`/flow`) — instantaneous flow, totalizer, and today's
  consumption for F1–F4.
- **Energy Report** (`/report`) — pick a date range, filter by station
  (chips) or individual meters (multi-select), and get: total kWh, total
  flow m³, a per-station bar chart, a trend chart over the range, a
  per-meter consumption table, a flow totalizer table, and CSV export.

All live pages poll their JSON API every 5 seconds (`config.LIVE_POLL_INTERVAL_MS`).

## Running it

```bash
pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:5000**.

By default the app runs in **DEMO_MODE** (see `config.py`) — it generates
realistic synthetic live data and ~30 days of history in memory, so you can
see the whole UI immediately with no database.

## Connecting to your real SQL Server

1. Install the ODBC driver (Windows: "ODBC Driver 17 for SQL Server" from
   Microsoft; it's usually already present if SSMS is installed).
2. In `config.py`, set:
   ```python
   DEMO_MODE = False
   ```
3. Check `SQL_SERVER_CONN_STR` matches your setup. Your original string used
   `Integrated Security=True`, which maps to `Trusted_Connection=yes` in the
   ODBC connection string already set for you. Adjust `SERVER=` / `DATABASE=`
   if they differ.
4. This build assumes your `MyDB` database layout from the query file you
   sent:
   - `dbo.KWH` — cumulative energy per meter, columns `LT{n}M{nn}_E`
   - `dbo.Live` — per-meter `Vavg`, `Iavg`, `P`, `PF`, `F`
   - `dbo.Flow` — `F1..F4` with `_Flow` (instant) and `_Total_Flow` (totalizer)
   - `dbo.Boiler1` (and optionally `Boiler2` with the same tag shape)

   If your real column names differ even slightly, adjust the column-building
   logic in `db.py` (functions `get_live_meters`, `get_energy_consumption`,
   `get_energy_trend`, `get_flow_live`, `get_flow_consumption`,
   `get_boiler_live`) — they're centralized so changes are localized.

## Customizing

- **Meter counts / station layout**: `config.LT_STATION_METERS`
- **Colors**: `config.STATION_COLORS`
- **Poll interval**: `config.LIVE_POLL_INTERVAL_MS`
- **Logo**: replace `static/img/mpac-logo.jpeg`
- **Theme**: all colors/spacing are CSS variables at the top of
  `static/css/style.css`

## Notes on "consumption" calculations

Both energy (kWh) and flow (m³) meters in your source tables store
**cumulative totalizers**, not instantaneous consumption. So "consumption
over a date range" is computed as `(last reading in range) - (first reading
in range)` — done in `db.get_energy_consumption` / `db.get_flow_consumption`.
This is the correct approach for totalizer-style meters and avoids drift
from summing instantaneous power samples.
