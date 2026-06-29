# Dashboard screenshots

This directory holds the human-readable archive of the four Power BI
dashboards.

## Expected files

| File | Dashboard | Spec |
|---|---|---|
| `executive_summary.png` | Executive Summary | [spec](../../powerbi/reports/executive_summary.md) |
| `hardware_performance.png` | Hardware Performance | [spec](../../powerbi/reports/hardware_performance.md) |
| `model_comparison.png` | Model Comparison | [spec](../../powerbi/reports/model_comparison.md) |
| `regression_reliability.png` | Regression Reliability | [spec](../../powerbi/reports/regression_reliability.md) |

PNG at **1920 × 1080**, taken from Power BI Desktop's *File → Export →
Export to PDF* (then crop) or via *Insights → Take screenshot*.

## How to (re)generate them

1. Bring up the warehouse and verify it has data:
   ```powershell
   docker compose up -d
   docker compose exec api benchlens orchestration run sample_csv
   docker compose exec api benchlens orchestration run sample_json
   ```
2. Open the connection file in Power BI Desktop:
   ```powershell
   start ..\..\powerbi\datasets\benchmark_model.pbids
   ```
3. Sign in: **Database** auth, user `benchlens`, password `benchlens`.
4. In Navigator, select all eleven `vw_*` views and click **Load**.
5. Apply the theme: **View → Themes → Browse for themes →
   `powerbi\themes\benchlens_theme.json`**.
6. Follow the spec markdown for the dashboard you're rebuilding. Each spec
   includes the page layout, visual list, measure references, slicer
   defaults, and an acceptance checklist.
7. Save as `<name>.pbix` somewhere outside the repo (or use the local
   `powerbi/reports/` directory — `.pbix` files are gitignored).
8. Take a 1920 × 1080 screenshot and save it here.

## Why no `.pbix` files in git?

See [ADR-9](../decisions.md#adr-9--specs-over-pbix-binaries-in-source-control)
— `.pbix` is a binary container; diffs are useless and the file balloons
the repo. The dashboard markdown + DAX library are the canonical source of
truth.
