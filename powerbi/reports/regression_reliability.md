# Regression Reliability — Dashboard Spec

**File**: `powerbi/reports/regression_reliability.pbix`
**Page**: single page, 16:9 (1280 × 720)
**Audience**: SRE / DQ engineers — answers *"Where are regressions
concentrated, how fast do we catch them, and which cohorts have the worst
failure rate?"*

This page is also the **drill-through target** from the top-regressions
table on `executive_summary.pbix`.

## Data sources

- `RegressionTrendDaily`   ← `vw_regression_trend_daily`
- `RegressionFindings`     ← `vw_regression_summary`
- `DetectionLag`           ← `vw_regression_detection_lag`
- `RunReliability`         ← `vw_run_reliability`
- `Calendar`

## Page layout

```
+--------------------------------------------------------------+
| Title bar: Regression Reliability   [date | severity slicer] |
+----------+----------+-----------+-----------+----------------+
| Findings | Critical | Avg       | Median    | Cohort         |
| (30d)    | + Error  | Detect Lag| Detect Lag| Success Rate   |
+----------+----------+-----------+-----------+----------------+
|                                                              |
|  Findings over time (stacked area by severity)               |
|                                                              |
+----------------------+---------------------------------------+
| Top failing cohorts  | Detection lag histogram (column)      |
| (matrix, sorted ↓    |                                       |
| failure_pct)         |                                       |
+----------------------+---------------------------------------+
| Detailed findings (paginated table)                          |
+--------------------------------------------------------------+
```

## Visuals

### V1 — Title + slicers
- Text: `Regression Reliability` Segoe UI Light 24
- Slicers (top-right strip):
  - `Calendar[Date]` between-slider, default last 30 days
  - `RegressionFindings[severity]` button list
  - `RegressionFindings[workload_code]` dropdown (multi)

### V2 — KPI cards (row 1)

| # | Title              | Measure                       | Conditional color                |
|---|--------------------|-------------------------------|----------------------------------|
| 1 | FINDINGS (30d)     | `Findings 30d`                | Use `Status Color` measure       |
| 2 | CRIT + ERROR (30d) | `Critical+Error 30d`          | >0 red                            |
| 3 | AVG DETECT LAG     | `Avg Detection Lag (min)`     | <60 green, 60-240 amber, >240 red|
| 4 | MEDIAN DETECT LAG  | `Median Detection Lag (min)`  | same as above                    |
| 5 | COHORT SUCCESS %   | `Avg Cohort Success %`        | >=99 green, 95-98 amber, <95 red |

### V3 — Findings over time
`Stacked area chart`:
- Axis: `Calendar[Date]` (day grain)
- Legend: `RegressionTrendDaily[severity]` (sort by `severity_rank` desc)
- Values: `Sum Finding Count`
- Legend colors: critical `#D50000`, error `#FF6F00`, warning `#FFAB00`,
  info `#90CAF9`
- Title: `Findings over time (stacked by severity)`

### V4 — Top failing cohorts
`Matrix`:
- Rows: `RunReliability[workload_code]`, `RunReliability[hardware_code]`
  (drill-down hierarchy)
- Values:
  - `Sum Total Runs`
  - `Sum Failures`
  - `Avg Cohort Success %`
  - `Min MTBF Hours` (worst-case)
- Sort: by `Avg Cohort Success %` asc (worst first)
- Conditional format: background scale red→green on `Avg Cohort Success %`
- Top N filter (visual level): 10 rows
- Title: `Lowest-reliability cohorts`

### V5 — Detection lag histogram
`Stacked column chart`:
- Axis: bucket on `DetectionLag[detection_lag_minutes]` using grouping:
  `<5`, `5-15`, `15-60`, `1-4h`, `4-24h`, `>24h` (create via "New group")
- Values: `Findings With Lag`
- Title: `Time-to-detect distribution`

### V6 — Detailed findings table
`Table`:
- Columns: `detected_at`, `severity`, `rule_type`, `rule_id`,
  `workload_code`, `hardware_code`, `kpi_code`, `observed_value`,
  `baseline_value`, `deviation_pct`, `detection_lag_minutes`, `message`
- Sort: `detected_at` desc
- Page size: 25
- Conditional formatting on `deviation_pct`: data bars, red for negative
- Filter (visual level): `severity IN [warning, error, critical]`

## Drill-through configuration

In Power BI Desktop, on this page:
1. Drill-through panel → drag `RegressionFindings[workload_code]` and
   `RegressionFindings[kpi_code]` as drill-through fields.
2. From Executive Summary, right-click any row of the top-regressions
   table → **Drill through → Regression Reliability** to land here with
   workload + kpi filters pre-applied.

## Bookmarks

- **All findings** — no severity filter
- **Critical only** — severity = "critical"
- **This week** — date slicer = last 7 days

## Acceptance checklist

- [ ] Stacked area covers full date range; severity colors match Executive
  Summary
- [ ] Lag histogram buckets sort low→high (not alphabetical)
- [ ] Cohort matrix correctly drills from workload → hardware
- [ ] Drill-through from Executive Summary lands on this page with filters
  applied (verify by right-clicking a regression row)
- [ ] All cards return 0 (not blank) when no findings exist in the slicer
  window
