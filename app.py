# app.py
# ---------------------------------------------------------------------------
# MPAC Plant Energy & Process Dashboard
# Run with:  python app.py
# Then open: http://127.0.0.1:5000
# ---------------------------------------------------------------------------
import io
import csv
from datetime import datetime, timedelta

from flask import Flask, render_template, jsonify, request, Response

import config
import db

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@app.route("/")
def overview():
    return render_template(
        "overview.html",
        stations=list(config.LT_STATION_METERS.keys()),
        station_colors=config.STATION_COLORS,
        poll_ms=config.LIVE_POLL_INTERVAL_MS,
        demo=config.DEMO_MODE,
    )


@app.route("/lt/<station>")
def lt_station(station):
    station = station.upper()
    if station not in config.LT_STATION_METERS:
        return "Unknown station", 404
    meters = db.meters_for_station(station)
    return render_template(
        "station.html",
        station=station,
        meters=meters,
        color=config.STATION_COLORS.get(station, "#2F8FE0"),
        poll_ms=config.LIVE_POLL_INTERVAL_MS,
    )


@app.route("/boiler/<int:num>")
def boiler(num):
    if num not in config.BOILERS:
        return "Unknown boiler", 404
    return render_template("boiler.html", num=num, poll_ms=config.LIVE_POLL_INTERVAL_MS)


@app.route("/flow")
def flow():
    return render_template(
        "flow.html",
        flow_meters=config.FLOW_METERS,
        poll_ms=config.LIVE_POLL_INTERVAL_MS,
    )


@app.route("/report")
def report():
    stations = list(config.LT_STATION_METERS.keys())
    all_meters = db.all_meter_codes()
    return render_template(
        "report.html",
        stations=stations,
        all_meters=all_meters,
        flow_meters=config.FLOW_METERS,
        station_colors=config.STATION_COLORS,
        poll_ms=config.LIVE_POLL_INTERVAL_MS,
    )


# ---------------------------------------------------------------------------
# Live JSON APIs (polled every N ms by the browser)
# ---------------------------------------------------------------------------

@app.route("/api/health/db")
def api_health_db():
    """Quick diagnostic: tries to open the SQL Server connection and run a
    trivial query against each expected table, reporting exactly what fails."""
    if config.DEMO_MODE:
        return jsonify({"ok": True, "mode": "DEMO_MODE - not using SQL Server"})
    result = {"ok": True, "mode": "SQL Server", "checks": {}}
    try:
        conn = db.get_connection()
        result["checks"]["connect"] = "OK"
    except Exception as e:
        result["ok"] = False
        result["checks"]["connect"] = f"FAILED: {e}"
        return jsonify(result)
    for table in ["KWH", "Live", "Flow", "Boiler1"]:
        try:
            cur = conn.cursor()
            cur.execute(f"SELECT TOP (1) * FROM [dbo].[{table}]")
            row = cur.fetchone()
            result["checks"][table] = "OK - has rows" if row else "OK - table empty (0 rows)"
        except Exception as e:
            result["ok"] = False
            result["checks"][table] = f"FAILED: {e}"
    conn.close()
    return jsonify(result)


@app.route("/api/live/overview")
def api_live_overview():
    try:
        all_live = db.get_live_meters()
        per_station = {}
        total_p = total_e_today = 0.0
        for station, count in config.LT_STATION_METERS.items():
            codes = db.meters_for_station(station)
            p_sum = sum((all_live[c]["P"] or 0) for c in codes)
            e_sum = sum((all_live[c]["E"] or 0) for c in codes)
            per_station[station] = {
                "meters": count,
                "power_kw": round(p_sum, 1),
                "energy_kwh": round(e_sum, 1),
            }
            total_p += p_sum
            total_e_today += e_sum

        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_consumption = db.get_energy_consumption(db.all_meter_codes(), today_start, now)
        today_by_station = {}
        for station in config.LT_STATION_METERS:
            codes = db.meters_for_station(station)
            today_by_station[station] = round(sum((today_consumption.get(c) or 0) for c in codes), 1)

        flow_live = db.get_flow_live()

        # Top 5 consuming meters today
        ranking = sorted(
            ((c, today_consumption.get(c) or 0) for c in db.all_meter_codes()),
            key=lambda x: x[1], reverse=True
        )[:5]

        return jsonify({
            "timestamp": now.strftime("%d %b %Y  %I:%M:%S %p"),
            "total_power_kw": round(total_p, 1),
            "today_energy_kwh": round(sum(today_by_station.values()), 1),
            "per_station": per_station,
            "today_by_station": today_by_station,
            "flow_live": flow_live,
            "top_meters": [{"meter": m, "kwh": v} for m, v in ranking],
        })
    except Exception as e:
        app.logger.exception("api_live_overview failed")
        return jsonify({"error": str(e)}), 200


@app.route("/api/live/station/<station>")
def api_live_station(station):
    try:
        station = station.upper()
        meters = db.meters_for_station(station)
        live = db.get_live_meters(station)
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        consumption = db.get_energy_consumption(meters, today_start, now)
        rows = []
        for m in meters:
            row = dict(live.get(m, {}))
            row["meter"] = m
            row["today_kwh"] = consumption.get(m)
            rows.append(row)
        return jsonify({"timestamp": now.strftime("%I:%M:%S %p"), "meters": rows})
    except Exception as e:
        app.logger.exception("api_live_station failed")
        return jsonify({"error": str(e)}), 200


@app.route("/api/live/flow")
def api_live_flow():
    try:
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        live = db.get_flow_live()
        consumption = db.get_flow_consumption(today_start, now)
        rows = []
        for f in config.FLOW_METERS:
            rows.append({
                "meter": f,
                "flow": live[f]["flow"],
                "total": live[f]["total"],
                "today_total": consumption.get(f),
            })
        return jsonify({"timestamp": now.strftime("%I:%M:%S %p"), "flow": rows})
    except Exception as e:
        app.logger.exception("api_live_flow failed")
        return jsonify({"error": str(e)}), 200


@app.route("/api/live/boiler/<int:num>")
def api_live_boiler(num):
    try:
        data = db.get_boiler_live(num)
        return jsonify({"timestamp": datetime.now().strftime("%I:%M:%S %p"), "tags": data})
    except Exception as e:
        app.logger.exception("api_live_boiler failed")
        return jsonify({"error": str(e)}), 200


# ---------------------------------------------------------------------------
# Report API — date-range + individual station/meter selection
# ---------------------------------------------------------------------------

def _parse_range():
    start_s = request.args.get("start")
    end_s = request.args.get("end")
    fmt = "%Y-%m-%d"
    start = datetime.strptime(start_s, fmt) if start_s else datetime.now() - timedelta(days=7)
    end = datetime.strptime(end_s, fmt) if end_s else datetime.now()
    end = end.replace(hour=23, minute=59, second=59)
    return start, end


@app.route("/api/report/energy")
def api_report_energy():
    try:
        start, end = _parse_range()
        selection = request.args.get("meters", "")
        codes = [c.strip() for c in selection.split(",") if c.strip()] or db.all_meter_codes()

        consumption = db.get_energy_consumption(codes, start, end)
        trend = db.get_energy_trend(codes, start, end)

        by_station = {}
        for c in codes:
            station = c.split("M")[0]
            by_station.setdefault(station, 0.0)
            by_station[station] += consumption.get(c) or 0

        return jsonify({
            "start": start.strftime("%Y-%m-%d"),
            "end": end.strftime("%Y-%m-%d"),
            "meters": [{"meter": c, "kwh": consumption.get(c)} for c in codes],
            "by_station": {k: round(v, 1) for k, v in by_station.items()},
            "trend": trend,
            "total_kwh": round(sum(v or 0 for v in consumption.values()), 1),
        })
    except Exception as e:
        app.logger.exception("api_report_energy failed")
        return jsonify({"error": str(e)}), 200


@app.route("/api/report/flow")
def api_report_flow():
    try:
        start, end = _parse_range()
        consumption = db.get_flow_consumption(start, end)
        return jsonify({
            "start": start.strftime("%Y-%m-%d"),
            "end": end.strftime("%Y-%m-%d"),
            "totals": consumption,
            "grand_total": round(sum(v or 0 for v in consumption.values()), 1),
        })
    except Exception as e:
        app.logger.exception("api_report_flow failed")
        return jsonify({"error": str(e)}), 200


@app.route("/api/report/export.csv")
def export_csv():
    start, end = _parse_range()
    selection = request.args.get("meters", "")
    codes = [c.strip() for c in selection.split(",") if c.strip()] or db.all_meter_codes()
    consumption = db.get_energy_consumption(codes, start, end)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Meter", "Station", "Consumption (kWh)",
                      f"From {start.strftime('%Y-%m-%d')}", f"To {end.strftime('%Y-%m-%d')}"])
    for c in codes:
        writer.writerow([c, c.split("M")[0], consumption.get(c), "", ""])
    writer.writerow([])
    writer.writerow(["TOTAL", "", round(sum(v or 0 for v in consumption.values()), 1)])

    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=energy_report_{start:%Y%m%d}_{end:%Y%m%d}.csv"},
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
