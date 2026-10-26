# Heat Control: AN AI-Assisted Heating Optimization Dashboard

A feasibility-study prototype for **Trollhättan Stad / Kraftstaden Fastigheter Trollhättan AB**. It shows how smarter heating control could cut energy use, cost and peak demand in school and municipal buildings without hurting indoor comfort.

It is a self-contained HTML/CSS/JS app with no build tooling and no framework.

> **Data disclaimer:** The temperature, energy and cost figures come from a **digital-twin simulation** of one classroom (Room 101, 60 m², Trollhättan) over 2025, driven by real SMHI weather.
> They are simulated, not measured. The other nine buildings on the Control panel are illustrative placeholders. The heat-usage forecast card is illustrative and is not output from a trained model.

## Features

**Control panel (landing page)**
- Summary tiles for Heating, Idle, Manual, Auto and Needs attention.
-  Click a tile to see which buildings are in that state, then click a name to open its details.
- Filter the building list by type (schools, industrial, sports facilities, health centers, offices).
- Per-building Auto/Manual mode and heater toggle.
- Building detail drawer with HVAC/AHU status, room temperatures, alarms and energy tabs.
- Live outdoor temperature for Trollhättan via [Open-Meteo](https://open-meteo.com/), with a fallback to the simulation's last data point if the request fails.

**Weekly temperature**
- Baseline ("Today", with the building's current control faults) vs. optimized ("Smart control") for indoor temperature, heating power and cumulative energy.
- KPI tiles for energy use, estimated cost, peak demand and comfort violations, recalculated for the selected range (3 days to 1 year).
- Chart and table views, and an illustrative heat-usage forecast card.

**Settings and About**
- °C/°F units and light/dark theme.
- About page covering data provenance, the room energy-balance equation, validation benchmarks against published Swedish school data, and a model-parameters table with sourced / derived / assumed / unknown confidence tags.

## Getting started

The page loads its data with `fetch`, so it needs to be served over HTTP. Opening `index.html` directly from disk won't work.

VS Code's Live Server extension also works.

## Project structure

```
index.html            App shell and markup
dashboard.css         Styles (light/dark themes via CSS variables)
dashboard.js          All app logic: rendering, charts, control panel, live weather
generate_data.py      Builds data/dashboard_data.json from the twin export
assets/               Logo and sidebar background
data/
  twin_dashboard.json     Raw digital-twin export (format 1.0)
  dashboard_data.json     The only file the dashboard reads
  SCHEMA.md               Shape of dashboard_data.json
  dashboard-format.md     Twin export format spec
  params_research.md      Classroom parameter research
  room_energy_balance.md  Heat-model equation and term definitions
```

## Regenerating the data

```bash
python3 generate_data.py
```

This reads `data/twin_dashboard.json` and writes `data/dashboard_data.json`. To use real building data later, produce a file matching `data/SCHEMA.md` at the same path. The dashboard code doesn't need to change.

## How the numbers are produced

The simulation is based on a room energy balance:

```
C · dT_in/dt = Q_radiator + Q_internal + Q_solar − (T_in − T_out)/R − Q_vent
```

- **Baseline** is the twin's `legacy-faults-as-is` scenario: roughly half the radiator valves stuck open, an outdoor sensor biased low, and a manual morning boost.
- **Optimized** is the twin's `optimized-faults-none` scenario: coordinated smart-valve control with those faults fixed.
- The twin has four scenarios; the dashboard charts these two.
- Weather comes from SMHI open data (Såtenäs station, CC BY 4.0). The Vänersborg station was tried first but only reports every quarter-hour.

## Known limitations

- One simulated classroom stands in for the whole building stock, so don't read the savings as a whole-portfolio figure.
- Several model parameters (thermal mass, envelope resistance, occupancy schedule, radiator size) are placeholders. They are tagged "assumed" in the app.
- Control-panel Auto/Manual overrides are stored in the browser's `localStorage`. They are not sent to any real building system.
- The forecast card is a UI placeholder for a model that is still being trained.

## Data sources and credits

- Weather: [SMHI Open Data](https://www.smhi.se/data) (CC BY 4.0) and [Open-Meteo](https://open-meteo.com/)
- Benchmarks: SKR 2011 (citing Energimyndigheten STIL2)
- Radiator survey: Jangsten 2017 (Chalmers)
- Planned forecast model training data: SINTEF COFACTOR-SBHUB Oslo school-building dataset (Lien et al., *Data in Brief*, 2025)
