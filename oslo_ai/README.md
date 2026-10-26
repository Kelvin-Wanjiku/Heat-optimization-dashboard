# oslo_ai: the AI model and digital twin behind the Oslo results

Copied from our team's PAI700 project (Group 10, University West; client Trollhättan Stad / Kraftstaden) so this repository is self-contained. The code is the same as in the PAI700 repository: **[add link to the PAI700 repository]**. Credit for the digital twin and the AI model: see that repository's README.

| Folder | What it is |
|---|---|
| `twin/`, `config/params.yaml`, `twin_runner.py` | Digital twin of one 60 m² classroom: two-node room model, radiator, ventilation unit, legacy controller and the smart controllers. Parameters are assumed values, each with a confidence label. |
| `modeling/`, `etl/` | Forecasting code: baselines, LightGBM, GRU, features, training, final test, model export, predictor. |
| `models/ai_v1/` | The trained models (LightGBM + GRU at 1, 6 and 24 h) with a `manifest.json` of SHA-256 checksums. The predictor refuses a changed file. |
| `frozen/` | The frozen Oslo replay window (3 schools, 24 Sep 2022 – 31 Mar 2023, hourly) with its checksum. |
| `docs/` | The team's notes: controllers and scenario, metrics, parameters, data-quality decision log. |

## Rebuild the dashboard data (no Docker, works on Windows)
From the repository root:
```
pip install -r requirements-oslo.txt
python export_oslo_data.py
```
This reads `frozen/`, runs the saved models and the twin in one process, and writes `data/oslo_ai.json` (about 15 s for the forecasts, about 8 minutes for the 300 simulations). Use `--forecast-only` or `--twin-only` to redo one part. The output is identical to what the PAI700 services return.

## Re-train the model
The raw data is **not** included (it is large). Download the Oslo dataset from SINTEF (DOI 10.60609/2hvr-wc82, CC BY 4.0, Lien et al., *Data in Brief* 63, 112288, 2025) and put the building CSV files in `oslo_ai/datasets/COFACTOR-SBHUB-Oslo/Dataset_buildings_csv_files/`. Then, **from inside `oslo_ai/`** (the scripts use paths relative to it):
```
python -m etl.preprocess_htot            # raw files -> data/silver and data/gold
python -m modeling.run_gbm --daytypes --trends   # LightGBM on all validation folds (about 40 min)
python -m modeling.run_gru --schemes pooled      # GRU (about 2.5 h on CPU)
python -m modeling.final                 # the final test run - use once
python -m modeling.export                # train on data before 2022-03-01 and save to models/ai_v1/ (about 40 min)
```
After exporting new models, rebuild the dashboard data with `python export_oslo_data.py`. The GRU is not bit-for-bit repeatable, so scores can differ slightly (about 0.4 percentage points in the original check). Use `git` with `oslo_ai/models/` stored as-is: `.gitattributes` in the repository root stops Windows from changing line endings in the model files, which would break the checksums.

## Limits
Forecasts use measured weather as a "perfect weather forecast", so real accuracy would be lower. Room parameters are assumed and the Oslo data has no indoor temperature, so the simulations show the mechanism, not a proven saving. The AI forecast is a benchmark only; no controller uses it.
