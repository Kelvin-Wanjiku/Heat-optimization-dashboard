# Dashboard data file: `dashboard.json` (format 1.0)

The digital twin writes **one JSON file** for the dashboard. It holds a whole simulated year of one classroom under four scenarios, at hourly, daily, weekly and monthly resolution, plus yearly totals and savings. The dashboard only has to load this file; there is no server or API.

```
dashboard_data/dashboard.json        produced by: cd twinFolder && uv run python -m twin.dashboard --year 2025
twinFolder/docs/dashboard-example.json   small example (14 days, SYNTHETIC weather) to build against now
```

The data is **simulated**, not measured (`"simulated": true`). Show that in the dashboard, e.g. "Simulated with SMHI weather for Trollhättan 2025".

## Top level

| Key | Content |
|---|---|
| `format_version` | `"1.0"`. Only *additions* happen within 1.x; read fields you know and ignore the rest. |
| `generated_utc` | when the file was produced |
| `simulated` | always `true` for twin output |
| `about` | one sentence to show under the dashboard title |
| `period` | `from`, `to` (exclusive), `days`, `timezone` (`Europe/Stockholm`) |
| `weather` | where the weather came from: SMHI station, distance, licence (CC BY 4.0, attribution "SMHI"), hours filled by interpolation |
| `calendar` | number of school days and whether the calendar is confirmed or assumed |
| `building` | floor area, window area and orientation, pupils, teachers |
| `assumptions` | heat model, prices, baseline faults, how today's ventilation is assumed to run |
| `scenarios` | the four scenarios: `id`, `label` (short, for legends), `description`, `is_reference` |
| `metrics` | catalogue of every metric: `label`, `unit`, `category`, `aggregation`, `scope` (`shared` or `scenario`) |
| `totals` | yearly totals per scenario: `totals[scenario_id][metric]` |
| `comparison` | savings of each scenario against the reference (today's control) |
| `series` | the time series (below) |

## Series

`series` has four resolutions: `hourly`, `daily`, `weekly` (weeks start Monday; the key is the Monday's date) and `monthly`. Each has the same shape:

```json
"daily": {
  "times":  ["2025-01-01", "2025-01-02", "..."],
  "shared": { "t_outdoor_C": [ -2.1, -3.4, "..."], "occupied_h": [0, 0, "..."] },
  "scenarios": {
    "legacy-faults-as-is":   { "t_air_C": [21.3, "..."], "cost_total_SEK": [4.81, "..."] },
    "optimized-faults-none": { "t_air_C": [19.2, "..."], "cost_total_SEK": [2.10, "..."] }
  }
}
```

- `times[i]` belongs to `values[i]` of every array in that block.
- Time formats:

  | Resolution | Format | Example |
  |---|---|---|
  | `hourly` | `YYYY-MM-DDTHH:MM` | `2025-01-01T08:00` |
  | `daily` | `YYYY-MM-DD` | `2025-01-01` |
  | `weekly` | Monday's date | `2025-01-06` |
  | `monthly` | `YYYY-MM` | `2025-01` |

  All are local time.
- **shared** metrics are the same in every scenario: weather and occupancy.
- **scenario** metrics differ per scenario: temperatures, power, energy, cost.
- `null` means "no value" (e.g. `setpoint_C` for a controller without a setpoint).

## Metrics

| id | Unit | Aggregation | Scope | Meaning |
|---|---|---|---|---|
| `t_outdoor_C` | °C | mean | shared | outdoor temperature (SMHI) |
| `solar_W_m2` | W/m² | mean | shared | sunlight on the south window (from SMHI STRÅNG) |
| `occupants_max` | people | max | shared | most people in the room in the period |
| `occupied_h` | h | sum | shared | time with anyone in the room |
| `t_air_C` | °C | mean | scenario | room temperature |
| `t_air_min_C`, `t_air_max_C` | °C | min / max | scenario | lowest and highest room temperature in the period |
| `setpoint_C` | °C | mean | scenario | temperature the controller aimed for |
| `q_radiator_W`, `q_ahu_coil_W`, `q_cooling_W` | W | mean | scenario | average heating / AHU coil / cooling power |
| `valve_effective_pct` | % | mean | scenario | radiator valve opening the room sees |
| `ventilation_flow_L_s` | L/s | mean | scenario | ventilation airflow |
| `radiator_heat_kWh`, `ahu_coil_heat_kWh`, `total_heat_kWh` | kWh | sum | scenario | district heat |
| `ac_electricity_kWh`, `fan_electricity_kWh`, `total_electricity_kWh` | kWh | sum | scenario | electricity |
| `cost_total_SEK` | SEK | sum | scenario | heat + electricity at the prices in `assumptions` |
| `heating_while_cooling_h` | h | sum | scenario | radiator heating while the AC or the overheat purge runs (the problem) |
| `lesson_too_cold_h`, `lesson_too_hot_h` | h | sum | scenario | lesson time below 20 °C / above 26 °C |

The same catalogue is inside the file (`metrics`), so the dashboard can build its menus and axis labels from it.

## Recipes for the dashboard

| View | Read |
|---|---|
| **Day view** (hour by hour) | `series.hourly`: pick the 24 entries of that date from `times` |
| **Week view** | `series.hourly` for 7 days (168 points), or `series.daily` for 7 bars |
| **Year view** | `series.monthly` (12 points) or `series.weekly` (53) |
| **Is the class occupied? How many people?** | `shared.occupants_max` (0 = empty) and `shared.occupied_h` at any resolution |
| **Temperature** | `t_air_C` with `t_air_min_C` and `t_air_max_C` as a band; `t_outdoor_C` from `shared`; comfort band 20–26 °C |
| **Energy** | `total_heat_kWh`, `total_electricity_kWh`, or the split metrics |
| **Heating power** | `q_radiator_W`, `q_ahu_coil_W`, `q_cooling_W` |
| **Today vs smart control** | the same metric from two entries of `scenarios`; headline numbers from `comparison` and `totals` |

Example (JavaScript): daily cost of two scenarios for a chart.

```js
const d = await (await fetch("dashboard.json")).json();
const x = d.series.daily.times;
const today = d.series.daily.scenarios["legacy-faults-as-is"].cost_total_SEK;
const smart = d.series.daily.scenarios["optimized-faults-none"].cost_total_SEK;
const unit  = d.metrics.cost_total_SEK.unit;          // "SEK"
```

## Size

A full year is about 5 MB, mostly the hourly series. Web servers compress JSON (gzip) to about 1 MB on the way. If that is ever too big, the file can be split per resolution without changing the shape.
