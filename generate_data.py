#!/usr/bin/env python3
"""
Synthetic data generator for the heating-optimization dashboard proof-of-concept.

Simulates ONE classroom zone (Room 101, School A — 60 m², matching the scope
of the digital-twin parameter research) over a 14-day winter window, under
two controllers:

  - baseline:  fixed schedule, no weather compensation (mirrors "Their problems"
               slide: heats hard from 06:00, overshoots by midday, no pre-heat)
  - optimized: weather-forecast-based Optimal Start/Stop + occupancy-aware
               setback + ventilation heat recovery (FTX retrofit)

The physics is the real room energy-balance contract agreed with the heat-model
teammate (data/room_energy_balance.md):

    C * dT_in/dt = Q_radiator + Q_internal + Q_solar - (T_in - T_out)/R - Q_vent

stepped at the contract's dt=60s resolution and aggregated to hourly rows for
the dashboard. Parameter values come from data/params_research.md and
data/room_energy_balance.md — see the About page for the full sourced/derived/
assumed breakdown of every constant used below. Values still flagged assumed
or unknown in those docs (zone C/R placeholders, fan specific power, solar
irradiance) are clearly placeholders until the heat-model owner and a verified
weather feed replace them.

The dashboard reads strictly from data/dashboard_data.json — regenerate that
file from real data later using the same schema (see data/SCHEMA.md) and
nothing in dashboard.html needs to change.
"""

import json
import math
import random
from datetime import datetime, timedelta

random.seed(42)

# ---------------------------------------------------------------------------
# Simulation setup
# ---------------------------------------------------------------------------

START = datetime(2026, 1, 12, 0, 0)  # a Monday
DAYS = 14
HOURS = DAYS * 24
SUBSTEPS_PER_HOUR = 60   # dt = 60s, per the room-energy-balance contract
DT_S = 3600.0 / SUBSTEPS_PER_HOUR

# Daily occupancy blocks (params_research.md: "typical day, replace with real
# timetable"). Weekdays only.
OCCUPIED_BLOCKS = [((8, 0), (9, 30)), ((9, 45), (11, 30)), ((12, 30), (15, 0))]

def is_occupied(ts: datetime) -> bool:
    if ts.weekday() >= 5:
        return False
    minute_of_day = ts.hour * 60 + ts.minute
    for (sh, sm), (eh, em) in OCCUPIED_BLOCKS:
        if sh * 60 + sm <= minute_of_day < eh * 60 + em:
            return True
    return False

# --- Synthetic outdoor temperature: seasonal Vasteras/Trollhattan-like winter ---
def outdoor_temp(hour_index: float) -> float:
    day = hour_index / 24
    # multi-day cold front passing through, plus daily cycle, plus noise
    base = -4.0 - 5.0 * math.sin(day / 5.0)
    daily_cycle = 3.0 * math.sin((hour_index % 24 - 6) / 24 * 2 * math.pi)
    noise = random.gauss(0, 0.6)
    return base + daily_cycle + noise

# ---------------------------------------------------------------------------
# Classroom + envelope parameters — data/room_energy_balance.md placeholders,
# data/params_research.md zone/gains/ventilation table.
# ---------------------------------------------------------------------------
FLOOR_AREA_M2 = 60.0
WINDOW_AREA_M2 = 10.0
WINDOW_G_VALUE = 0.6          # assumed — typical double-glazing solar transmittance
C_J_PER_K = 2.2e6             # assumed — heat-model placeholder (twin/placeholder_model.py)
R_K_PER_W = 0.025             # assumed — heat-model placeholder (~40 W/K)
AIR_DENSITY_KG_M3 = 1.2       # sourced — physical constant
AIR_CP_J_PER_KGK = 1005.0     # sourced — physical constant
VENT_FLOW_OCCUPIED_L_S = 221.0    # sourced — 8 L/s/person x 26 + 0.35 L/s/m2 x 60 (params_research.md)
VENT_FLOW_UNOCCUPIED_L_S = 0.35 * FLOOR_AREA_M2  # assumed — area-only minimum, demand-controlled down
                                                   # when empty rather than running occupied design flow
                                                   # around the clock (standard DCV practice, not spelled
                                                   # out in either doc but needed for a believable result)
FAN_SFP_W_PER_M3S = 1800.0    # assumed — typical school AHU specific fan power, not in either doc

PUPILS, TEACHERS = 25, 1
SENSIBLE_PUPIL_W, SENSIBLE_ADULT_W = 60.0, 75.0
LIGHTING_W_PER_M2 = 10.0
EQUIPMENT_W = 200.0

RADIATOR_RATED_W = 3000.0     # sourced (user-confirmed) — params_research.md
RADIATOR_LAG_S = 240.0        # assumed — first-order lag time constant (contract says "lagged", no tau given)

SETPOINT_C = 21.0             # sourced — params_research.md comfort setpoint
SETBACK_C = 17.0              # assumed — unoccupied/overnight setback
OVERHEAT_PURGE_C = 24.0       # assumed — params_research.md overheat-purge trigger
OVERHEAT_PURGE_FLOW_MULT = 1.5
COMFORT_LOW, COMFORT_HIGH = 20.0, 26.0   # sourced — setpoint 21 (20-21) / lower 20 / discomfort 26

def q_internal_w(occupied: bool) -> float:
    """Pupils + teacher + lighting + equipment, per room_energy_balance.md."""
    if not occupied:
        return 0.0
    return (PUPILS * SENSIBLE_PUPIL_W + TEACHERS * SENSIBLE_ADULT_W
            + LIGHTING_W_PER_M2 * FLOOR_AREA_M2 + EQUIPMENT_W)

def q_solar_w(ts: datetime) -> float:
    """Q_solar = irradiance * window_area * g_value. Solar irradiance source is
    still an open item (data/params_research.md) — this is a synthetic, low
    winter-sun stand-in, not a verified SMHI/Open-Meteo feed."""
    hour = ts.hour + ts.minute / 60.0
    if 8.0 <= hour <= 16.0:
        irradiance = max(0.0, 120.0 * (1 - abs(hour - 12.0) / 4.0))
    else:
        irradiance = 0.0
    return irradiance * WINDOW_AREA_M2 * WINDOW_G_VALUE

def vent_flow_l_s(occupied: bool, purge: bool) -> float:
    """Demand-controlled ventilation: full design flow (people + area term)
    while occupied, area-only minimum while empty — rather than running the
    occupied design rate around the clock, which would make an empty room
    overnight lose heat to fresh air faster than any radiator could keep up."""
    base = VENT_FLOW_OCCUPIED_L_S if occupied else VENT_FLOW_UNOCCUPIED_L_S
    return base * (OVERHEAT_PURGE_FLOW_MULT if purge else 1.0)

def q_vent_w(indoor_c: float, outdoor_c: float, heat_recovery_eff: float, occupied: bool, purge: bool) -> float:
    """Q_vent = (1 - heat_recovery_eff) * rho * cp * flow * (T_in - T_supply_air),
    per room_energy_balance.md. Overheat purge (indoor > 24C) multiplies flow
    1.5x, per params_research.md."""
    flow_m3_s = vent_flow_l_s(occupied, purge) / 1000.0
    return (1 - heat_recovery_eff) * AIR_DENSITY_KG_M3 * AIR_CP_J_PER_KGK * flow_m3_s * (indoor_c - outdoor_c)

# ---------------------------------------------------------------------------
# Baseline controller — fixed schedule, no weather compensation, no pre-heat,
# no ventilation heat recovery. Mirrors the "Their problems" slide: full-power
# heat from 06:00, no TRV/thermostat nuance, overshoots once occupants/solar/
# equipment gains stack on top of heat already blasted in all morning.
# ---------------------------------------------------------------------------
BASELINE_FROST_FLOOR_FRAC = 0.33  # ~1 kW fixed frost-protection floor — enough to avoid literally
                                   # freezing on the coldest night, still well below a real setpoint
                                   # (not weather-compensated, which is exactly the point)

def baseline_target_w(hour_of_day, weekday, indoor_c):
    if weekday >= 5:
        return BASELINE_FROST_FLOOR_FRAC * RADIATOR_RATED_W  # weekend: frost protection only
    if 6 <= hour_of_day < 17:
        return RADIATOR_RATED_W if indoor_c < OVERHEAT_PURGE_C else 0.0
    return BASELINE_FROST_FLOOR_FRAC * RADIATOR_RATED_W      # overnight: fixed floor, no weather compensation

BASELINE_HEAT_RECOVERY_EFF = 0.0  # older school, no FTX (params_research.md)

# ---------------------------------------------------------------------------
# Optimized controller — weather-forecast-based Optimal Start/Stop +
# occupancy-aware setback + proportional control near the setpoint, running
# on a building with an FTX ventilation heat-recovery retrofit (0.6-0.9 range
# per params_research.md; 0.75 used here) — the two SKR-cited levers this
# feasibility study is actually arguing for, not just a smarter thermostat.
# ---------------------------------------------------------------------------
OPTIMIZED_HEAT_RECOVERY_EFF = 0.75

def optimized_target_w(hour_of_day, weekday, indoor_c, outdoor_c_now, occupied_now, occupied_soon):
    target = SETPOINT_C if (weekday < 5 and occupied_now) else SETBACK_C

    if weekday < 5 and hour_of_day in (5, 6) and occupied_soon and not occupied_now:
        # Optimal Start: begin pre-heating earlier when it's colder outside, so
        # the room just reaches target as occupants arrive, instead of a fixed
        # 06:00 full-power blast regardless of weather.
        cold_factor = max(0.0, (5 - outdoor_c_now) / 15)
        error = SETPOINT_C - indoor_c
        power = min(0.75 * RADIATOR_RATED_W, max(0.0, error * 450 + cold_factor * 500))
        return power

    error = target - indoor_c
    # Proportional band — tapers off near target instead of slamming zero/full,
    # avoiding the overshoot-then-purge cycle.
    return min(RADIATOR_RATED_W, max(0.0, error * 650))

# ---------------------------------------------------------------------------
# Run simulation — dt = 60s per the room-energy-balance contract, aggregated
# to hourly rows (the dashboard's existing schema) at the end of each hour.
# ---------------------------------------------------------------------------

rows = []
baseline_indoor = 19.0
optimized_indoor = 19.0
base_rad_w = opt_rad_w = 0.0   # lagged radiator output, carried across substeps

for h in range(HOURS):
    ts = START + timedelta(hours=h)
    outdoor_hour = outdoor_temp(h)
    occupied = is_occupied(ts)
    occupied_soon = any(is_occupied(ts + timedelta(minutes=m)) for m in (30, 60))

    base_energy_wh = opt_energy_wh = 0.0
    base_purge_wh = opt_purge_wh = 0.0
    base_peak_w = opt_peak_w = 0.0

    for sub in range(SUBSTEPS_PER_HOUR):
        ts_sub = ts + timedelta(seconds=sub * DT_S)
        outdoor_sub = outdoor_temp(h + sub / SUBSTEPS_PER_HOUR)
        occ_sub = is_occupied(ts_sub)
        q_int = q_internal_w(occ_sub)
        q_sol = q_solar_w(ts_sub)

        # --- baseline substep ---
        base_target = baseline_target_w(ts.hour, ts.weekday(), baseline_indoor)
        base_rad_w += (base_target - base_rad_w) * (DT_S / RADIATOR_LAG_S)
        base_purge = baseline_indoor > OVERHEAT_PURGE_C
        q_vent_b = q_vent_w(baseline_indoor, outdoor_sub, BASELINE_HEAT_RECOVERY_EFF, occ_sub, base_purge)
        d_base = (base_rad_w + q_int + q_sol - (baseline_indoor - outdoor_sub) / R_K_PER_W - q_vent_b) / C_J_PER_K * DT_S
        baseline_indoor += d_base
        base_energy_wh += base_rad_w * DT_S / 3600.0
        base_peak_w = max(base_peak_w, base_rad_w)
        if base_purge:
            extra_flow_m3s = vent_flow_l_s(occ_sub, False) * (OVERHEAT_PURGE_FLOW_MULT - 1.0) / 1000.0
            base_purge_wh += extra_flow_m3s * FAN_SFP_W_PER_M3S * DT_S / 3600.0

        # --- optimized substep ---
        opt_target = optimized_target_w(ts.hour, ts.weekday(), optimized_indoor, outdoor_sub, occ_sub, occupied_soon)
        opt_rad_w += (opt_target - opt_rad_w) * (DT_S / RADIATOR_LAG_S)
        opt_purge = optimized_indoor > OVERHEAT_PURGE_C
        q_vent_o = q_vent_w(optimized_indoor, outdoor_sub, OPTIMIZED_HEAT_RECOVERY_EFF, occ_sub, opt_purge)
        d_opt = (opt_rad_w + q_int + q_sol - (optimized_indoor - outdoor_sub) / R_K_PER_W - q_vent_o) / C_J_PER_K * DT_S
        optimized_indoor += d_opt
        opt_energy_wh += opt_rad_w * DT_S / 3600.0
        opt_peak_w = max(opt_peak_w, opt_rad_w)
        if opt_purge:
            extra_flow_m3s = vent_flow_l_s(occ_sub, False) * (OVERHEAT_PURGE_FLOW_MULT - 1.0) / 1000.0
            opt_purge_wh += extra_flow_m3s * FAN_SFP_W_PER_M3S * DT_S / 3600.0

    baseline_indoor = round(baseline_indoor, 2)
    optimized_indoor = round(optimized_indoor, 2)

    rows.append({
        "timestamp": ts.isoformat(),
        "outdoor_temp_c": round(outdoor_hour, 1),
        "occupied": occupied,
        "baseline_indoor_temp_c": baseline_indoor,
        "baseline_heating_power_kw": round(base_peak_w / 1000.0, 2),
        "baseline_heating_energy_kwh": round(base_energy_wh / 1000.0, 3),
        "baseline_ventilation_purge_kwh": round(base_purge_wh / 1000.0, 3),
        "baseline_energy_kwh": round((base_energy_wh + base_purge_wh) / 1000.0, 3),
        "optimized_indoor_temp_c": optimized_indoor,
        "optimized_heating_power_kw": round(opt_peak_w / 1000.0, 2),
        "optimized_heating_energy_kwh": round(opt_energy_wh / 1000.0, 3),
        "optimized_ventilation_purge_kwh": round(opt_purge_wh / 1000.0, 3),
        "optimized_energy_kwh": round((opt_energy_wh + opt_purge_wh) / 1000.0, 3),
    })

# ---------------------------------------------------------------------------
# Derived summary stats (dashboard can also compute these client-side, but
# shipping them precomputed keeps the dashboard simple and gives the schema
# an explicit "summary" contract for the real-data version to match).
# ---------------------------------------------------------------------------

def comfort_violations(rows, key):
    count = 0
    for r in rows:
        if not r["occupied"]:
            continue
        t = r[key]
        if t < COMFORT_LOW or t > COMFORT_HIGH:
            count += 1
    return count

total_baseline_kwh = round(sum(r["baseline_energy_kwh"] for r in rows), 1)
total_optimized_kwh = round(sum(r["optimized_energy_kwh"] for r in rows), 1)
pct_savings = round((1 - total_optimized_kwh / total_baseline_kwh) * 100, 1)

peak_baseline = round(max(r["baseline_heating_power_kw"] for r in rows), 1)
peak_optimized = round(max(r["optimized_heating_power_kw"] for r in rows), 1)
peak_reduction_pct = round((1 - peak_optimized / peak_baseline) * 100, 1)

summary = {
    "total_energy_baseline_kwh": total_baseline_kwh,
    "total_energy_optimized_kwh": total_optimized_kwh,
    "energy_savings_pct": pct_savings,
    "peak_demand_baseline_kw": peak_baseline,
    "peak_demand_optimized_kw": peak_optimized,
    "peak_demand_reduction_pct": peak_reduction_pct,
    "comfort_violations_baseline": comfort_violations(rows, "baseline_indoor_temp_c"),
    "comfort_violations_optimized": comfort_violations(rows, "optimized_indoor_temp_c"),
}

# ---------------------------------------------------------------------------
# Control panel — per-building snapshot for "today" (latest hour in the run).
# Hand-specified rather than derived, so the demo tells a clear story: most
# buildings are fine, one or two need attention, one is on manual override.
# Replace this block entirely once a real building list / BMS export exists —
# see data/SCHEMA.md for the exact shape the dashboard expects.
# ---------------------------------------------------------------------------

today_outdoor_c = rows[-1]["outdoor_temp_c"]

def room_status(temp_c, target_c, tolerance=1.8):
    delta = temp_c - target_c
    if delta > tolerance:
        return "high"
    if delta < -tolerance:
        return "low"
    return "normal"

def building(id_, code, name, kind, target_c, indoor_c, mode, minutes_ago,
             room_names, room_temps, co2_ppm, energy_kw, ahu_count=1):
    delta = indoor_c - target_c
    if abs(delta) <= 0.5:
        status = "idle"
    elif delta < 0:
        status = "heating"
    else:
        status = "idle"
    attention = delta <= -1.5
    heater_on = status == "heating" or (mode == "manual" and delta <= 0)

    rooms = []
    for i, (rname, t) in enumerate(zip(room_names, room_temps)):
        rooms.append({
            "name": rname,
            "temp_c": t,
            "occupied": i % 3 != 2,
            "status": room_status(t, target_c),
        })

    ahu_running = status == "heating"
    fan_pct = 78 if ahu_running else 12
    # Heating AHU: supply air is blown in hot and gives up heat to the room,
    # so supply > return > room temp drops as it crosses the space.
    supply_c = round(indoor_c + 5.0, 1) if ahu_running else round(indoor_c - 0.3, 1)
    return_c = round(indoor_c + 0.3, 1) if ahu_running else round(indoor_c - 0.1, 1)
    ahus = []
    for i in range(ahu_count):
        ahus.append({
            "id": "AHU-{:02d}".format(i + 1),
            "running": ahu_running,
            "fan_pct": fan_pct,
            "supply_c": supply_c,
            "return_c": return_c,
        })

    return {
        "id": id_,
        "code": code,
        "name": name,
        "type": kind,
        "target_c": target_c,
        "indoor_c": indoor_c,
        "outdoor_c": today_outdoor_c,
        "mode": mode,          # "auto" | "manual"
        "status": status,      # "heating" | "idle"
        "heater_on": heater_on,
        "attention": attention,
        "updated_min_ago": minutes_ago,
        "co2_ppm": co2_ppm,
        "energy_kw": energy_kw,
        "rooms": rooms,
        "ahus": ahus,
    }

buildings = [
    building("sch-a", "SCH-A", "School A — Kronogården",      "School",          21.0, 21.2, "auto",   1,
              ["Room 101", "Room 102", "Room 103", "Room 104"], [21.0, 21.4, 21.1, 21.3],
              co2_ppm=520, energy_kw=38, ahu_count=2),
    building("sch-b", "SCH-B", "School B — Sylte",             "School",          21.0, 20.8, "auto",   3,
              ["Room 201", "Room 202", "Room 203", "Room 204"], [20.6, 21.0, 20.9, 20.7],
              co2_ppm=540, energy_kw=41, ahu_count=2),
    building("sch-c", "SCH-C", "School C — Kroppkärr",         "School",          21.0, 22.6, "auto",   2,
              ["Room 301", "Room 302", "Room 303", "Room 304"], [22.3, 22.6, 22.4, 22.5],
              co2_ppm=500, energy_kw=22, ahu_count=2),
    building("sch-d", "SCH-D", "School D — Sjuntorp",          "School",          21.0, 21.0, "auto",   5,
              ["Room 401", "Room 402", "Room 403", "Room 404"], [20.9, 21.1, 21.0, 21.0],
              co2_ppm=510, energy_kw=35, ahu_count=2),
    building("sch-e", "SCH-E", "School E — Upphärad",          "School",          21.0, 18.9, "manual", 1,
              ["Room 501", "Room 502", "Room 503", "Room 504"], [18.2, 18.9, 20.6, 21.0],
              co2_ppm=560, energy_kw=52, ahu_count=2),
    building("ind-1", "IND-1", "Industrial Hall 1 — Stallbacka","Industrial",     17.0, 17.4, "auto",   4,
              ["Bay 1", "Bay 2", "Bay 3"], [17.1, 17.6, 17.5],
              co2_ppm=460, energy_kw=94, ahu_count=3),
    building("ind-2", "IND-2", "Industrial Hall 2 — Nordre Älv","Industrial",     17.0, 15.1, "auto",   2,
              ["Bay 1", "Bay 2", "Bay 3"], [14.5, 15.0, 16.8],
              co2_ppm=470, energy_kw=101, ahu_count=3),
    building("spo-1", "SPO-1", "Sports Hall — Edsborg",        "Sports facility", 18.0, 18.3, "auto",   6,
              ["Main Hall", "Changing Room A", "Changing Room B"], [18.1, 18.6, 18.4],
              co2_ppm=610, energy_kw=47, ahu_count=2),
    building("care-1","CARE-1","Health Center — Kronan",       "Health center",   22.0, 21.6, "auto",   1,
              ["Waiting Room", "Treatment 1", "Treatment 2", "Office"], [21.4, 21.8, 21.7, 21.5],
              co2_ppm=490, energy_kw=55, ahu_count=2),
    building("off-1", "OFF-1", "Office — Åkerssjövägen",       "Office",          21.0, 21.1, "auto",   3,
              ["Open Plan", "Meeting Room", "Reception"], [21.0, 21.3, 21.0],
              co2_ppm=450, energy_kw=19, ahu_count=1),
]

# ---------------------------------------------------------------------------
# Heat price + cost summary — from the teammate's classroom-twin parameter
# research (see data/params_research.md). 1.10-1.35 SEK/kWh; we display the
# midpoint and keep the range alongside it so the KPI reads as an estimate,
# not false precision.
# ---------------------------------------------------------------------------
HEAT_PRICE_LOW_SEK, HEAT_PRICE_HIGH_SEK = 1.10, 1.35
heat_price_mid = (HEAT_PRICE_LOW_SEK + HEAT_PRICE_HIGH_SEK) / 2

summary["energy_cost_baseline_sek"] = round(total_baseline_kwh * heat_price_mid, 0)
summary["energy_cost_optimized_sek"] = round(total_optimized_kwh * heat_price_mid, 0)
summary["energy_cost_savings_sek"] = round(
    summary["energy_cost_baseline_sek"] - summary["energy_cost_optimized_sek"], 0
)

# ---------------------------------------------------------------------------
# Validation benchmarks — published Swedish school energy-use figures to
# sanity-check this model's output against, not numbers the simulation
# produces itself.
# ---------------------------------------------------------------------------
benchmarks = [
    {
        "label": "Average school heat use (2006)",
        "value": "152 kWh/m²·yr",
        "source": "SKR 2011, citing STIL2",
    },
    {
        "label": "Average school total energy",
        "value": "213 kWh/m²·yr",
        "source": "SKR 2011",
    },
    {
        "label": "Operations optimisation saving",
        "value": "10–30%",
        "source": "SKR 2011",
    },
    {
        "label": "Schools with air-climate problems",
        "value": "~75% (temperature most common)",
        "source": "SKR 2011",
    },
    {
        "label": "Implied classroom heat use (60 m²)",
        "value": "≈9.1 MWh/yr",
        "source": "Derived: 152 kWh/m²·yr × 60 m²",
    },
]

# ---------------------------------------------------------------------------
# Model parameters — the classroom digital-twin parameter research a
# teammate brought in (params_research.md v0.1, room_energy_balance.md v0.1).
# This is the data the heat model (owned separately) runs on; the dashboard
# just surfaces it for transparency/review. confidence: sourced | derived |
# assumed | unknown.
# ---------------------------------------------------------------------------
model_parameters = [
    {"group": "Zone", "parameter": "Floor area / height / volume", "value": "60 m² / 3.0 m / 180 m³", "confidence": "assumed", "source": "engineering default"},
    {"group": "Zone", "parameter": "Window area, orientation", "value": "10 m² (6–14), south", "confidence": "assumed", "source": "engineering default"},
    {"group": "Zone", "parameter": "Solar shading", "value": "none (~3/4 of schools lack it)", "confidence": "sourced", "source": "SKR 2011"},
    {"group": "Occupancy", "parameter": "Pupils + teacher", "value": "25 (20–30) + 1", "confidence": "assumed", "source": "engineering default"},
    {"group": "Occupancy", "parameter": "School days per year", "value": "165", "confidence": "sourced", "source": "SKR 2011"},
    {"group": "Occupancy", "parameter": "Daily blocks", "value": "08:00–09:30, 09:45–11:30, 12:30–15:00", "confidence": "assumed", "source": "typical day — replace with real timetable"},
    {"group": "Gains", "parameter": "Sensible heat per pupil / adult", "value": "60 W (50–70) / 75 W (70–90)", "confidence": "assumed", "source": "check EN 16798-1 / ISO 7730"},
    {"group": "Gains", "parameter": "CO₂ per child", "value": "404 mg/min", "confidence": "sourced", "source": "classroom CO₂ study (secondary), essd-487"},
    {"group": "Gains", "parameter": "Lighting", "value": "10 W/m² (8–20)", "confidence": "derived", "source": "SKR 2011 Risbroskolan: ~1200 W/classroom, −55% after retrofit"},
    {"group": "Gains", "parameter": "Teacher PC + projector", "value": "200 W (100–300)", "confidence": "assumed", "source": "engineering default"},
    {"group": "Ventilation", "parameter": "Airflow", "value": "8 L/s/person + 0.35 L/s/m² ≈ 221 L/s (~4.4 ACH)", "confidence": "derived", "source": "AIVC 1992 Växjö; SKR 2011 (BBR table)"},
    {"group": "Ventilation", "parameter": "Operating hours", "value": "3500 h/yr avg, 1320–2000 h needed", "confidence": "sourced", "source": "SKR 2011"},
    {"group": "Ventilation", "parameter": "Heat recovery", "value": "0 (older school) or 0.6–0.9 (FTX)", "confidence": "sourced", "source": "SKR 2011"},
    {"group": "Ventilation", "parameter": "Overheat purge", "value": "triggers at 24 °C, flow ×1.5", "confidence": "assumed", "source": "placeholder for \"system fighting\" effect"},
    {"group": "Comfort", "parameter": "Setpoint / lower / discomfort", "value": "21 °C (20–21) / 20 °C / 26 °C", "confidence": "sourced", "source": "SKR 2011"},
    {"group": "Comfort", "parameter": "Cost per °C", "value": "~5% of heating cost", "confidence": "sourced", "source": "SKR 2011"},
    {"group": "Heating", "parameter": "Supply / return at design outdoor temp", "value": "64 °C / 42 °C at −16 °C (mean of 109 systems)", "confidence": "sourced", "source": "Chalmers radiator survey (Jangsten 2017)"},
    {"group": "Heating", "parameter": "Supply when outdoor ≥ 5 °C", "value": "≤ 55 °C", "confidence": "sourced", "source": "Jangsten 2017"},
    {"group": "Heating", "parameter": "Radiator design supply", "value": "80 °C pre-1980; ≤ 60 °C post-1982", "confidence": "sourced", "source": "Jangsten 2017"},
    {"group": "Heating", "parameter": "Radiator rated output", "value": "3 kW (2–4.5), user-confirmed", "confidence": "assumed", "source": "~50 W/m² — heat-loss owner to verify"},
    {"group": "Heating", "parameter": "Heat price", "value": "1.10–1.35 SEK/kWh", "confidence": "sourced", "source": "team's own background doc"},
    {"group": "Actuator", "parameter": "Smart TRV", "value": "Zigbee 3.0, M30×1.5, 8–28 °C, PI control, battery ~2 yrs", "confidence": "sourced", "source": "product pages (Shelly BLU TRV V2, Salus)"},
    {"group": "Actuator", "parameter": "TRV price", "value": "~26–58 GBP retail; mechanical retrofit 100–300 SEK", "confidence": "sourced", "source": "retailers; SKR 2011"},
    {"group": "Actuator", "parameter": "Time to move full stroke", "value": "not found", "confidence": "unknown", "source": "keep configurable"},
    {"group": "Sensor", "parameter": "CO₂ (SCD41)", "value": "±(40 ppm + 5%), 400–5000 ppm", "confidence": "sourced", "source": "Sensirion via retailer pages"},
    {"group": "Sensor", "parameter": "Temperature", "value": "~±0.4–0.8 °C (sources differ); SHT4x suggested", "confidence": "sourced", "source": "esp32.co.uk"},
    {"group": "Weather", "parameter": "Source", "value": "SMHI Open Data, hourly, CC BY 4.0, no key", "confidence": "sourced", "source": "SMHI / wetterdienst docs"},
    {"group": "Weather", "parameter": "Nearest station", "value": "Trollhättan–Vänersborg Airport (58.314N, 12.347E) — SMHI id not yet resolved", "confidence": "sourced", "source": "meteo365 METAR page"},
    {"group": "Heat model", "parameter": "Zone heat capacity (C)", "value": "2.2 MJ/K", "confidence": "assumed", "source": "heat-model placeholder, twin/placeholder_model.py"},
    {"group": "Heat model", "parameter": "Envelope resistance (R)", "value": "0.025 K/W (~40 W/K)", "confidence": "assumed", "source": "heat-model placeholder — owner to define from construction"},
    {"group": "Heat model", "parameter": "Window solar transmittance (g-value)", "value": "0.6", "confidence": "assumed", "source": "typical double glazing, engineering default"},
    {"group": "Heat model", "parameter": "Air density / specific heat", "value": "1.2 kg/m³ / 1005 J/(kg·K)", "confidence": "sourced", "source": "physical constants"},
    {"group": "Heat model", "parameter": "Radiator first-order lag", "value": "~240 s time constant", "confidence": "assumed", "source": "contract specifies \"lagged\", no τ given"},
    {"group": "Heat model", "parameter": "Ventilation fan specific power (purge)", "value": "~1.8 kW per m³/s", "confidence": "assumed", "source": "typical school AHU SFP — not in either research doc"},
]

open_items = [
    "Zone size, pupils, gains per person, schedule, radiator size and overheat-purge numbers are placeholders — nothing in the source set pins them down for a Trollhättan school.",
    "SMHI station id for Trollhättan is not resolved yet.",
    "Solar radiation source is not verified (SMHI STRÅNG candidate, Open-Meteo fallback) — the simulated Q_solar term is a synthetic winter-sun stand-in until that's wired up.",
    "Design outdoor temperature (−16 °C) comes from the Gothenburg survey — confirm the Trollhättan value.",
    "TRV motion speed and heat meter specs were not found.",
    "R and C (envelope resistance/heat capacity) are heat-model placeholders — the model owner still needs to define them from the actual building construction.",
    "Whether the heat model or the twin owns Q_solar and Q_vent is undecided per the room-energy-balance contract — agree before the real model replaces this placeholder.",
    "Most Swedish school figures trace back to one 2011 SKR report summarising a 2006 survey — cite the originals (Energimyndigheten STIL2, Jangsten 2017) in the final report.",
]

output = {
    "meta": {
        "network": "Kraftstaden district network",
        "data_source": "Demo dataset — see data/SCHEMA.md to connect a live export",
        "period_start": rows[0]["timestamp"],
        "period_end": rows[-1]["timestamp"],
        "comfort_band_c": [COMFORT_LOW, COMFORT_HIGH],
        "heat_price_sek_per_kwh": [HEAT_PRICE_LOW_SEK, HEAT_PRICE_HIGH_SEK],
        "scenario_scope": (
            "Simulated for one classroom zone (Room 101, 60 m²) using the real room "
            "energy-balance equation — not a whole-building figure. “Optimized” "
            "combines Optimal Start/Stop scheduling with a ventilation heat-recovery "
            "(FTX) retrofit at 75% efficiency; the baseline has neither."
        ),
        "generated_at": datetime.now().isoformat(),
    },
    "summary": summary,
    "timeseries": rows,
    "buildings": buildings,
    "benchmarks": benchmarks,
    "model_parameters": model_parameters,
    "open_items": open_items,
}

# ---------------------------------------------------------------------------
# PART 2 — overlay the real digital-twin data.
#
# A teammate's digital twin (SINTEF-style room energy-balance simulation)
# produced a full simulated year (2025) of a real classroom — Room 101,
# 60 m², Trollhättan — under four control scenarios, driven by real SMHI
# weather (Såtenäs station, since Vänersborg only has quarterly-hour
# coverage). That file (data/twin_dashboard.json, format 1.0 — see
# data/dashboard-format.md) replaces this script's own synthetic physics as
# the dashboard's source of truth: PART 1 above still runs (it's useful as a
# fallback/reference and still supplies the 9 other illustrative buildings),
# but everything below overwrites it with real numbers wherever the twin's
# data covers it.
#
# Binary scenario mapping (per product decision — the twin actually has 4):
#   baseline  = "legacy-faults-as-is" ("Today": stuck-open valves on half the
#               radiators, a biased/laggy outdoor sensor, a manual morning
#               boost — today's actual, undocumented behavior)
#   optimized = "optimized-faults-none" (coordinated smart-valve control with
#               those faults fixed — the proposed retrofit)
# The other two scenarios ("Faults fixed" alone, "Smart control, old valves")
# aren't charted, but their totals are kept in model_parameters/open_items
# context so nothing from the real file is silently dropped.
# ---------------------------------------------------------------------------
with open("data/twin_dashboard.json") as f:
    twin = json.load(f)

TWIN_BASELINE_ID = "legacy-faults-as-is"
TWIN_OPTIMIZED_ID = "optimized-faults-none"
twin_hourly = twin["series"]["hourly"]
twin_times = twin_hourly["times"]
twin_shared = twin_hourly["shared"]
twin_base = twin_hourly["scenarios"][TWIN_BASELINE_ID]
twin_opt = twin_hourly["scenarios"][TWIN_OPTIMIZED_ID]

twin_rows = []
for i, ts in enumerate(twin_times):
    occupied = (twin_shared["occupants_max"][i] or 0) > 0
    base_heat_kwh = twin_base["total_heat_kWh"][i]
    base_fan_kwh = twin_base["fan_electricity_kWh"][i]
    opt_heat_kwh = twin_opt["total_heat_kWh"][i]
    opt_fan_kwh = twin_opt["fan_electricity_kWh"][i]
    twin_rows.append({
        "timestamp": ts + ":00",
        "outdoor_temp_c": twin_shared["t_outdoor_C"][i],
        "occupied": occupied,
        "baseline_indoor_temp_c": twin_base["t_air_C"][i],
        "baseline_heating_power_kw": round((twin_base["q_radiator_W"][i] + twin_base["q_ahu_coil_W"][i]) / 1000, 3),
        "baseline_heating_energy_kwh": base_heat_kwh,
        "baseline_ventilation_purge_kwh": base_fan_kwh,
        "baseline_energy_kwh": round(base_heat_kwh + base_fan_kwh, 4),
        "baseline_cost_sek": twin_base["cost_total_SEK"][i],
        "optimized_indoor_temp_c": twin_opt["t_air_C"][i],
        "optimized_heating_power_kw": round((twin_opt["q_radiator_W"][i] + twin_opt["q_ahu_coil_W"][i]) / 1000, 3),
        "optimized_heating_energy_kwh": opt_heat_kwh,
        "optimized_ventilation_purge_kwh": opt_fan_kwh,
        "optimized_energy_kwh": round(opt_heat_kwh + opt_fan_kwh, 4),
        "optimized_cost_sek": twin_opt["cost_total_SEK"][i],
    })

twin_base_total_kwh = sum(r["baseline_energy_kwh"] for r in twin_rows)
twin_opt_total_kwh = sum(r["optimized_energy_kwh"] for r in twin_rows)
twin_base_peak_kw = max(r["baseline_heating_power_kw"] for r in twin_rows)
twin_opt_peak_kw = max(r["optimized_heating_power_kw"] for r in twin_rows)
twin_base_viol = sum(1 for r in twin_rows if r["occupied"] and not (COMFORT_LOW <= r["baseline_indoor_temp_c"] <= COMFORT_HIGH))
twin_opt_viol = sum(1 for r in twin_rows if r["occupied"] and not (COMFORT_LOW <= r["optimized_indoor_temp_c"] <= COMFORT_HIGH))
twin_base_cost = sum(r["baseline_cost_sek"] for r in twin_rows)
twin_opt_cost = sum(r["optimized_cost_sek"] for r in twin_rows)

output["timeseries"] = twin_rows
output["summary"] = {
    "total_energy_baseline_kwh": round(twin_base_total_kwh, 1),
    "total_energy_optimized_kwh": round(twin_opt_total_kwh, 1),
    "energy_savings_pct": round((1 - twin_opt_total_kwh / twin_base_total_kwh) * 100, 1) if twin_base_total_kwh else 0,
    "peak_demand_baseline_kw": round(twin_base_peak_kw, 2),
    "peak_demand_optimized_kw": round(twin_opt_peak_kw, 2),
    "peak_demand_reduction_pct": round((1 - twin_opt_peak_kw / twin_base_peak_kw) * 100, 1) if twin_base_peak_kw else 0,
    "comfort_violations_baseline": twin_base_viol,
    "comfort_violations_optimized": twin_opt_viol,
    "energy_cost_baseline_sek": round(twin_base_cost, 0),
    "energy_cost_optimized_sek": round(twin_opt_cost, 0),
    "energy_cost_savings_sek": round(twin_base_cost - twin_opt_cost, 0),
}

output["meta"]["data_source"] = (
    "Digital twin simulation (room energy-balance model, heat model v" +
    twin["assumptions"]["params_version"] + "), simulated — not measured. Driven by real SMHI "
    "weather (" + twin["weather"]["temperature"]["station_name"] + " station, " +
    str(twin["weather"]["temperature"]["distance_km"]) + " km away, CC BY 4.0) for a full year, " +
    str(twin["period"]["from"][:4]) + ". See data/dashboard-format.md."
)
output["meta"]["period_start"] = twin_rows[0]["timestamp"]
output["meta"]["period_end"] = twin_rows[-1]["timestamp"]
output["meta"]["comfort_band_c"] = [20.0, 26.0]  # twin's own lesson_too_cold/too_hot thresholds
output["meta"]["heat_price_sek_per_kwh"] = [
    twin["assumptions"]["prices_SEK_per_kWh"]["heat"],
    twin["assumptions"]["prices_SEK_per_kWh"]["heat"],
]
output["meta"]["electricity_price_sek_per_kwh"] = twin["assumptions"]["prices_SEK_per_kWh"]["electricity"]
output["meta"]["scenario_scope"] = (
    "Full year (" + str(twin["period"]["from"][:4]) + ") digital-twin simulation of one real classroom "
    "(Room 101, " + str(twin["building"]["floor_area_m2"]) + " m², " + str(twin["building"]["pupils"]) +
    " pupils + " + str(twin["building"]["teachers"]) + " teacher) — not a whole-building figure. "
    "“Today” (baseline) is the building's actual control faults: " +
    str(int(twin["assumptions"]["baseline_faults"]["trv_stuck_open_share"] * 100)) +
    "% of radiator valves stuck open, an outdoor sensor biased " +
    str(twin["assumptions"]["baseline_faults"]["outdoor_sensor_bias_K"]) + " K low, and a manual " +
    str(twin["assumptions"]["baseline_faults"]["morning_boost_K"]) + " K morning boost. "
    "“Smart control” is coordinated valve control with those faults fixed — the proposed retrofit. "
    "Both scenarios share the same weather and occupancy, so the comparison is apples-to-apples."
)

# School A (sch-a, index 0 above) becomes the real classroom this twin models —
# pick a recent, ordinary occupied hour under the optimized/"Smart control"
# scenario as its Control-panel snapshot (what the room would look like day to
# day once the retrofit is in place), rather than the illustrative numbers
# PART 1 invented for it.
rep_i = None
for i in range(len(twin_times) - 1, max(0, len(twin_times) - 24 * 45), -1):
    if (twin_shared["occupants_max"][i] or 0) > 0:
        rep_i = i
        break
if rep_i is not None:
    rep_indoor = round(twin_opt["t_air_C"][rep_i], 1)
    rep_outdoor = round(twin_shared["t_outdoor_C"][rep_i], 1)
    rep_target = 21.0  # standard classroom comfort target (comfort band 20-26 C)
    sch_a = buildings[0]
    sch_a["name"] = "School A — Kronogården (Room 101, digital twin)"
    sch_a["target_c"] = rep_target
    sch_a["indoor_c"] = rep_indoor
    sch_a["outdoor_c"] = rep_outdoor
    sch_a["status"] = "heating" if rep_indoor < rep_target - 0.5 else "idle"
    sch_a["heater_on"] = sch_a["status"] == "heating"
    sch_a["attention"] = abs(rep_indoor - rep_target) > 1.8
    sch_a["updated_min_ago"] = 1
    sch_a["energy_kw"] = round((twin_opt["q_radiator_W"][rep_i] + twin_opt["q_ahu_coil_W"][rep_i]) / 1000, 2)
    sch_a["rooms"] = [{
        "name": "Room 101",
        "temp_c": rep_indoor,
        "occupied": True,
        "status": room_status(rep_indoor, rep_target),
    }]
    sch_a["ahus"] = [{
        "id": "AHU-101",
        "running": sch_a["heater_on"],
        "fan_pct": 78 if sch_a["heater_on"] else 12,
        "supply_c": round(rep_indoor + 5.0, 1) if sch_a["heater_on"] else round(rep_indoor - 0.3, 1),
        "return_c": round(rep_indoor + 0.3, 1) if sch_a["heater_on"] else round(rep_indoor - 0.1, 1),
    }]
output["buildings"] = buildings

# A real validation point: the twin's own baseline heat use per m² against
# the same SKR 2011 figure the other benchmark rows cite.
twin_annual_kwh_m2 = round(
    twin["totals"][TWIN_BASELINE_ID]["total_heat_kWh"] / twin["building"]["floor_area_m2"], 1
)
benchmarks.append({
    "label": "This twin — Today (baseline), Room 101",
    "value": f"{twin_annual_kwh_m2} kWh/m²·yr",
    "source": "Digital twin simulation, 2025 (data/twin_dashboard.json)",
})

model_parameters.extend([
    {"group": "Twin — zone", "parameter": "Floor area / window area / orientation", "value": f"{twin['building']['floor_area_m2']} m² / {twin['building']['window_area_m2']} m² / {twin['building']['window_orientation']}", "confidence": "sourced", "source": "data/twin_dashboard.json (building)"},
    {"group": "Twin — occupancy", "parameter": "Pupils + teacher", "value": f"{twin['building']['pupils']} + {twin['building']['teachers']}", "confidence": "sourced", "source": "data/twin_dashboard.json (building)"},
    {"group": "Twin — weather", "parameter": "Outdoor temperature station", "value": f"{twin['weather']['temperature']['station_name']} (id {twin['weather']['temperature']['station_id']}, {twin['weather']['temperature']['distance_km']} km away, {twin['weather']['temperature']['coverage']*100:.1f}% coverage)", "confidence": "sourced", "source": "SMHI metobs, via data/twin_dashboard.json (weather)"},
    {"group": "Twin — weather", "parameter": "Solar irradiance", "value": twin["weather"]["solar"]["source"], "confidence": "sourced", "source": "data/twin_dashboard.json (weather)"},
    {"group": "Twin — prices", "parameter": "Heat / electricity price", "value": f"{twin['assumptions']['prices_SEK_per_kWh']['heat']} / {twin['assumptions']['prices_SEK_per_kWh']['electricity']} SEK/kWh", "confidence": "sourced", "source": "data/twin_dashboard.json (assumptions)"},
    {"group": "Twin — baseline faults", "parameter": "Stuck-open valves / sensor bias / morning boost", "value": f"{twin['assumptions']['baseline_faults']['trv_stuck_open_share']*100:.0f}% stuck / {twin['assumptions']['baseline_faults']['outdoor_sensor_bias_K']} K bias / +{twin['assumptions']['baseline_faults']['morning_boost_K']} K boost", "confidence": "sourced", "source": "data/twin_dashboard.json (assumptions.baseline_faults) — this is today's documented, undiagnosed behavior, not a hypothetical"},
    {"group": "Twin — legacy operation", "parameter": "Heating / ventilation schedule today", "value": f"heat {twin['assumptions']['legacy_operation']['heating_start']}–{twin['assumptions']['legacy_operation']['heating_end']}, vent {twin['assumptions']['legacy_operation']['ventilation_start']}–{twin['assumptions']['legacy_operation']['ventilation_end']}", "confidence": "sourced", "source": "data/twin_dashboard.json (assumptions.legacy_operation)"},
])

open_items.append(
    "The twin file (data/twin_dashboard.json) also includes daily/weekly/monthly pre-aggregated "
    "series and two more scenarios (\"Faults fixed\" alone, \"Smart control on old valves\") that "
    "this dashboard doesn't chart yet — see data/dashboard-format.md for the full shape if a "
    "resolution switcher or a 4-way scenario comparison gets built later."
)
open_items.append(
    "The heat-usage forecast card is illustrative only — generated from the twin's own totals as a "
    "stand-in, not real model output. The actual model (features, horizons, training data) is "
    "described by a teammate but not yet trained/connected; swap data[\"forecast\"] for real output "
    "once it exists."
)
output["model_parameters"] = model_parameters
output["open_items"] = open_items

# ---------------------------------------------------------------------------
# Forecast (preview) — a teammate is training a short-horizon heat-usage
# model ("Oslo dataset": ~200k cleaned hourly rows, from 2.2M raw, across 48
# Oslo school buildings — SINTEF COFACTOR-SBHUB, Lien et al., Data in Brief
# 2025) but hasn't shared trained output yet. These numbers are NOT model
# predictions — they're derived from the twin's own recent totals so the UI
# slot looks plausible, and are labeled "illustrative" everywhere they render.
# ---------------------------------------------------------------------------
recent_opt_rows = twin_rows[-168:]  # last 7 days of the twin's optimized scenario
recent_avg_kwh = sum(r["optimized_heating_energy_kwh"] for r in recent_opt_rows) / len(recent_opt_rows)
output["forecast"] = {
    "status": "illustrative",
    "status_note": (
        "Illustrative placeholder, not model output. The forecasting model is still being trained "
        "and tuned by the team — these numbers are derived from the twin's own recent totals so the "
        "UI slot is grounded in real magnitudes, not from a trained predictor."
    ),
    "trained_on": (
        "~200k cleaned hourly readings (from 2.2M raw) across 48 Oslo school buildings — "
        "SINTEF COFACTOR-SBHUB Oslo dataset (Lien et al., Data in Brief, 2025)"
    ),
    "features": ["Time of day / day of week", "Past heat input (lagged)", "Outdoor temperature", "Wind speed", "Wind direction", "Solar irradiance"],
    "history_windows": ["Past 24 h", "Past 168 h (1 week)"],
    "horizons": [
        {"label": "Next 1 h", "hours": 1, "predicted_kwh": round(recent_avg_kwh * 1, 2)},
        {"label": "Next 6 h", "hours": 6, "predicted_kwh": round(recent_avg_kwh * 6, 2)},
        {"label": "Next 24 h", "hours": 24, "predicted_kwh": round(recent_avg_kwh * 24, 2)},
    ],
}

with open("data/dashboard_data.json", "w") as f:
    json.dump(output, f, indent=2)

print(f"[Part 1 — synthetic illustrative buildings] wrote {len(rows)} hourly rows (reference only, not used for timeseries)")
print(f"[Part 2 — real digital twin] wrote {len(twin_rows)} hourly rows to data/dashboard_data.json")
print(f"Baseline total:  {twin_base_total_kwh:.1f} kWh  (+fan elec.)")
print(f"Optimized total: {twin_opt_total_kwh:.1f} kWh  (+fan elec.)")
print(f"Savings: {output['summary']['energy_savings_pct']}%")
print(f"Peak demand reduction: {output['summary']['peak_demand_reduction_pct']}%")
print(f"Comfort violations — baseline: {twin_base_viol}, optimized: {twin_opt_viol}")
print(f"Cost — baseline: {twin_base_cost:.0f} SEK, optimized: {twin_opt_cost:.0f} SEK, saved: {twin_base_cost - twin_opt_cost:.0f} SEK")
print(f"Comfort violations (occupied hours) — baseline: {summary['comfort_violations_baseline']}, optimized: {summary['comfort_violations_optimized']}")
