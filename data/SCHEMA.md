# dashboard_data.json — schema

This is the **only** file the dashboard reads (`index.html` fetches
`data/dashboard_data.json`). real data from
Kraftstaden / Trollhättan Energi should be placed here, build a new file matching this exact shape
and drop it in / at the same path — nothing in `index.html` needs to change.

```jsonc
{
  "meta": {
    "network": "string — shown nowhere in the UI yet, kept for context",
    "data_source": "string — e.g. 'Demo dataset' or 'Kraftstaden BMS export, Jan 2026'",
    "period_start": "ISO 8601 timestamp — first row's timestamp",
    "period_end": "ISO 8601 timestamp — last row's timestamp",
    "comfort_band_c": [20.0, 23.0],   // [low, high] used for violation shading
    "heat_price_sek_per_kwh": [1.10, 1.35], // [low, high] — fallback for the cost KPI when rows have no real per-hour cost
    "electricity_price_sek_per_kwh": 1.5,   // optional — only present when the source data separately prices electricity
    "scenario_scope": "string — shown under the Weekly temperature subtitle; what the timeseries simulation actually represents (e.g. one classroom zone, what 'optimized' includes) so the numbers aren't mistaken for a whole-building figure",
    "generated_at": "ISO 8601 timestamp — when this file was built"
  },

  "summary": {
    // Precomputed KPIs for the top tiles. Recompute these from your real
    // timeseries the same way generate_data.py does (see that file's
    // "Derived summary stats" section) rather than hand-typing them.
    "total_energy_baseline_kwh": 0,
    "total_energy_optimized_kwh": 0,
    "energy_savings_pct": 0,
    "peak_demand_baseline_kw": 0,
    "peak_demand_optimized_kw": 0,
    "peak_demand_reduction_pct": 0,
    "comfort_violations_baseline": 0,
    "comfort_violations_optimized": 0,
    // kWh totals × meta.heat_price_sek_per_kwh midpoint — see generate_data.py
    "energy_cost_baseline_sek": 0,
    "energy_cost_optimized_sek": 0,
    "energy_cost_savings_sek": 0
  },

  "timeseries": [
    {
      "timestamp": "ISO 8601, hourly steps",
      "outdoor_temp_c": 0.0,
      "occupied": false,                       // true/false per hour

      "baseline_indoor_temp_c": 0.0,
      "baseline_heating_power_kw": 0.0,
      "baseline_heating_energy_kwh": 0.0,       // power * timestep
      "baseline_ventilation_purge_kwh": 0.0,    // 0 if not modeling this; see note below
      "baseline_energy_kwh": 0.0,               // heating + purge — what the KPI tiles sum
      "baseline_cost_sek": 0.0,                 // optional — real per-hour cost, if the source has it (preferred over price × kWh)

      "optimized_indoor_temp_c": 0.0,
      "optimized_heating_power_kw": 0.0,
      "optimized_heating_energy_kwh": 0.0,
      "optimized_ventilation_purge_kwh": 0.0,
      "optimized_energy_kwh": 0.0,
      "optimized_cost_sek": 0.0
    }
    // ... one object per hour in the period
  ],

  "buildings": [
    {
      "id": "string — unique, used as a DOM/storage key (e.g. 'sch-a')",
      "code": "string — short tag shown in the list (e.g. 'SCH-A')",
      "name": "string — full building name shown in the list",
      "type": "string — e.g. 'School', 'Industrial', 'Sports facility', 'Health center', 'Office'",
      "target_c": 21.0,              // comfort setpoint for this building
      "indoor_c": 21.2,              // current/latest indoor reading
      "outdoor_c": -3.1,             // today's outdoor reading (same across buildings)
      "mode": "auto",                // "auto" | "manual" — the Control panel's default
      "status": "heating",           // "heating" | "idle" — only used when mode is "auto"
      "heater_on": true,
      "attention": false,            // true flags the row red ("needs attention")
      "updated_min_ago": 2,
      "co2_ppm": 520,
      "energy_kw": 38,               // current draw shown in the building detail panel
      "ahus": [
        { "id": "AHU-01", "running": true, "fan_pct": 78, "supply_c": 14.9, "return_c": 19.1 }
        // ... one per air handling unit
      ],
      "rooms": [
        { "name": "Room 101", "temp_c": 21.0, "occupied": true, "status": "normal" }
        // "status" is "normal" | "low" | "high" — low/high rooms are what
        // the building detail panel and the Control panel's per-row alert
        // line surface to the person ("Room 501 needs attention — 18.2°C")
      ]
    }
    // ... one object per building
  ],

  "benchmarks": [
    // Published reference figures to sanity-check the model against — NOT
    // numbers the simulation produces. Rendered as a row of tiles on the
    // Settings page ("Validation benchmarks").
    { "label": "Average school heat use (2006)", "value": "152 kWh/m²·yr", "source": "SKR 2011, citing STIL2" }
    // ... see generate_data.py for the full list
  ],

  "model_parameters": [
    // Every input the thermal model (owned separately by the teammate who
    // built it) runs on, with how confident we are in each value. Rendered
    // as a table on the Settings page ("Model parameters & sources").
    {
      "group": "Heating",                 // groups the table into sections
      "parameter": "Supply / return at design outdoor temp",
      "value": "64 °C / 42 °C at −16 °C (mean of 109 systems)",
      "confidence": "sourced",            // "sourced" | "derived" | "assumed" | "unknown"
      "source": "Chalmers radiator survey (Jangsten 2017)"
    }
    // ... see generate_data.py for the full 28-row list, sourced from
    // data/params_research.md (the teammate's classroom-twin research doc)
  ],

  "open_items": [
    "Free-text caveats shown as a hint under the parameters table — things",
    "still unresolved (an unconfirmed station id, an unverified design",
    "temperature, a spec that wasn't found, etc.)."
  ],

  "forecast": {
    // Heat-usage forecast (preview) card on the Weekly temperature page.
    // Optional — the page renders nothing if this key is missing.
    "status": "illustrative",            // "illustrative" | "live" — "live" is not implemented by the UI yet, but is reserved for when a real model's output replaces this block; the UI always shows the "illustrative"/"preview" badge regardless, so don't wire a "live" status in without also removing that badge in dashboard.html.
    "status_note": "string — shown under the card heading",
    "trained_on": "string — one line describing the training dataset",
    "features": ["list", "of", "feature", "names"],
    "history_windows": ["Past 24 h", "Past 168 h (1 week)"],
    "horizons": [
      { "label": "Next 1 h", "hours": 1, "predicted_kwh": 0.0 }
      // ... one per forecast horizon, rendered as KPI tiles
    ]
  }
}
```

The source research this is built from lives at `data/params_research.md`
(classroom parameters) and `data/room_energy_balance.md` (the C·dT/dt
equation the timeseries simulation actually runs on) — keep both alongside
`dashboard_data.json` so the confidence tags and the equation card in the UI
can be traced back to where each number came from.

As of this version, `timeseries` and `buildings[0]` ("School A") are built
from a real digital-twin export, not synthetic data: `data/twin_dashboard.json`
(format 1.0, documented in `data/dashboard-format.md`) is a full simulated
year of one classroom under four control scenarios; `generate_data.py`
converts its `legacy-faults-as-is` → `baseline` and `optimized-faults-none`
→ `optimized` scenarios into this schema. The other 9 buildings are still
the original illustrative/synthetic data.

## Control panel behavior

The Control panel (`dashboard.js`, `renderBuildings()`) reads `buildings` once per
load. When a person flips a building to **Manual**, or flips its heater switch
while in Manual, that choice is stored client-side (`localStorage`, per browser)
as an override on top of the data file — it does not write back to
`dashboard_data.json`. A real backend would instead send that toggle to the
building's BMS/controller and let the next data refresh reflect it.

## Notes for swapping in real data

- **"baseline"** = the building's current/actual behavior (fixed schedule,
  whatever Kraftstaden's BMS or substation logs show). **"optimized"** = your
  model's simulated/recommended alternative for the *same* outdoor-temperature
  and occupancy period, so the two are a fair side-by-side comparison.
- If you only have **real baseline data** and no real "optimized" run yet,
  that's fine — generate `optimized_*` columns from your simulation model fed
  the *real* `outdoor_temp_c` and `occupied` columns, so the comparison is
  apples-to-apples against what actually happened.
- `ventilation_purge_kwh` is optional — if you don't have real ventilation
  data, set it to `0` for every row rather than omitting the key (the
  dashboard expects the field to exist).
- Keep timestamps at a **constant interval** (hourly in the synthetic data).
  If your real data is at a different resolution (15-min, daily), that's fine
  too, just be consistent — the dashboard doesn't assume hourly, it just plots
  what's there.
- `occupied` drives the shaded occupancy bands on the chart and the comfort-
  violation count (violations only count during occupied hours) — make sure
  it reflects real schedules, not just weekday/weekend.
