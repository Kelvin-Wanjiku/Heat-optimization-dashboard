#!/usr/bin/env python3
"""Export the partner's real AI-forecast and digital-twin results into one static file for the dashboard.

Needs the partner project (pai700_final_project) running locally:
    feed :8001, twin service :8002, forecast service :8003   (docker compose up --build)
Writes data/oslo_ai.json, which dashboard.js loads next to dashboard_data.json.
Standard library only.

    python3 export_oslo_data.py [--feed URL] [--twin URL] [--forecast URL]
"""
import argparse
import datetime as dt
import json
import urllib.request

ap = argparse.ArgumentParser()
ap.add_argument("--feed", default="http://localhost:8001")
ap.add_argument("--twin", default="http://localhost:8002")
ap.add_argument("--forecast", default="http://localhost:8003")
ap.add_argument("--out", default="data/oslo_ai.json")
ap.add_argument("--twin-only", action="store_true", help="keep the forecasts already in --out, redo only the twin runs")
args = ap.parse_args()


def get(url):
    with urllib.request.urlopen(url, timeout=300) as r:
        return json.load(r)


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M")


info = get(args.feed + "/buildings")
model = None if args.twin_only else get(args.forecast + "/model")
win_first = dt.datetime.fromisoformat(info["window"]["first"]).replace(tzinfo=None)
win_last = dt.datetime.fromisoformat(info["window"]["last"]).replace(tzinfo=None)
replay_start = dt.datetime.fromisoformat(info["window"]["replay_start"]).replace(tzinfo=None)
HORIZONS = [1, 6, 24]

# hourly index of the whole window; every array below is aligned to it
hours = []
t = win_first
while t <= win_last:
    hours.append(t)
    t += dt.timedelta(hours=1)
idx = {h: i for i, h in enumerate(hours)}

out = None if args.twin_only else {
    "meta": {
        "source": "PAI700 final project (Group 10): replay feed, forecast service and twin service, run locally and exported",
        "dataset": "SINTEF COFACTOR-SBHUB Oslo school dataset (Lien et al., Data in Brief 63, 112288, 2025), CC BY 4.0",
        "timezone": "fixed UTC+1 all year, no daylight saving",
        "window_first": iso(win_first),
        "replay_start": iso(replay_start),
        "window_last": iso(win_last),
        "hours": len(hours),
        "model": {
            "version": model["version"],
            "train_end": model["train_end"],
            "rule": model["rule"],
            "lookback_hours": model["lookback_hours"],
            "test_wape": {str(s["horizon"]): s["wape"] for s in model["test_scores"]},
        },
        "forecast_note": model["note"],
    },
    "buildings": [],
    "twin": {"weeks": []},
}

# ---------------- AI forecasts ----------------
if args.twin_only:
    out = json.load(open(args.out))
for b in ([] if args.twin_only else info["buildings"]):
    bid = b["building_id"]
    rows = get(f"{args.feed}/readings?until={iso(win_last)}&building={bid}")
    n = len(hours)
    heat = [None] * n
    tout = [None] * n
    for r in rows:
        ts = dt.datetime.fromisoformat(r["timestamp"]).replace(tzinfo=None)
        if ts in idx:
            heat[idx[ts]] = round(r["HtTot"] / 1000.0, 2)       # kW (Wh per hour / 1000)
            tout[idx[ts]] = round(r["Tout"], 1)
    fc = {h: [None] * n for h in HORIZONS}
    cursor = win_first + dt.timedelta(hours=167)
    while cursor <= win_last:
        end = min(cursor + dt.timedelta(days=30), win_last)
        d = get(f"{args.forecast}/forecast/series?from={iso(cursor)}&until={iso(end)}&building={bid}"
                f"&horizons=1,6,24")
        for h in HORIZONS:
            for p in d["series"][str(h)]:
                ts = dt.datetime.fromisoformat(p["target_time"]).replace(tzinfo=None)
                if ts in idx:
                    fc[h][idx[ts]] = round(p["wh"] / 1000.0, 2)
        cursor = end + dt.timedelta(hours=1)
    # scores on the replay window (forecast vs measured), and the simple baselines for comparison
    def wape(pred):
        num = den = 0.0
        for i in range(n):
            if hours[i] >= replay_start and heat[i] is not None and pred(i) is not None:
                num += abs(pred(i) - heat[i]); den += heat[i]
        return round(num / den, 4) if den else None
    def mae(pred):
        tot = c = 0
        for i in range(n):
            if hours[i] >= replay_start and heat[i] is not None and pred(i) is not None:
                tot += abs(pred(i) - heat[i]); c += 1
        return round(tot / c, 2) if c else None
    scores = {}
    for h in HORIZONS:
        scores[str(h)] = {
            "wape": wape(lambda i, h=h: fc[h][i]),
            "mae_kw": mae(lambda i, h=h: fc[h][i]),
            "seasonal_naive_wape": wape(lambda i: heat[i - 24] if i >= 24 else None),
        }
    scores["1"]["persistence_wape"] = wape(lambda i: heat[i - 1] if i >= 1 else None)
    out["buildings"].append({
        "id": bid, "floor_area_m2": b["floor_area"], "year_built": b["year_of_construction"],
        "heat_kw": heat, "tout_c": tout,
        "forecast_kw": {str(h): fc[h] for h in HORIZONS},
        "scores_replay": scores,
    })
    print(bid, "forecast scores", scores)

# ---------------- digital twin: every Monday x every school x 1/3/5/7 days ----------------
# A shorter run is exactly the start of a longer one (same start state), so the curves are stored once per
# (school, Monday) from the longest run that fits, thinned to 30-minute points; the summary numbers are the
# service's own, exported for every length.
d0 = replay_start
while d0.weekday() != 0:
    d0 += dt.timedelta(days=1)
twin = {"mondays": [], "runs": {}}
last_r = None
while d0 + dt.timedelta(days=1) <= win_last + dt.timedelta(hours=1):
    start = d0.strftime("%Y-%m-%d")
    for b in info["buildings"]:
        bid = str(b["building_id"])
        entry = {"days": {}}
        for days in (7, 5, 3, 1):
            try:
                r = get(f"{args.twin}/compare?start={start}&days={days}&building={bid}")
            except Exception:                                   # does not fit the data window
                continue
            last_r = r
            temp = r["weather"]["t_outdoor_C"]
            entry["days"][str(days)] = {
                "legacy": r["runs"]["legacy"]["summary"], "combined": r["runs"]["combined"]["summary"],
                "mean_outdoor_c": round(sum(temp) / len(temp), 1)}
            if "series" not in entry:                           # longest run that fit
                ls, cs = r["runs"]["legacy"]["series"], r["runs"]["combined"]["series"]
                k = slice(2, None, 3)                           # every 30 min (the series is 10-minute, first point 00:10)
                entry["series"] = {
                    "legacy_t_air": [round(v, 2) for v in ls["t_air_C"][k]],
                    "combined_t_air": [round(v, 2) for v in cs["t_air_C"][k]],
                    "legacy_kw": [round(a + c, 2) for a, c in zip(ls["radiator_kW"][k], ls["coil_kW"][k])],
                    "combined_kw": [round(a + c, 2) for a, c in zip(cs["radiator_kW"][k], cs["coil_kW"][k])],
                    "outdoor_c": [round(v, 1) for v in temp[k]]}
        if entry["days"]:
            twin["runs"].setdefault(bid, {})[start] = entry
    if start in twin["runs"].get(str(info["buildings"][0]["building_id"]), {}):
        twin["mondays"].append(start)
    print("twin", start, "done")
    d0 += dt.timedelta(days=7)
twin["room"] = {"floor_area_m2": last_r["room_floor_area_m2"], "setpoint_c": last_r["setpoint_C"],
                "purge_trigger_c": last_r["purge_trigger_C"], "south_facade_ratio": last_r["south_facade_ratio"]}
twin["note"] = last_r["note"]
twin["series_step_min"] = 30
out["twin"] = twin

with open(args.out, "w") as f:
    json.dump(out, f, separators=(",", ":"))
print("wrote", args.out)
