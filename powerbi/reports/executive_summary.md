# Executive Summary — Dashboard Spec

**File**: `powerbi/reports/executive_summary.pbix`
**Page**: single page, 16:9 (1280 × 720), 4-column grid
**Audience**: engineering leadership — answers *"How healthy is the benchmark
program right now?"* in five seconds.

## Data sources

From `powerbi/datasets/data_model.md`:

- `RunSummary` (cards, sparkline trend)
- `RegressionFindings` (severity counts, top-N table)
- `EtlHealth` (pipeline reliability card)
- `KpiTrendDaily` (trend chart)
- `Calendar` (slicer + time intelligence)

## Page layout

```
+---------------------------------------------------------------+
| Title bar:  BenchLens — Executive Summary    [date slicer]    |
+--------------+--------------+--------------+------------------+
| Total Runs   | Success %    | Findings (7d)| ETL Success %    |
| (card)       | (card)       | (card+color) | (card)           |
+--------------+--------------+--------------+------------------+
|                                                               |
|  Daily run volume + headline KPI trend (combo chart)          |
|                                                               |
+----------------------------------+----------------------------+
|  Findings by severity (stacked   |  Top 5 regressions (table) |
|  column, last 30 days)           |                            |
+----------------------------------+----------------------------+
|  Workload x Hardware perf matrix (heatmap)                    |
+---------------------------------------------------------------+
```

## Visuals

### V1 — Title + global date slicer
- Text box: `BenchLens — Executive Summary`, theme color, font Segoe UI Light 24
- Slicer (between two dates) on `Calendar[Date]`, default = last 30 days

### V2 — KPI cards (row 1)
Four `Card` visuals, all use the corporate theme. Card background white,
title in `Segoe UI Semibold`.

| # | Title              | Measure              | Conditional color                 |
|---|--------------------|----------------------|-----------------------------------|
| 1 | TOTAL RUNS         | `Total Runs`         | None                              |
| 2 | SUCCESS RATE       | `Success Rate %`     | >=95 green, 90-94 amber, <90 red  |
| 3 | FINDINGS (7d)      | `Findings 7d`        | Use `Status Color` measure        |
| 4 | ETL SUCCESS RATE   | `ETL Success %`      | >=99 green, 95-98 amber, <95 red  |

Each card also shows a small secondary line `Δ vs prior period` using
`Runs MoM Δ %` for card 1, etc.

### V3 — Run volume + trend (combo)
`Line and clustered column chart`:
- Shared axis: `Calendar[Date]` (continuous, day grain)
- Column values: `Successful Runs`, `Failed Runs` (stacked)
- Line values: `Avg Primary KPI`
- Secondary Y-axis for the line
- Title: `Daily run volume & primary KPI trend`

### V4 — Severity stacked column (last 30 days)
`Stacked column chart`:
- Axis: `Calendar[Date]` (week binning)
- Legend: `RegressionFindings[severity]` (sort by `severity_rank` desc)
- Values: `Findings Count`
- Legend colors: critical `#D50000`, error `#FF6F00`, warning `#FFAB00`,
  info `#90CAF9`
- Filter (visual level): `Calendar[Date]` last 30 days

### V5 — Top regressions table
`Table` visual:
- Columns (in order): `detected_at`, `workload_code`, `hardware_code`,
  `kpi_code`, `observed_value`, `baseline_value`, `deviation_pct`, `severity`
- Filter (visual level): `rule_type = "regression"`, `severity_rank >= 3`
- Sort: `detected_at` desc
- Top N filter: 5 rows
- Conditional formatting on `deviation_pct`: data bars, red for negative

### V6 — Workload x Hardware heatmap
`Matrix` visual:
- Rows: `RunSummary[workload_code]`
- Columns: `RunSummary[hardware_code]`
- Values: `Avg Primary KPI`
- Conditional format → Background color → scale `Minimum #FFEBEE` → `Center
  #FFF8E1` → `Maximum #E8F5E9`, rule `Diverging` based on field value
- Show grand totals: off
- Cell padding: 6

## Slicers

- Top right: `Calendar[Date]` between-slider, default last 30 days
- Slicer panel (collapsed, top right corner):
  - `RunSummary[workload_category]` (button list)
  - `RunSummary[accelerator_type]` (button list)

## Drill-through targets

- Right-click any row on the regression table → drill through to the Day 8
  *Regression Reliability* page filtered to that workload/kpi.

## Acceptance checklist

- [ ] All 4 cards display non-null values when at least one run exists
- [ ] Date slicer filters every visual (verified by changing range and seeing
  card numbers update)
- [ ] Heatmap shows at least one cell per (workload, hardware) combo present
  in `vw_run_summary`
- [ ] Top-regressions table shows 0–5 rows; never errors when empty
- [ ] Theme `themes/benchlens_theme.json` applied (cards have rounded
  border, page background `#FAFAFA`)
