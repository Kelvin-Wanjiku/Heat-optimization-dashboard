#!/usr/bin/env python3
"""Build data/oslo_ai.json (the Oslo AI forecasts and smart-control simulations) straight from the PAI700 code in
oslo_ai/. No servers, no Docker: it reads the frozen Oslo window, runs the saved forecasting models and the digital
twin in this process, and writes one static file the dashboard loads.

    pip install -r requirements-oslo.txt
    python export_oslo_data.py                # forecasts + simulations (about 10 minutes on a laptop CPU)
    python export_oslo_data.py --twin-only    # keep the forecasts already in the file, redo only the simulations
    python export_oslo_data.py --forecast-only

The numbers are identical to what the PAI700 services (feed, forecast service, twin service) return.
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OSLO = HERE / "oslo_ai"
sys.path.insert(0, str(OSLO))                      # the vendored packages: twin, modeling, etl

import pandas as pd                                 # noqa: E402

from etl import windows as w                        # noqa: E402
from modeling.predictor import TZ, Predictor, make_frame   # noqa: E402
from twin.feed_weather import FeedWeather           # noqa: E402
from twin.params import load_params                 # noqa: E402
from twin_runner import PREVIEW_MARGIN_H, compare   # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--out", default=str(HERE / "data" / "oslo_ai.json"))
ap.add_argument("--twin-only", action="store_true", help="keep the forecasts already in --out, redo the twin runs")
ap.add_argument("--forecast-only", action="store_true", help="keep the twin runs already in --out, redo the forecasts")
args = ap.parse_args()

HORIZONS = [1, 6, 24]
FROZEN = OSLO / "frozen" / "oslo_window_v1.parquet"
MODEL_DIR = OSLO / "models" / "ai_v1"
HEAT_AND_WEATHER = ["HtTot", "Tout", "SolGlob", "WindSpd", "WindDir"]
STATIC = ["floor_area", "year_of_construction"]


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M")


# ---------------- the frozen window (what the replay feed serves) ----------------
try:
    df = pd.read_parquet(FROZEN)
except Exception as err:                            # an older pyarrow (e.g. in Anaconda) cannot read this parquet file
    print(f"Could not read {FROZEN.name} ({err}).\nUsing the identical CSV copy instead; "
          "'pip install -U pyarrow' would fix the parquet reading.", flush=True)
    df = pd.read_csv(FROZEN.with_suffix(".csv"))
df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert(TZ)
building_ids = sorted(int(b) for b in df["building_id"].unique())
static = df.drop_duplicates("building_id").set_index("building_id")[STATIC]
first = df["timestamp"].min()
last = df["timestamp"].max()
replay_start = df.loc[df["phase"] == "replay", "timestamp"].min()
naive = lambda t: t.tz_localize(None).to_pydatetime()        # the data's own clock (fixed UTC+1)
win_first, win_last, replay_first = naive(first), naive(last), naive(replay_start)
hours = pd.date_range(win_first, win_last, freq="h")
idx = {h.to_pydatetime(): i for i, h in enumerate(hours)}


def rows_of(building, lo, hi, with_heat=True):
    """Feed-style readings of one building for lo <= t <= hi (tz-aware Timestamps)."""
    part = df[(df["building_id"] == building) & (df["timestamp"] >= lo) & (df["timestamp"] <= hi)]
    cols = HEAT_AND_WEATHER if with_heat else [c for c in HEAT_AND_WEATHER if c != "HtTot"]
    out = []
    for r in part.sort_values("timestamp").to_dict("records"):
        d = {"timestamp": r["timestamp"].isoformat(), "building_id": int(r["building_id"])}
        d.update({c: float(r[c]) for c in cols})
        out.append(d)
    return out


old = json.loads(Path(args.out).read_text()) if (args.twin_only or args.forecast_only) else None
model_info = json.loads((MODEL_DIR / "manifest.json").read_text())
predictor = Predictor(MODEL_DIR)                    # checks every model file against the manifest checksums

if args.twin_only:
    out = old
else:
    out = {
        "meta": {
            "source": "PAI700 final project (Group 10): frozen Oslo window, saved forecasting models and digital twin (vendored in oslo_ai/)",
            "dataset": "SINTEF COFACTOR-SBHUB Oslo school dataset (Lien et al., Data in Brief 63, 112288, 2025), CC BY 4.0",
            "timezone": "fixed UTC+1 all year, no daylight saving",
            "window_first": iso(win_first), "replay_start": iso(replay_first), "window_last": iso(win_last),
            "hours": len(hours),
            "model": {
                "version": model_info["version"], "train_end": model_info["train_end"], "rule": model_info["rule"],
                "lookback_hours": model_info["lookback"],
                "test_wape": {str(s["horizon"]): s["wape"] for s in model_info.get("test_scores", [])},
            },
            "forecast_note": ("Forecast of the whole building's heat use. The next hours of weather are measured values "
                              "replayed as a perfect forecast, so real forecast errors are not included: the accuracy is an upper bound."),
        },
        "buildings": [], "twin": old["twin"] if old else {},
    }

# ---------------- AI forecasts ----------------
if not args.twin_only:
    n = len(hours)
    for bid in building_ids:
        sub = df[df["building_id"] == bid].sort_values("timestamp")
        heat, tout = [None] * n, [None] * n
        for r in sub.to_dict("records"):
            i = idx.get(naive(r["timestamp"]))
            if i is not None:
                heat[i] = round(r["HtTot"] / 1000.0, 2)                  # kW
                tout[i] = round(r["Tout"], 1)
        fc = {h: [None] * n for h in HORIZONS}
        cursor = first + pd.Timedelta(hours=w.LOOKBACK - 1)
        while cursor <= last:
            end = min(cursor + pd.Timedelta(days=30), last)
            lo = cursor - pd.Timedelta(hours=w.LOOKBACK - 1)
            rows = rows_of(bid, lo, end)                                  # heat up to the last origin ...
            ahead = rows_of(bid, end + pd.Timedelta(hours=1), end + pd.Timedelta(hours=max(HORIZONS)), with_heat=False)
            frame = make_frame(rows + ahead)                              # ... and only WEATHER after it (no future heat)
            for h in HORIZONS:
                origins = pd.date_range(cursor, end, freq="h")
                origins = origins[(origins >= frame.index.min() + pd.Timedelta(hours=w.LOOKBACK - 1))
                                  & (origins + pd.Timedelta(hours=h) <= frame.index.max())]
                origins = origins[frame.loc[origins, "HtTot"].notna()]
                if not len(origins):
                    continue
                f = predictor.forecast(frame, bid, origins, [h])
                for t, v in zip(f["target_time"], f["y_pred"]):
                    i = idx.get(naive(t))
                    if i is not None:
                        fc[h][i] = round(round(float(v), 1) / 1000.0, 2)
            cursor = end + pd.Timedelta(hours=1)

        def wape(pred):
            num = den = 0.0
            for i in range(n):
                if hours[i] >= replay_start.tz_localize(None) and heat[i] is not None and pred(i) is not None:
                    num += abs(pred(i) - heat[i]); den += heat[i]
            return round(num / den, 4) if den else None

        def mae(pred):
            tot = c = 0
            for i in range(n):
                if hours[i] >= replay_start.tz_localize(None) and heat[i] is not None and pred(i) is not None:
                    tot += abs(pred(i) - heat[i]); c += 1
            return round(tot / c, 2) if c else None

        scores = {str(h): {"wape": wape(lambda i, h=h: fc[h][i]), "mae_kw": mae(lambda i, h=h: fc[h][i]),
                           "seasonal_naive_wape": wape(lambda i: heat[i - 24] if i >= 24 else None)} for h in HORIZONS}
        scores["1"]["persistence_wape"] = wape(lambda i: heat[i - 1] if i >= 1 else None)
        out["buildings"].append({
            "id": bid, "floor_area_m2": float(static.loc[bid, "floor_area"]), "year_built": int(static.loc[bid, "year_of_construction"]),
            "heat_kw": heat, "tout_c": tout, "forecast_kw": {str(h): fc[h] for h in HORIZONS}, "scores_replay": scores})
        print(f"school {bid}: forecast error {scores['1']['wape']} / {scores['6']['wape']} / {scores['24']['wape']} (1/6/24 h)", flush=True)

# ---------------- digital twin: every Monday x school x 1/3/5/7 days ----------------
# A shorter run is exactly the start of a longer one (same start state), so the curves are stored once per
# (school, Monday) from the longest run that fits, every 30 minutes; the summary numbers exist for every length.
if not args.forecast_only:
    params = load_params()
    d0 = replay_first
    while d0.weekday() != 0:
        d0 += dt.timedelta(days=1)
    d0 = dt.datetime(d0.year, d0.month, d0.day)
    twin = {"mondays": [], "runs": {}}
    last_r = None
    while d0 + dt.timedelta(days=1) <= win_last + dt.timedelta(hours=1):
        start = d0.strftime("%Y-%m-%d")
        for bid in building_ids:
            entry = {"days": {}}
            for days in (7, 5, 3, 1):
                end = d0 + dt.timedelta(days=days)
                if end > win_last:                                        # must lie inside the data window
                    continue
                until = min(end + dt.timedelta(hours=PREVIEW_MARGIN_H), win_last)
                lo_ts = pd.Timestamp(d0, tz=TZ)
                rows = rows_of(bid, lo_ts, pd.Timestamp(until, tz=TZ))
                weather = FeedWeather(rows, params.zone.south_facade_ratio)
                r = compare(weather, params, d0, days)
                last_r = r
                temp = r["weather"]["t_outdoor_C"]
                entry["days"][str(days)] = {"legacy": r["runs"]["legacy"]["summary"], "combined": r["runs"]["combined"]["summary"],
                                            "mean_outdoor_c": round(sum(temp) / len(temp), 1)}
                if "series" not in entry:
                    ls, cs = r["runs"]["legacy"]["series"], r["runs"]["combined"]["series"]
                    k = slice(2, None, 3)                                 # every 30 min (series is 10-minute, first point 00:10)
                    entry["series"] = {
                        "legacy_t_air": [round(v, 2) for v in ls["t_air_C"][k]],
                        "combined_t_air": [round(v, 2) for v in cs["t_air_C"][k]],
                        "legacy_kw": [round(a + c, 2) for a, c in zip(ls["radiator_kW"][k], ls["coil_kW"][k])],
                        "combined_kw": [round(a + c, 2) for a, c in zip(cs["radiator_kW"][k], cs["coil_kW"][k])],
                        "outdoor_c": [round(v, 1) for v in temp[k]]}
            if entry["days"]:
                twin["runs"].setdefault(str(bid), {})[start] = entry
        if start in twin["runs"].get(str(building_ids[0]), {}):
            twin["mondays"].append(start)
        print("twin runs from", start, "done", flush=True)
        d0 += dt.timedelta(days=7)
    twin["room"] = {"floor_area_m2": params.zone.floor_area_m2, "setpoint_c": params.comfort.setpoint_C,
                    "purge_trigger_c": params.ventilation.purge_trigger_C, "south_facade_ratio": params.zone.south_facade_ratio}
    twin["note"] = last_r["note"]
    twin["series_step_min"] = 30
    out["twin"] = twin

Path(args.out).write_text(json.dumps(out, separators=(",", ":")))
print("wrote", args.out)
