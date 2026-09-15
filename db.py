# db.py
# ---------------------------------------------------------------------------
# All data access lives here. Two modes:
#   - DEMO_MODE = True  -> synthetic in-memory data (no DB needed)
#   - DEMO_MODE = False -> real queries against SQL Server via pyodbc
#
# The rest of the app (app.py) never knows which mode it's in - it just calls
# these functions.
# ---------------------------------------------------------------------------
import math
import random
import time
import threading
from datetime import datetime, timedelta

import config

# ---------------------------------------------------------------------------
# Meter helpers
# ---------------------------------------------------------------------------

def all_meter_codes():
    """Returns e.g. ['LT1M01','LT1M02',...,'LT4M08']"""
    codes = []
    for station, count in config.LT_STATION_METERS.items():
        for i in range(1, count + 1):
            codes.append(f"{station}M{i:02d}")
    return codes


def meters_for_station(station):
    count = config.LT_STATION_METERS[station]
    return [f"{station}M{i:02d}" for i in range(1, count + 1)]


# ---------------------------------------------------------------------------
# Real SQL Server connection (used when DEMO_MODE is False)
# ---------------------------------------------------------------------------

def get_connection():
    import pyodbc
    return pyodbc.connect(config.SQL_SERVER_CONN_STR, timeout=5)


def _run_query(sql, params=()):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        return rows
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# DEMO DATA ENGINE
# A background thread advances a synthetic plant simulation every second so
# live pages show moving numbers, and a rolling history buffer backs the
# reports and trend charts without needing a real database.
# ---------------------------------------------------------------------------

class _DemoPlant:
    def __init__(self):
        self.lock = threading.Lock()
        self.meters = all_meter_codes()
        # base electrical characteristics per meter (kW draw, PF, V, F)
        self.base_kw = {m: random.uniform(8, 60) for m in self.meters}
        self.energy_kwh = {m: random.uniform(500, 12000) for m in self.meters}  # totalizer
        self.flow_total = {f: random.uniform(2000, 50000) for f in config.FLOW_METERS}
        self.boiler_state = {
            1: dict(TT_501=182.0, FT_500=1200.0, FIQ_500=845000.0, PT_501=8.4,
                    LT_101=52.0, LCV_101=48.0, FT_100=310.0, FIQQ_100=210000.0,
                    TCV_100=55.0, TT_100=24.5, LCV_100=44.0, LT_100=50.0, TT_500=196.0),
            2: dict(TT_501=178.0, FT_500=1140.0, FIQ_500=790000.0, PT_501=8.1,
                    LT_101=49.0, LCV_101=46.0, FT_100=298.0, FIQQ_100=198000.0,
                    TCV_100=52.0, TT_100=24.0, LCV_100=42.0, LT_100=48.0, TT_500=190.0),
        }
        self.history = []  # list of dicts: {ts, energy_kwh:{...}, flow_total:{...}}
        self.t0 = time.time()
        self._seed_history()
        self._running = True
        threading.Thread(target=self._tick_loop, daemon=True).start()

    def _seed_history(self):
        # Build ~30 days of hourly history so reports/date-range have data
        now = datetime.now()
        start = now - timedelta(days=30)
        energy = {m: max(50.0, self.energy_kwh[m] - self.base_kw[m] * 24 * 30 * 0.6)
                  for m in self.meters}
        flow = {f: max(50.0, self.flow_total[f] - random.uniform(30, 90) * 24 * 30)
                for f in config.FLOW_METERS}
        ts = start
        while ts <= now:
            hour_factor = 0.55 + 0.45 * math.sin((ts.hour - 6) / 24 * 2 * math.pi) ** 2
            for m in self.meters:
                energy[m] += self.base_kw[m] * hour_factor * (1 + random.uniform(-0.08, 0.08))
            for f in config.FLOW_METERS:
                flow[f] += random.uniform(20, 80) * hour_factor
            self.history.append({
                "ts": ts,
                "energy_kwh": dict(energy),
                "flow_total": dict(flow),
            })
            ts += timedelta(hours=1)
        self.energy_kwh = dict(energy)
        self.flow_total = dict(flow)

    def _tick_loop(self):
        while self._running:
            time.sleep(1)
            with self.lock:
                hour_factor = 0.55 + 0.45 * math.sin((datetime.now().hour - 6) / 24 * 2 * math.pi) ** 2
                for m in self.meters:
                    self.energy_kwh[m] += (self.base_kw[m] / 3600.0) * hour_factor * (1 + random.uniform(-0.15, 0.15))
                for f in config.FLOW_METERS:
                    self.flow_total[f] += random.uniform(0.005, 0.02) * hour_factor
                for b in self.boiler_state.values():
                    b["TT_501"] += random.uniform(-0.3, 0.3)
                    b["FT_500"] += random.uniform(-8, 8)
                    b["PT_501"] += random.uniform(-0.05, 0.05)
                    b["LT_101"] = min(100, max(0, b["LT_101"] + random.uniform(-1, 1)))
                # append hourly history snapshot at top of each hour
                now = datetime.now()
                if not self.history or (now - self.history[-1]["ts"]).total_seconds() >= 3600:
                    self.history.append({
                        "ts": now,
                        "energy_kwh": dict(self.energy_kwh),
                        "flow_total": dict(self.flow_total),
                    })

    def live_meter_row(self, code):
        with self.lock:
            kw = self.base_kw[code] * (1 + random.uniform(-0.1, 0.1))
            v = random.uniform(398, 412)
            pf = random.uniform(0.9, 0.99)
            i = (kw * 1000) / (1.732 * v * pf) if v and pf else 0
            return {
                "Vavg": round(v, 1),
                "Iavg": round(i, 1),
                "P": round(kw, 2),
                "PF": round(pf, 2),
                "F": round(random.uniform(49.9, 50.1), 2),
                "E": round(self.energy_kwh[code], 1),
            }

    def energy_between(self, code, start, end):
        with self.lock:
            snaps = [h for h in self.history if start <= h["ts"] <= end]
            if not snaps:
                return 0.0
            return max(0.0, snaps[-1]["energy_kwh"][code] - snaps[0]["energy_kwh"][code])

    def trend_between(self, codes, start, end):
        with self.lock:
            snaps = [h for h in self.history if start <= h["ts"] <= end]
        return snaps

    def flow_live(self, f):
        with self.lock:
            return {
                "flow": round(random.uniform(30, 90), 2),
                "total": round(self.flow_total[f], 1),
            }

    def boiler_live(self, num):
        with self.lock:
            return dict(self.boiler_state.get(num, {}))


_plant = _DemoPlant() if config.DEMO_MODE else None


# ---------------------------------------------------------------------------
# PUBLIC API - dispatches to demo engine or real SQL depending on config
# ---------------------------------------------------------------------------

def get_live_meters(station=None):
    """Returns {meter_code: {Vavg,Iavg,P,PF,F,E}} for one station or all."""
    codes = meters_for_station(station) if station else all_meter_codes()
    if config.DEMO_MODE:
        return {c: _plant.live_meter_row(c) for c in codes}

    cols = []
    for c in codes:
        cols += [f"{c}_Vavg", f"{c}_Iavg", f"{c}_P", f"{c}_PF", f"{c}_F"]
    col_sql = ",".join(f"[{x}]" for x in cols)
    kwh_cols = ",".join(f"[{c}_E]" for c in codes)
    live_row = _run_query(f"SELECT TOP (1) {col_sql} FROM [dbo].[Live] ORDER BY Time_Stamp DESC")
    kwh_row = _run_query(f"SELECT TOP (1) {kwh_cols} FROM [dbo].[KWH] ORDER BY Time_Stamp DESC")
    live_row = live_row[0] if live_row else {}
    kwh_row = kwh_row[0] if kwh_row else {}
    out = {}
    for c in codes:
        out[c] = {
            "Vavg": live_row.get(f"{c}_Vavg"),
            "Iavg": live_row.get(f"{c}_Iavg"),
            "P": live_row.get(f"{c}_P"),
            "PF": live_row.get(f"{c}_PF"),
            "F": live_row.get(f"{c}_F"),
            "E": kwh_row.get(f"{c}_E"),
        }
    return out


def get_energy_consumption(codes, start, end):
    """Returns {code: kWh consumed in [start,end]} using first/last totalizer reading."""
    if config.DEMO_MODE:
        return {c: round(_plant.energy_between(c, start, end), 1) for c in codes}

    col_sql = ",".join(f"[{c}_E]" for c in codes)
    first = _run_query(
        f"SELECT TOP (1) {col_sql} FROM [dbo].[KWH] WHERE Time_Stamp >= ? ORDER BY Time_Stamp ASC",
        (start,))
    last = _run_query(
        f"SELECT TOP (1) {col_sql} FROM [dbo].[KWH] WHERE Time_Stamp <= ? ORDER BY Time_Stamp DESC",
        (end,))
    first = first[0] if first else {}
    last = last[0] if last else {}
    out = {}
    for c in codes:
        f0 = first.get(f"{c}_E")
        f1 = last.get(f"{c}_E")
        out[c] = round((f1 - f0), 1) if (f0 is not None and f1 is not None) else None
    return out


def get_energy_trend(codes, start, end, group_by="LT_station"):
    """Returns list of {ts, <station>: kwh_in_bucket} for a bar/line chart,
    bucketed by day (for ranges > 3 days) or by hour (short ranges)."""
    span_hours = (end - start).total_seconds() / 3600.0
    bucket_hours = 24 if span_hours > 72 else 1

    if config.DEMO_MODE:
        snaps = _plant.trend_between(codes, start, end)
        if not snaps:
            return []
        buckets = {}
        order = []
        for snap in snaps:
            bucket_ts = snap["ts"].replace(minute=0, second=0, microsecond=0)
            if bucket_hours == 24:
                bucket_ts = bucket_ts.replace(hour=0)
            key = bucket_ts
            if key not in buckets:
                buckets[key] = {"ts": key, "_first": snap["energy_kwh"], "_last": snap["energy_kwh"]}
                order.append(key)
            buckets[key]["_last"] = snap["energy_kwh"]
        rows = []
        for key in order:
            b = buckets[key]
            row = {"ts": key.strftime("%Y-%m-%d %H:%M")}
            for c in codes:
                row[c] = round(max(0.0, b["_last"][c] - b["_first"][c]), 1)
            rows.append(row)
        return rows

    # Real SQL: bucket via DATEADD/DATEDIFF trick, sum deltas per bucket via window func
    col_sql = ",".join(f"[{c}_E]" for c in codes)
    rows = _run_query(
        f"SELECT Time_Stamp, {col_sql} FROM [dbo].[KWH] "
        f"WHERE Time_Stamp BETWEEN ? AND ? ORDER BY Time_Stamp ASC",
        (start, end))
    if not rows:
        return []
    buckets = {}
    order = []
    for r in rows:
        ts = r["Time_Stamp"]
        bucket_ts = ts.replace(minute=0, second=0, microsecond=0)
        if bucket_hours == 24:
            bucket_ts = bucket_ts.replace(hour=0)
        if bucket_ts not in buckets:
            buckets[bucket_ts] = {"first": r, "last": r}
            order.append(bucket_ts)
        buckets[bucket_ts]["last"] = r
    out = []
    for key in order:
        b = buckets[key]
        row = {"ts": key.strftime("%Y-%m-%d %H:%M")}
        for c in codes:
            v0, v1 = b["first"].get(f"{c}_E"), b["last"].get(f"{c}_E")
            row[c] = round(max(0.0, v1 - v0), 1) if v0 is not None and v1 is not None else 0.0
        out.append(row)
    return out


def get_flow_live():
    out = {}
    for f in config.FLOW_METERS:
        if config.DEMO_MODE:
            out[f] = _plant.flow_live(f)
        else:
            row = _run_query(
                f"SELECT TOP (1) [{f}_Flow],[{f}_Total_Flow] FROM [dbo].[Flow] ORDER BY Time_Stamp DESC")
            row = row[0] if row else {}
            out[f] = {"flow": row.get(f"{f}_Flow"), "total": row.get(f"{f}_Total_Flow")}
    return out


def get_flow_consumption(start, end):
    if config.DEMO_MODE:
        out = {}
        with _plant.lock:
            snaps = [h for h in _plant.history if start <= h["ts"] <= end]
        for f in config.FLOW_METERS:
            if not snaps:
                out[f] = 0.0
            else:
                out[f] = round(max(0.0, snaps[-1]["flow_total"][f] - snaps[0]["flow_total"][f]), 1)
        return out

    out = {}
    for f in config.FLOW_METERS:
        first = _run_query(
            f"SELECT TOP (1) [{f}_Total_Flow] FROM [dbo].[Flow] WHERE Time_Stamp >= ? ORDER BY Time_Stamp ASC",
            (start,))
        last = _run_query(
            f"SELECT TOP (1) [{f}_Total_Flow] FROM [dbo].[Flow] WHERE Time_Stamp <= ? ORDER BY Time_Stamp DESC",
            (end,))
        f0 = first[0].get(f"{f}_Total_Flow") if first else None
        f1 = last[0].get(f"{f}_Total_Flow") if last else None
        out[f] = round(f1 - f0, 1) if (f0 is not None and f1 is not None) else None
    return out


def get_boiler_live(num):
    if config.DEMO_MODE:
        return _plant.boiler_live(num)
    row = _run_query(f"SELECT TOP (1) * FROM [dbo].[Boiler{num}] ORDER BY Time_Stamp DESC")
    return row[0] if row else {}
