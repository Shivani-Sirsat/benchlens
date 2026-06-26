# Hardware Performance — Dashboard Spec

**File**: `powerbi/reports/hardware_performance.pbix`
**Page**: single page, 16:9 (1280 × 720)
**Audience**: hardware-evaluation engineers — answers *"Which accelerator
gives the most throughput per watt and per dollar for my workload?"*

## Data sources

- `HardwareEfficiency` (primary fact)
- `KpiTrendDaily` (trend chart)
- `Calendar` (slicer + time intelligence)
- Optional cross-filter from `RunSummary` (drill-down)

## Page layout

```
+--------------------------------------------------------------+
| Title bar: Hardware Performance       [date | workload slicer]|
+----------+----------+-----------+-----------+----------------+
| Avg Tput | Avg Power| Perf/Watt | Perf/$1k  | Energy (kWh)   |
| (card)   | (card)   | (card)    | (card)    | (card)         |
+----------+----------+-----------+-----------+----------------+
|                                                              |
|  Perf-per-Watt by SKU (horizontal bar, ranked)               |
|                                                              |
+----------------------+---------------------------------------+
| Throughput vs Power  | Throughput trend                      |
| (scatter, by vendor) | (line, by hardware)                   |
+----------------------+---------------------------------------+
| Hardware comparison matrix (detail table)                    |
+--------------------------------------------------------------+
```

## Visuals

### V1 — Title + slicers
- Text box: `Hardware Performance` Segoe UI Light 24
- Slicers (top-right strip):
  - `Calendar[Date]` between-slider, default last 90 days
  - `HardwareEfficiency[workload_code]` dropdown (single select), default
    most-recent workload
  - `HardwareEfficiency[accelerator_type]` button list (CPU/GPU/NPU)

### V2 — KPI cards (row 1)
Five `Card` visuals with theme styling.

| # | Title             | Measure                      | Format            |
|---|-------------------|------------------------------|-------------------|
| 1 | AVG THROUGHPUT    | `Avg Throughput`             | `#,##0`           |
| 2 | AVG POWER         | `Avg Power (W)`              | `#,##0 " W"`      |
| 3 | PERF / WATT       | `Perf per Watt`              | `0.000`           |
| 4 | PERF / $1k        | `Perf per $1k`               | `0.00`            |
| 5 | ENERGY            | `Energy Used (kWh)`          | `0.000 " kWh"`    |

Each card adds a sub-line "Best: " using `Top Hardware Perf/Watt` (card 3)
or `Top Hardware Throughput` (card 1).

### V3 — Perf-per-watt ranking
`Stacked bar chart` (horizontal):
- Axis: `HardwareEfficiency[hardware_sku]`
- Legend: `HardwareEfficiency[hardware_vendor]`
- Values: `Perf per Watt`
- Sort: by value desc
- Data labels: on, format `0.000`
- Title: `Perf-per-Watt by SKU (filtered by workload + period)`

### V4 — Throughput vs Power scatter
`Scatter chart`:
- X axis: `Avg Power (W)`
- Y axis: `Avg Throughput`
- Details (legend): `HardwareEfficiency[hardware_sku]`
- Size: `HardwareEfficiency[tdp_watts]`
- Color saturation: `Perf per Watt`
- Plot area trend line: optional, linear regression
- Title: `Throughput vs Power (bubble size = TDP)`

### V5 — Throughput trend
`Line chart`:
- X axis: `Calendar[Date]` (continuous, day)
- Legend: `KpiTrendDaily[hardware_code]` (top 5 by `Perf per Watt`)
- Values: `KpiTrendDaily[kpi_value_avg]`
- Filter (visual): `kpi_code IN { "throughput", "tokens_per_sec" }`
- Show forecast: off

### V6 — Hardware comparison matrix
`Matrix` visual:
- Rows: `HardwareEfficiency[hardware_sku]`
- Columns: `HardwareEfficiency[accelerator_type]`
- Values:
  - `Avg Throughput`
  - `Avg Power (W)`
  - `Perf per Watt`
  - `Perf per $1k`
- Conditional formatting on `Perf per Watt` (data bars, theme accent)
- Show grand totals: off
- Subtotals: off

## Slicers (page-level)

| Slicer field                              | Default            |
| ----------------------------------------- | ------------------ |
| `Calendar[Date]`                          | Last 90 days       |
| `HardwareEfficiency[workload_code]`       | First in list      |
| `HardwareEfficiency[accelerator_type]`    | All                |
| `HardwareEfficiency[hardware_vendor]`     | All                |

## Bookmarks

Create three bookmarks for quick demo:
- **All accelerators** — no accelerator filter
- **GPUs only** — accelerator_type = GPU
- **Compare 4090 vs H100** — sku in {GeForce RTX 4090, H100 80GB}

## Acceptance checklist

- [ ] Workload slicer drives every visual; changing workload re-ranks the
  bar chart
- [ ] Scatter shows each SKU as a distinct bubble; hover tooltip includes
  vendor, TDP, perf-per-watt
- [ ] Cards never display `(Blank)` when at least one successful run exists
  for the selected slicers
- [ ] Matrix sorts SKUs by `Perf per Watt` desc by default
- [ ] Theme applied across all visuals; cards have rounded border
