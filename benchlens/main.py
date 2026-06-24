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
    from sqlalchemy import text

    from benchlens.utils.db import get_engine

    if not yes:
        confirm = typer.confirm(
            "This will DROP all BenchLens tables. Continue?", default=False
        )
        if not confirm:
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(code=1)

    drop_sql = """
        DROP TABLE IF EXISTS fact_kpi_value CASCADE;
        DROP TABLE IF EXISTS fact_benchmark_run CASCADE;
        DROP TABLE IF EXISTS etl_run_log CASCADE;
        DROP TABLE IF EXISTS dim_kpi, dim_model, dim_stack, dim_hardware,
                             dim_workload, dim_date CASCADE;
        DROP TABLE IF EXISTS schema_version CASCADE;
    """
    with get_engine().begin() as conn:
        conn.exec_driver_sql(drop_sql)
    console.print("[green]All BenchLens tables dropped.[/green] Run [bold]benchlens db bootstrap[/bold] to recreate.")


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
) -> None:
    """Run the full ETL pipeline (ingest -> transform -> load) for one source."""
    from benchlens.ingestion import ConnectorError
    from benchlens.load.dim_resolver import UnknownDimensionError
    from benchlens.orchestration import run_pipeline

    try:
        summary = run_pipeline(source, commit_watermark=commit_watermark)
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
        console.print("[yellow]No rows loaded — check quarantine / dimension warnings above.[/yellow]")
        raise typer.Exit(code=1)
    console.print("[green]Pipeline complete.[/green]")


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


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="API bind host."),
    port: int = typer.Option(8000, help="API bind port."),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload."),
) -> None:
    """Start the BenchLens REST API. (Day 6)"""
    console.print(f"[yellow]API server (would bind {host}:{port}, reload={reload}) — implemented on Day 6.[/yellow]")
    raise typer.Exit(code=2)


if __name__ == "__main__":
    app()
