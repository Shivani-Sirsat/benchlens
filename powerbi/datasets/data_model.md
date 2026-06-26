# BenchLens — Power BI Data Model

This is the canonical mapping between the warehouse reporting views and the
Power BI semantic model. Both Day-7 dashboards (`executive_summary`,
`hardware_performance`) and the Day-8 dashboards (`model_comparison`,
`regression_reliability`) share the same model.

## Source

- **Server**: `localhost`
- **Database**: `benchlens`
- **Schema**: `public` (default)
- **Mode**: Import (refresh nightly)
- **Connection file**: `datasets/benchmark_model.pbids`

Use the included `.pbids` to launch Power BI Desktop with the connection
pre-filled. You will be prompted for the `benchlens` user credentials
(default password also `benchlens` in dev).

## Tables to import

All six reporting views are exposed to Power BI as tables. Do **not** import
the raw `fact_*` / `dim_*` tables — the views are the supported contract.

| Power BI table         | Source view              | Grain                                      |
| ---------------------- | ------------------------ | ------------------------------------------ |
| `RunKpi`               | `vw_run_kpi_flat`        | One row per (run, KPI)                     |
| `RunSummary`           | `vw_run_summary`         | One row per run                            |
| `HardwareEfficiency`   | `vw_hardware_efficiency` | One row per successful run                 |
| `KpiTrendDaily`        | `vw_kpi_trend_daily`     | One row per (date, workload, hardware, KPI)|
| `RegressionFindings`   | `vw_regression_summary`  | One row per DQ finding                     |
| `EtlHealth`            | `vw_etl_health`          | One row per (date, source, pipeline)       |

## Date table (mark as date table)

Create a calculated table named `Calendar`:

```dax
Calendar =
ADDCOLUMNS(
    CALENDAR( DATE(2025,1,1), DATE(2027,12,31) ),
    "Year",        YEAR([Date]),
    "Quarter",     "Q" & FORMAT([Date], "Q"),
    "Month",       MONTH([Date]),
    "Month Name",  FORMAT([Date], "MMM"),
    "Year-Month",  FORMAT([Date], "YYYY-MM"),
    "Week",        WEEKNUM([Date], 2),
    "Is Weekend",  WEEKDAY([Date], 2) > 5
)
```

Then in Modeling: **Mark as date table** → choose `Date` column.

## Relationships

| From table          | From column   | To table   | To column | Cardinality | Filter direction |
| ------------------- | ------------- | ---------- | --------- | ----------- | ---------------- |
| `RunKpi`            | `run_date`    | `Calendar` | `Date`    | Many-to-One | Single           |
| `RunSummary`        | `run_date`    | `Calendar` | `Date`    | Many-to-One | Single           |
| `HardwareEfficiency`| `run_date`    | `Calendar` | `Date`    | Many-to-One | Single           |
| `KpiTrendDaily`     | `run_date`    | `Calendar` | `Date`    | Many-to-One | Single           |
| `RegressionFindings`| `detected_date`| `Calendar`| `Date`    | Many-to-One | Single           |
| `EtlHealth`         | `run_date`    | `Calendar` | `Date`    | Many-to-One | Single           |

All other fields stay denormalized inside each table. **Do not** create
cross-table relationships between the reporting views — slicers should bind
to columns within each table.

## Column visibility (hide from report view)

For each table, hide the following columns (they are IDs used only for joins
or row identity):

- `RunKpi` — `run_id`, `run_uuid`, `workload_id`, `hardware_id`, `stack_id`,
  `model_id`, `kpi_id`, `date_id`-equivalents
- `RunSummary` — `run_id`, `run_uuid`
- `HardwareEfficiency` — `run_id`, `hardware_id`
- `RegressionFindings` — `check_id`

## Refresh strategy

- **Dev**: Import + manual refresh from Power BI Desktop after a pipeline run.
- **Demo**: Schedule daily refresh in Power BI Service against the on-prem
  gateway pointing at the warehouse host.
- **Refreshing views (server-side)**: Views are not materialized, so they
  reflect the latest warehouse state. To re-apply DDL after a schema change:
  ```powershell
  benchlens reports views refresh
  benchlens reports views check
  ```
