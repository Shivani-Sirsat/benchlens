# Model Comparison — Dashboard Spec

**File**: `powerbi/reports/model_comparison.pbix`
**Page**: single page, 16:9 (1280 × 720)
**Audience**: ML engineers — answers *"Which model gives the best
throughput/$/accuracy for my workload, normalized for parameter count?"*

## Data sources

- `ModelComparison`   ← `vw_model_comparison_matrix`  (1 row per model)
- `ModelPerfPivot`    ← `vw_model_perf_pivot`         (model × workload × hardware × KPI)
- `KpiTrendDaily`     ← `vw_kpi_trend_daily`          (trend lines)
- `Calendar`

## Page layout

```
+--------------------------------------------------------------+
| Title bar: Model Comparison    [workload | hardware | quant] |
+----------+----------+-----------+-----------+----------------+
| Models   | Best ↑    | Best ↑    | Best ↑    | Total Energy   |
| Tested   | Throughput| Tput/$1k  | Tput/MParam| (kWh)          |
+----------+----------+-----------+-----------+----------------+
|                                                              |
|  Parameter count vs throughput (scatter, log-X)              |
|                                                              |
+----------------------+---------------------------------------+
| Model family rollup  | Throughput per Million Params (bar)   |
| (donut: run share)   | ranked desc                           |
+----------------------+---------------------------------------+
| Model comparison matrix (detail table — every measure)       |
+--------------------------------------------------------------+
```

## Visuals

### V1 — Title + slicers
- Text: `Model Comparison` Segoe UI Light 24
- Slicers (top-right strip):
  - `ModelPerfPivot[workload_code]` dropdown (single select)
  - `ModelPerfPivot[hardware_code]` dropdown (multi select)
  - `ModelComparison[quantization]` button list (fp16/int8/fp8/etc.)
  - `ModelComparison[model_family]` button list

### V2 — KPI cards (row 1)

| # | Title                | Measure                             | Format         |
|---|----------------------|-------------------------------------|----------------|
| 1 | MODELS TESTED        | `Models Tested`                     | `#,##0`        |
| 2 | BEST THROUGHPUT      | `Top Model Throughput`              | text           |
| 3 | BEST PERF / $1k      | `Top Model Throughput/$1k`          | text           |
| 4 | BEST TPUT / MPARAM   | `Top Model Per-Param`               | text           |
| 5 | TOTAL ENERGY         | `Total Energy (kWh)`                | `0.000 " kWh"` |

Each text card shows the model name + the numeric value beneath it.

### V3 — Parameter count vs throughput scatter
`Scatter chart`:
- X axis: `ModelComparison[parameter_count]` (log scale)
- Y axis: `Avg Throughput (Model)`
- Details: `ModelComparison[model_code]`
- Color: `ModelComparison[model_family]`
- Bubble size: `ModelComparison[run_count]`
- Trend line: linear, optional
- Title: `Param count vs throughput (log-X, bubble = run count)`

### V4 — Family rollup donut
`Donut chart`:
- Legend: `ModelComparison[model_family]`
- Values: `Sum Run Count`
- Detail labels: `Category, Percent of total`

### V5 — Perf-per-parameter ranking
`Stacked bar chart` (horizontal):
- Axis: `ModelComparison[model_code]`
- Values: `Avg Throughput per Million Params`
- Sort: by value desc
- Color: `ModelComparison[quantization]`
- Data labels: on, format `0.00`
- Title: `Throughput per Million Parameters (higher is better)`

### V6 — Comparison matrix
`Matrix` visual:
- Rows: `ModelComparison[model_code]`
- Values:
  - `Parameter Count (B)` (custom measure: `parameter_count / 1e9`)
  - `Avg Throughput (Model)`
  - `Avg Latency (Model, ms)`
  - `Avg Perf/Watt (Model)`
  - `Avg Throughput/$1k (Model)`
  - `Avg Throughput / MParam`
  - `Avg Accuracy` (if present)
  - `Total Energy (kWh)`
- Conditional formatting on `Avg Perf/Watt (Model)`: data bars
- Show grand totals: off

## Bookmarks

- **All models** — no slicer filter
- **Llama family** — model_family = "Llama"
- **Compare quantizations** — model_family = "Llama" AND quantization IN (fp16, int8, fp8)

## Acceptance checklist

- [ ] Scatter renders one bubble per model in `vw_model_comparison_matrix`
- [ ] Quantization slicer filters scatter + matrix + bar chart simultaneously
- [ ] Donut totals match `Models Tested` card
- [ ] Per-million-params bar handles models with NULL parameter_count
  gracefully (excludes them rather than erroring)
- [ ] Theme applied; cards have rounded border
