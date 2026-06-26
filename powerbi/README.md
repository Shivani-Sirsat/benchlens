# Power BI artifacts

This directory holds everything needed to author and refresh the BenchLens
Power BI reports. The reporting **semantic layer** is implemented as SQL views
in the warehouse (`benchlens/warehouse/migrations/003_reporting_views.sql`)
— so you can rebuild any `.pbix` from scratch deterministically by:

1. installing the views (`benchlens reports views refresh`),
2. opening `datasets/benchmark_model.pbids` in Power BI Desktop,
3. importing the six reporting views as tables, and
4. following the dashboard spec in `reports/<name>.md` to lay out the visuals
   and applying the DAX library in `datasets/dax_measures.md`.

## Layout

```
powerbi/
  README.md                            <-- this file
  datasets/
    benchmark_model.pbids              Postgres connection (opens in Power BI)
    data_model.md                      Tables, relationships, hiding rules
    dax_measures.md                    Full DAX library
  reports/
    executive_summary.md               Day 7 dashboard 1 spec
    hardware_performance.md            Day 7 dashboard 2 spec
    model_comparison.md                (Day 8)
    regression_reliability.md          (Day 8)
  themes/
    benchlens_theme.json               Corporate visual theme
  deployment/
    refresh_views.ps1                  Re-apply views + verify
```

## Quickstart

```powershell
# 1. Make sure the warehouse + views are up to date
benchlens db ping
benchlens reports views refresh
benchlens reports views check

# 2. Open the connection file
start powerbi\datasets\benchmark_model.pbids
```

In Power BI Desktop:
- When prompted for credentials, choose **Database**, user `benchlens`,
  password `benchlens` (local dev), or your AAD account in production.
- In Navigator, select the six `vw_*` views (see `datasets/data_model.md`).
- Apply the corporate theme: **View → Themes → Browse for themes** →
  `powerbi/themes/benchlens_theme.json`.
- Create the `Calendar` table and the `_Measures` measure-host table per
  `datasets/data_model.md` and `datasets/dax_measures.md`.

## Reporting views (semantic layer)

| View                          | Grain                                       | Used by                          |
| ----------------------------- | ------------------------------------------- | -------------------------------- |
| `vw_run_kpi_flat`             | one row per (run, KPI)                      | ad-hoc / explore                 |
| `vw_run_summary`              | one row per run                             | Executive Summary                |
| `vw_hardware_efficiency`      | one row per successful run                  | Hardware Performance             |
| `vw_kpi_trend_daily`          | one row per (date, workload, hardware, KPI) | trend lines (both reports)       |
| `vw_regression_summary`       | one row per DQ finding                      | Executive Summary, Regression    |
| `vw_etl_health`               | one row per (date, source, pipeline)        | Executive Summary, ops tile      |
| `vw_model_perf_pivot`         | one row per (model, workload, hardware, KPI)| Model Comparison                 |
| `vw_model_comparison_matrix`  | one row per model                           | Model Comparison                 |
| `vw_run_reliability`          | one row per (workload, hardware)            | Regression Reliability           |
| `vw_regression_trend_daily`   | one row per (date, severity, cohort, KPI)   | Regression Reliability           |
| `vw_regression_detection_lag` | one row per finding (with run join)         | Regression Reliability           |

All views are non-materialized — Power BI Import mode reads the full result
at refresh time, so each refresh sees the latest warehouse state.

## Refresh strategy

- **Dev (Power BI Desktop)**: hit **Home → Refresh** after any pipeline run.
- **Demo**: run `powerbi\deployment\refresh_views.ps1` then refresh the
  dataset in Power BI Desktop / Service.
- **Server-side scheduled refresh**: deploy `.pbix` files to a Power BI
  workspace and configure a Postgres on-prem gateway pointing at the
  warehouse host. The views are query-folding-friendly (simple SELECTs over
  star-schema joins).
