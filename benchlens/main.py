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
def pipeline_run(source: str = typer.Option(..., "--source", "-s", help="Source name from sources.yaml.")) -> None:
    """Run the end-to-end ETL pipeline for a given source. (Day 4)"""
    console.print(f"[yellow]Pipeline run for source '{source}' — implemented on Day 4.[/yellow]")
    raise typer.Exit(code=2)


@app.command()
def ingest(source: str = typer.Option(..., "--source", "-s", help="Source name from sources.yaml.")) -> None:
    """Ingest from a configured source. (Day 3)"""
    console.print(f"[yellow]Ingest for source '{source}' — implemented on Day 3.[/yellow]")
    raise typer.Exit(code=2)


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
