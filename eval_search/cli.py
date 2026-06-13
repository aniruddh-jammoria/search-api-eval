from __future__ import annotations

import asyncio
import json
import logging
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.table import Table

from eval_search.config import Settings
from eval_search.models import AggregatedMetrics, EvaluationRun, TopicCategory
from eval_search.queries.bank import QUERY_BANK
from eval_search.runner import PROVIDER_FACTORY, run_evaluation

app = typer.Typer(name="eval-search", help="Benchmark search providers for newsletter use cases.", add_completion=False)
console = Console()

_VALID_TOPICS = [t.value for t in TopicCategory]
_VALID_PROVIDERS = list(PROVIDER_FACTORY.keys())
_VALID_JUDGES = {"claude", "openai", "both"}

logging.basicConfig(level=logging.WARNING, format="%(levelname)s  %(name)s  %(message)s")


def _resolve_topics(values: Optional[List[str]]) -> list[TopicCategory]:
    """Accept None (all), or a list of topic names (space- or comma-separated entries)."""
    if not values:
        return list(TopicCategory)
    # Flatten in case user passes "technology,finance" as one token
    parts = [p.strip() for v in values for p in v.split(",") if p.strip()]
    try:
        return [TopicCategory(p) for p in parts]
    except ValueError as e:
        console.print(f"[red]Invalid topic: {e}. Valid: {', '.join(_VALID_TOPICS)}")
        raise typer.Exit(1)


def _resolve_providers(values: Optional[List[str]]) -> list[str]:
    if not values:
        return _VALID_PROVIDERS[:]
    parts = [p.strip() for v in values for p in v.split(",") if p.strip()]
    unknown = [p for p in parts if p not in _VALID_PROVIDERS]
    if unknown:
        console.print(f"[red]Unknown providers: {unknown}. Valid: {', '.join(_VALID_PROVIDERS)}")
        raise typer.Exit(1)
    return parts


@app.command()
def run(
    topics: Optional[List[str]] = typer.Option(
        None, "--topics", "-t",
        help=f"Topics to evaluate. Repeat or comma-separate. Default: all. Options: {', '.join(_VALID_TOPICS)}",
    ),
    providers: Optional[List[str]] = typer.Option(
        None, "--providers", "-p",
        help=f"Providers to include. Repeat or comma-separate. Default: all. Options: {', '.join(_VALID_PROVIDERS)}",
    ),
    endpoints: Optional[str] = typer.Option(None, help="Comma-separated endpoint IDs to include (default: all)"),
    lookback_days: int = typer.Option(7, help="Days to look back for news"),
    max_results: int = typer.Option(10, help="Max results per query per endpoint"),
    queries_per_topic: int = typer.Option(3, help="Queries per topic from the query bank"),
    judge: str = typer.Option("both", help="LLM judges to use: claude, openai, both"),
    output_dir: Path = typer.Option(Path("./reports"), help="Directory for report output"),
    no_html: bool = typer.Option(False, "--no-html", help="Skip HTML report, save JSON only"),
    open_report: bool = typer.Option(True, "--open/--no-open", help="Open the HTML report in the browser after the run"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print what would run without calling any APIs"),
) -> None:
    """Run a full evaluation across search providers and topics."""
    if judge not in _VALID_JUDGES:
        console.print(f"[red]--judge must be one of: {', '.join(_VALID_JUDGES)}")
        raise typer.Exit(1)

    topic_list = _resolve_topics(topics)
    provider_list = _resolve_providers(providers)
    endpoint_list = [e.strip() for e in endpoints.split(",")] if endpoints else None
    judge_list = ["claude", "openai"] if judge == "both" else [judge]

    if dry_run:
        console.print("[bold yellow]DRY RUN - no API calls will be made[/bold yellow]")
        console.print(f"  Topics:            {[t.value for t in topic_list]}")
        console.print(f"  Providers:         {provider_list}")
        console.print(f"  Endpoints filter:  {endpoint_list or 'all'}")
        console.print(f"  Judges:            {judge_list}")
        console.print(f"  Lookback:          {lookback_days} days")
        console.print(f"  Results/query:     {max_results}")
        console.print(f"  Queries/topic:     {queries_per_topic}")
        total = len(provider_list) * len(topic_list) * queries_per_topic
        console.print(f"  Total API calls:   ~{total} (before endpoint expansion)")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    settings = Settings(
        lookback_days=lookback_days,
        max_results_per_query=max_results,
        queries_per_topic=queries_per_topic,
        output_dir=output_dir,
    )

    run_result, metrics = asyncio.run(
        run_evaluation(
            settings=settings,
            topics=topic_list,
            provider_ids=provider_list,
            endpoint_ids=endpoint_list,
            judge_ids=judge_list,
        )
    )

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    json_path = output_dir / f"eval_{ts}.json"
    json_path.write_text(
        json.dumps(
            {
                "run": run_result.model_dump(mode="json"),
                "metrics": [m.model_dump(mode="json") for m in metrics],
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    console.print(f"[green]JSON saved:[/green]  {json_path}")

    if not no_html:
        from eval_search.report.generator import generate_report
        html = generate_report(run_result, metrics)
        html_path = output_dir / f"eval_{ts}.html"
        html_path.write_text(html, encoding="utf-8")
        console.print(f"[green]HTML saved:[/green]  {html_path}")
        if open_report:
            webbrowser.open(html_path.resolve().as_uri())


@app.command()
def report(
    input_path: Path = typer.Argument(..., help="Path to a saved evaluation JSON file"),
    output_path: Optional[Path] = typer.Option(None, "--output", "-o", help="Output HTML path (default: same name as input with .html)"),
    open_report: bool = typer.Option(True, "--open/--no-open", help="Open the HTML report in the browser after generating"),
) -> None:
    """Re-generate the HTML report from a previously saved JSON run."""
    from eval_search.report.generator import generate_report

    if not input_path.exists():
        console.print(f"[red]File not found: {input_path}")
        raise typer.Exit(1)

    data = json.loads(input_path.read_text(encoding="utf-8"))
    run_result = EvaluationRun.model_validate(data["run"])
    metrics_list = [AggregatedMetrics.model_validate(m) for m in data["metrics"]]

    html = generate_report(run_result, metrics_list)
    out = output_path or input_path.with_suffix(".html")
    out.write_text(html, encoding="utf-8")
    console.print(f"[green]HTML saved:[/green] {out}")
    if open_report:
        webbrowser.open(out.resolve().as_uri())


@app.command()
def providers() -> None:
    """List all available search providers and their endpoints."""
    from eval_search.providers.brave import BraveSearchProvider
    from eval_search.providers.exa import ExaSearchProvider
    from eval_search.providers.serpapi import SerpApiProvider
    from eval_search.providers.serper import SerperSearchProvider
    from eval_search.providers.tavily import TavilySearchProvider

    table = Table(title="Available Search Providers & Endpoints")
    table.add_column("Provider", style="bold")
    table.add_column("Endpoint ID", style="cyan")
    table.add_column("Description")
    table.add_column("Date Filter", justify="center")
    table.add_column("News Category", justify="center")

    for cls in [BraveSearchProvider, ExaSearchProvider, TavilySearchProvider, SerperSearchProvider, SerpApiProvider]:
        # Access class-level endpoints without instantiating
        for ep in cls.endpoints:
            table.add_row(
                cls.display_name,
                ep.endpoint_id,
                ep.description,
                "yes" if ep.supports_date_filter else "no",
                "yes" if ep.supports_news_category else "no",
            )

    console.print(table)


@app.command()
def queries(
    topic: str = typer.Argument(..., help=f"Topic name. Options: {', '.join(_VALID_TOPICS)}"),
) -> None:
    """Show the static query bank for a topic."""
    try:
        cat = TopicCategory(topic)
    except ValueError:
        console.print(f"[red]Unknown topic '{topic}'. Valid: {', '.join(_VALID_TOPICS)}")
        raise typer.Exit(1)

    console.print(f"\n[bold]Query bank: {cat.value}[/bold]")
    for i, q in enumerate(QUERY_BANK[cat], 1):
        console.print(f"  {i}. {q}")
    console.print()


if __name__ == "__main__":
    app()
