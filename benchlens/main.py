"""BenchLens command-line interface.

Usage:
    benchlens --help
    benchlens version
    benchlens db ping
    benchlens db bootstrap          # implemented on Day 2
    benchlens ingest --source NAME  # implemented on Day 3
    benchlens pipeline run          # implemented on Day 4
    benchlens serve                 # implemented on Day 6
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from benchlens import __version__
from benchlens.utils.logger import get_logger

app = typer.Typer(
    name="benchlens",
    help="BenchLens — Benchmark Analytics Platform CLI.",
    no_args_is_help=True,
    add_completion=False,
)

db_app = typer.Typer(help="Database operations.", no_args_is_help=True)
app.add_typer(db_app, name="db")

console = Console()
log = get_logger(__name__)


# ---------- root commands ----------


@app.command()
def version() -> None:
    """Print the BenchLens version."""
    console.print(f"[bold cyan]BenchLens[/bold cyan] v{__version__}")


@app.command()
def info() -> None:
    """Print a quick environment summary."""
    from benchlens.utils.config_loader import load_config

    settings = load_config("settings")
    table = Table(title="BenchLens runtime", show_header=True, header_style="bold cyan")
    table.add_column("Key")
    table.add_column("Value")
    table.add_row("Version", __version__)
    table.add_row("Environment", str(settings["app"]["environment"]))
    table.add_row("DB host", str(settings["database"]["host"]))
    table.add_row("DB name", str(settings["database"]["name"]))
    table.add_row("API host:port", f"{settings['api']['host']}:{settings['api']['port']}")
    console.print(table)


# ---------- db subcommands ----------


@db_app.command("ping")
def db_ping() -> None:
    """Check that the warehouse is reachable."""
    from benchlens.utils.db import ping

    if ping():
        console.print("[green]OK[/green] — database is reachable.")
        raise typer.Exit(code=0)
    console.print("[red]FAIL[/red] — could not connect. Check .env / docker-compose.")
    raise typer.Exit(code=1)


@db_app.command("bootstrap")
def db_bootstrap() -> None:
    """Create the warehouse schema, load seed data, and apply migrations."""
    from scripts.bootstrap_db import main as run_bootstrap

    code = run_bootstrap()
    raise typer.Exit(code=code)


@db_app.command("reset")
def db_reset(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Drop and recreate all warehouse tables (dev only)."""

    from benchlens.utils.db import get_engine

    if not yes:
        confirm = typer.confirm("This will DROP all BenchLens tables. Continue?", default=False)
        if not confirm:
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(code=1)

    drop_sql = """
        DROP TABLE IF EXISTS quality_check_result CASCADE;
        DROP TABLE IF EXISTS fact_kpi_value CASCADE;
        DROP TABLE IF EXISTS fact_benchmark_run CASCADE;
        DROP TABLE IF EXISTS etl_run_log CASCADE;
        DROP TABLE IF EXISTS dim_kpi, dim_model, dim_stack, dim_hardware,
                             dim_workload, dim_date CASCADE;
        DROP TABLE IF EXISTS schema_version CASCADE;
    """
    with get_engine().begin() as conn:
        conn.exec_driver_sql(drop_sql)
    console.print(
        "[green]All BenchLens tables dropped.[/green] Run [bold]benchlens db bootstrap[/bold] to recreate."
    )


# ---------- pipeline subcommands ----------

pipeline_app = typer.Typer(help="ETL pipeline operations.", no_args_is_help=True)
app.add_typer(pipeline_app, name="pipeline")


@pipeline_app.command("run")
def pipeline_run(
    source: str = typer.Option(..., "--source", "-s", help="Source name from sources.yaml."),
    commit_watermark: bool = typer.Option(
        False,
        "--commit-watermark",
        help="Persist the new watermark after a successful run.",
    ),
    skip_quality: bool = typer.Option(
        False,
        "--skip-quality",
        help="Skip the data-quality / regression-detection phase.",
    ),
) -> None:
    """Run the full ETL pipeline (ingest -> transform -> load -> DQ) for one source."""
    from benchlens.ingestion import ConnectorError
    from benchlens.load.dim_resolver import UnknownDimensionError
    from benchlens.orchestration import run_pipeline

    try:
        summary = run_pipeline(
            source,
            commit_watermark=commit_watermark,
            run_quality=not skip_quality,
        )
    except ConnectorError as e:
        console.print(f"[red]Connector error:[/red] {e}")
        raise typer.Exit(code=1) from None
    except UnknownDimensionError as e:
        console.print(f"[red]Unknown dimension:[/red] {e}")
        raise typer.Exit(code=1) from None

    table = Table(title="Pipeline summary", show_header=True, header_style="bold cyan")
    table.add_column("Field")
    table.add_column("Value")
    for k, v in summary.as_table_rows():
        table.add_row(k, v)
    console.print(table)

    if summary.runs_upserted == 0 and summary.rows_extracted > 0:
        console.print(
            "[yellow]No rows loaded — check quarantine / dimension warnings above.[/yellow]"
        )
        raise typer.Exit(code=1)
    console.print("[green]Pipeline complete.[/green]")


# ---------- quality subcommands ----------

quality_app = typer.Typer(help="Data quality + regression detection.", no_args_is_help=True)
app.add_typer(quality_app, name="quality")


@quality_app.command("rules")
def quality_rules() -> None:
    """List rules currently loaded from config/dq_rules.yaml."""
    from benchlens.quality import load_rules

    rules = load_rules()
    table = Table(
        title=f"DQ rules ({len(rules)} total)", show_header=True, header_style="bold cyan"
    )
    table.add_column("ID")
    table.add_column("Type")
    table.add_column("Severity")
    table.add_column("KPI / param")
    table.add_column("Description")
    for r in rules.range_rules:
        bounds = f"{r.kpi_code} in [{r.min}, {r.max}]"
        table.add_row(r.id, r.type, r.severity, bounds, r.description or "")
    for r in rules.freshness_rules:
        table.add_row(r.id, r.type, r.severity, f"max_age={r.max_age_days}d", r.description or "")
    for r in rules.regression_rules:
        params = f"{r.kpi_code} {r.threshold_pct}% / {r.baseline_runs}-run baseline"
        table.add_row(r.id, r.type, r.severity, params, r.description or "")
    console.print(table)


@quality_app.command("history")
def quality_history(
    source: str | None = typer.Option(None, "--source", "-s", help="Filter by source name."),
    limit: int = typer.Option(20, "--limit", help="Most-recent findings to show."),
) -> None:
    """Show the most recent persisted DQ findings."""
    from sqlalchemy import select

    from benchlens.utils.db import session_scope
    from benchlens.warehouse.models import QualityCheckResult

    with session_scope() as session:
        stmt = select(QualityCheckResult).order_by(QualityCheckResult.detected_at.desc())
        if source:
            stmt = stmt.where(QualityCheckResult.source_name == source)
        stmt = stmt.limit(limit)
        rows = list(session.execute(stmt).scalars())

    if not rows:
        console.print("[yellow]No findings yet.[/yellow]")
        return

    table = Table(
        title=f"DQ findings (latest {len(rows)})", show_header=True, header_style="bold cyan"
    )
    table.add_column("Detected at")
    table.add_column("Severity")
    table.add_column("Rule")
    table.add_column("KPI")
    table.add_column("Observed")
    table.add_column("Baseline/min/max")
    table.add_column("Message", overflow="fold")
    for r in rows:
        bm = (
            str(r.baseline_value)
            if r.baseline_value is not None
            else f"[{r.expected_min}, {r.expected_max}]"
        )
        table.add_row(
            r.detected_at.strftime("%Y-%m-%d %H:%M:%S"),
            r.severity,
            f"{r.rule_type}:{r.rule_id}",
            r.kpi_code or "",
            str(r.observed_value) if r.observed_value is not None else "",
            bm,
            r.message or "",
        )
    console.print(table)


@app.command()
def ingest(
    source: str = typer.Option(..., "--source", "-s", help="Source name from sources.yaml."),
    save_raw: bool = typer.Option(
        False, "--save-raw", help="Write the extracted DataFrame to data/raw_extracts/."
    ),
    commit_watermark: bool = typer.Option(
        False,
        "--commit-watermark",
        help="Persist the new watermark after extraction (default: dry-run).",
    ),
    limit: int = typer.Option(10, "--limit", help="Rows to preview in the console."),
) -> None:
    """Run a single connector and print a summary of the extracted DataFrame."""
    from pathlib import Path

    from benchlens.ingestion import ConnectorError, build_connector_by_name

    try:
        connector = build_connector_by_name(source)
    except ConnectorError as e:
        console.print(f"[red]ERROR[/red] {e}")
        raise typer.Exit(code=2) from None

    console.print(
        f"[cyan]Ingest[/cyan] source=[bold]{source}[/bold] kind=[bold]{connector.kind}[/bold]"
    )
    try:
        result = connector.run()
    except ConnectorError as e:
        console.print(f"[red]Connector failed:[/red] {e}")
        raise typer.Exit(code=1) from None

    df = result.records
    summary = Table(title="Extraction summary", show_header=True, header_style="bold cyan")
    summary.add_column("Field")
    summary.add_column("Value")
    summary.add_row("Source", result.source)
    summary.add_row("Connector", result.connector)
    summary.add_row("Rows", str(result.rows))
    summary.add_row("Columns", str(len(df.columns)))
    summary.add_row("New watermark", str(result.new_watermark))
    summary.add_row("Extracted at", result.extracted_at.isoformat())
    console.print(summary)

    if result.rows:
        preview = Table(title=f"Preview (first {min(limit, result.rows)} rows)", show_header=True)
        for col in df.columns[:8]:
            preview.add_column(str(col))
        for _, row in df.head(limit).iterrows():
            preview.add_row(*[str(row[c]) for c in df.columns[:8]])
        console.print(preview)

    if save_raw and result.rows:
        out_dir = Path("data") / "raw_extracts"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{source}_{result.extracted_at.strftime('%Y%m%dT%H%M%S')}.parquet"
        try:
            df.to_parquet(out_path)
        except Exception:
            out_path = out_path.with_suffix(".csv")
            df.to_csv(out_path, index=False)
        console.print(f"[green]Saved[/green] {out_path}")

    if commit_watermark and result.new_watermark is not None:
        connector.commit_watermark(result.new_watermark)
        console.print(f"[green]Watermark committed:[/green] {result.new_watermark}")


# ---------- reports subcommands ----------

reports_app = typer.Typer(help="Reporting views + Power BI helpers.", no_args_is_help=True)
app.add_typer(reports_app, name="reports")

views_app = typer.Typer(help="Manage Power BI-facing SQL views.", no_args_is_help=True)
reports_app.add_typer(views_app, name="views")


@views_app.command("check")
def reports_views_check() -> None:
    """List reporting views with existence + row counts."""
    from benchlens.reports import check_views

    infos = check_views()
    table = Table(title="Reporting views", show_header=True, header_style="bold cyan")
    table.add_column("View")
    table.add_column("Installed")
    table.add_column("Rows", justify="right")
    table.add_column("Description")
    missing = 0
    for info in infos:
        installed = "[green]yes[/green]" if info.exists else "[red]no[/red]"
        rows = "" if info.row_count is None else f"{info.row_count:,}"
        if not info.exists:
            missing += 1
        table.add_row(info.name, installed, rows, info.description)
    console.print(table)
    if missing:
        console.print(
            f"[yellow]{missing} view(s) missing.[/yellow] "
            "Run [bold]benchlens reports views refresh[/bold] to (re)install."
        )
        raise typer.Exit(code=1)


@views_app.command("refresh")
def reports_views_refresh() -> None:
    """(Re)create all reporting views from migration 003."""
    from benchlens.reports import refresh_views

    names = refresh_views()
    console.print(f"[green]Refreshed[/green] {len(names)} reporting view(s): " + ", ".join(names))


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="API bind host."),
    port: int = typer.Option(8000, help="API bind port."),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload."),
    workers: int = typer.Option(1, "--workers", help="Worker count (incompatible with --reload)."),
) -> None:
    """Start the BenchLens REST API (FastAPI + JWT + RBAC)."""
    import uvicorn

    console.print(
        f"[cyan]BenchLens API[/cyan] binding [bold]{host}:{port}[/bold] "
        f"(reload={reload}, workers={workers}). Docs at /docs."
    )
    uvicorn.run(
        "benchlens.api.app:app",
        host=host,
        port=port,
        reload=reload,
        workers=workers if not reload else 1,
        log_level="info",
    )


# ---------- scheduler subcommands ----------

scheduler_app = typer.Typer(help="ETL scheduler (APScheduler).", no_args_is_help=True)
app.add_typer(scheduler_app, name="scheduler")


@scheduler_app.command("list")
def scheduler_list() -> None:
    """Show the jobs that would be scheduled (does not start the scheduler)."""
    from benchlens.scheduler import build_default_registry

    registry = build_default_registry()
    if not len(registry):
        console.print(
            "[yellow]No enabled sources.[/yellow] "
            "Set [bold]enabled: true[/bold] in config/sources.yaml."
        )
        raise typer.Exit(code=0)

    table = Table(
        title=f"Scheduled jobs ({len(registry)})",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Job ID")
    table.add_column("Cron")
    table.add_column("Description")
    for job in registry:
        table.add_row(job.job_id, job.cron, job.description)
    console.print(table)


@scheduler_app.command("start")
def scheduler_start() -> None:
    """Start the blocking scheduler (Ctrl+C to exit)."""
    from benchlens.scheduler import SchedulerRunner

    console.print("[cyan]Starting BenchLens scheduler[/cyan] (UTC). Ctrl+C to exit.")
    SchedulerRunner().start()


if __name__ == "__main__":
    app()
