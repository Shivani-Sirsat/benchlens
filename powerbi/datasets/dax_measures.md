# BenchLens — DAX Measures Library

All measures live in a single measure table (`_Measures`) so they appear
together in the Fields pane. Create the host table with:

```dax
_Measures = ROW("placeholder", BLANK())
```

…then move every measure below into it.

Measures are grouped by dashboard but most are reusable across reports.

---

## 1. Run volume + status (Executive Summary)

```dax
Total Runs := COUNTROWS( RunSummary )

Successful Runs :=
CALCULATE( [Total Runs], RunSummary[run_status] = "success" )

Failed Runs :=
CALCULATE( [Total Runs], RunSummary[run_status] IN { "fail", "timeout", "aborted" } )

Success Rate % :=
DIVIDE( [Successful Runs], [Total Runs] ) * 100

Runs (Previous Period) :=
CALCULATE(
    [Total Runs],
    DATEADD( Calendar[Date], -1, MONTH )
)

Runs MoM Δ % :=
VAR cur = [Total Runs]
VAR prev = [Runs (Previous Period)]
RETURN DIVIDE( cur - prev, prev ) * 100
```

---

## 2. Headline KPI averages (Executive Summary)

```dax
Avg Primary KPI :=
AVERAGE( RunSummary[primary_kpi_value] )

Latest Run :=
MAX( RunSummary[started_at] )

Days Since Last Run :=
INT( TODAY() - MAX( RunSummary[run_date] ) )
```

---

## 3. Quality + regression (Executive Summary)

```dax
Findings Count := COUNTROWS( RegressionFindings )

Critical Findings :=
CALCULATE( [Findings Count], RegressionFindings[severity] = "critical" )

Errors :=
CALCULATE( [Findings Count], RegressionFindings[severity] = "error" )

Warnings :=
CALCULATE( [Findings Count], RegressionFindings[severity] = "warning" )

Regression Findings :=
CALCULATE( [Findings Count], RegressionFindings[rule_type] = "regression" )

Findings 7d :=
CALCULATE(
    [Findings Count],
    DATESINPERIOD( Calendar[Date], MAX( Calendar[Date] ), -7, DAY )
)

Avg Deviation % :=
AVERAGE( RegressionFindings[deviation_pct] )
```

---

## 4. ETL health (Executive Summary)

```dax
ETL Pipeline Runs := SUM( EtlHealth[total_runs] )
ETL Successes     := SUM( EtlHealth[success_runs] )
ETL Failures      := SUM( EtlHealth[failed_runs] )

ETL Success % :=
DIVIDE( [ETL Successes], [ETL Pipeline Runs] ) * 100

ETL Rows Loaded     := SUM( EtlHealth[rows_out_total] )
ETL Rows Quarantined:= SUM( EtlHealth[rows_quarantined_total] )

Quarantine Rate % :=
DIVIDE(
    [ETL Rows Quarantined],
    [ETL Rows Loaded] + [ETL Rows Quarantined]
) * 100
```

---

## 5. Hardware efficiency (Hardware Performance dashboard)

```dax
Avg Throughput :=
AVERAGE( HardwareEfficiency[primary_throughput] )

Avg Latency (ms) :=
AVERAGE( HardwareEfficiency[inference_time_ms] )

Avg p95 Latency (ms) :=
AVERAGE( HardwareEfficiency[latency_p95_ms] )

Avg Power (W) :=
AVERAGE( HardwareEfficiency[power_watts_avg] )

-- Perf-per-watt: the headline efficiency KPI. Higher is better.
Perf per Watt :=
AVERAGE( HardwareEfficiency[throughput_per_watt] )

-- Cost-normalized throughput per $1,000 of hardware cost
Perf per $1k :=
AVERAGE( HardwareEfficiency[throughput_per_kdollar] )

-- GPU/CPU/NPU utilization rollups
Avg GPU Util %    := AVERAGE( HardwareEfficiency[gpu_util_pct] )
Avg Memory Util % := AVERAGE( HardwareEfficiency[memory_util_pct] )

-- Total energy consumed (kWh) across the filter context
Energy Used (kWh) := SUM( HardwareEfficiency[energy_kwh] )
```

---

## 6. Best-of comparisons (Hardware Performance dashboard)

```dax
Top Hardware Perf/Watt :=
VAR ranked =
    TOPN(
        1,
        SUMMARIZE(
            HardwareEfficiency,
            HardwareEfficiency[hardware_code],
            "ppw", AVERAGE( HardwareEfficiency[throughput_per_watt] )
        ),
        [ppw], DESC
    )
RETURN MAXX( ranked, HardwareEfficiency[hardware_code] )

Top Hardware Throughput :=
VAR ranked =
    TOPN(
        1,
        SUMMARIZE(
            HardwareEfficiency,
            HardwareEfficiency[hardware_code],
            "tp", AVERAGE( HardwareEfficiency[primary_throughput] )
        ),
        [tp], DESC
    )
RETURN MAXX( ranked, HardwareEfficiency[hardware_code] )
```

---

## 7. Trend deltas (both dashboards)

```dax
KPI Avg (30d) :=
CALCULATE(
    AVERAGE( KpiTrendDaily[kpi_value_avg] ),
    DATESINPERIOD( Calendar[Date], MAX( Calendar[Date] ), -30, DAY )
)

KPI Avg (Previous 30d) :=
CALCULATE(
    AVERAGE( KpiTrendDaily[kpi_value_avg] ),
    DATESINPERIOD(
        Calendar[Date],
        DATEADD( LASTDATE( Calendar[Date] ), -30, DAY ),
        -30,
        DAY
    )
)

KPI Δ % (30d vs 30d) :=
VAR cur  = [KPI Avg (30d)]
VAR prev = [KPI Avg (Previous 30d)]
RETURN DIVIDE( cur - prev, prev ) * 100
```

---

## 8. Conditional-format helpers

```dax
-- Color coding for status cards
Status Color :=
SWITCH(
    TRUE(),
    [Critical Findings] > 0, "#D50000",
    [Errors] > 0,            "#FF6F00",
    [Warnings] > 0,          "#FFAB00",
                             "#00C853"
)

-- Color coding for KPI delta: direction-aware
KPI Δ Color :=
VAR delta = [KPI Δ % (30d vs 30d)]
VAR dir   = SELECTEDVALUE( KpiTrendDaily[kpi_direction], "higher_is_better" )
RETURN
SWITCH(
    TRUE(),
    dir = "higher_is_better" && delta >= 0, "#00C853",
    dir = "higher_is_better" && delta <  0, "#D50000",
    dir = "lower_is_better"  && delta <= 0, "#00C853",
    dir = "lower_is_better"  && delta >  0, "#D50000",
                                           "#9E9E9E"
)
```

---

## Format strings (apply in Model view)

| Measure                  | Format string         |
| ------------------------ | --------------------- |
| `Success Rate %`         | `0.0 "%"`             |
| `Runs MoM Δ %`           | `+0.0 "%";-0.0 "%";0` |
| `KPI Δ % (30d vs 30d)`   | `+0.0 "%";-0.0 "%";0` |
| `Quarantine Rate %`      | `0.00 "%"`            |
| `ETL Success %`          | `0.0 "%"`             |
| `Avg Power (W)`          | `#,##0 " W"`          |
| `Avg Latency (ms)`       | `#,##0.0 " ms"`       |
| `Energy Used (kWh)`      | `0.000 " kWh"`        |
| `Perf per Watt`          | `0.000`               |
| `Perf per $1k`           | `0.00`                |
| Counts (`Total Runs`, …) | `#,##0`               |
