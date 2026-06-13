# eval-search

Benchmark web search APIs for newsletter generation. Runs structured queries across topic categories, scores results on recency, relevance, and newsworthiness using two independent LLM judges, and produces a self-contained HTML report.

## Providers supported

| Provider | Endpoint IDs |
|---|---|
| [Brave Search](https://brave.com/search/api/) | `brave_web` |
| [Exa](https://exa.ai/) | `exa_auto_native`, `exa_auto_fetch`, `exa_neural`, `exa_keyword` |
| [Tavily](https://tavily.com/) | `tavily_news`, `tavily_general` |
| [Serper](https://serper.dev/) | `serper_search`, `serper_news` |
| [SerpApi](https://serpapi.com/) | `serpapi_google_news`, `serpapi_google_search` |

You only need API keys for the providers you intend to test.

## Setup

**Requires Python 3.11+**

```bash
pip install -e .
cp .env.example .env
# Fill in API keys for the providers you want to test
```

## Usage

### Run an evaluation

```bash
# Quick start — technology topic, Exa and Brave, both judges
eval-search run --topics technology --providers exa brave

# Specific endpoints only
eval-search run --topics technology --providers exa --endpoints exa_auto_native,exa_auto_fetch

# Multiple topics, single judge, more results
eval-search run --topics technology,finance --providers exa --max-results 20 --judge claude

# Preview what would run without making API calls
eval-search run --topics technology --providers exa brave --dry-run
```

All options:

| Flag | Default | Description |
|---|---|---|
| `--topics` | all | Comma-separated or repeated. See topics below. |
| `--providers` | all | Comma-separated or repeated. |
| `--endpoints` | all | Comma-separated endpoint IDs to include. |
| `--lookback-days` | 7 | Date window for news freshness. |
| `--max-results` | 10 | Results per query per endpoint. |
| `--queries-per-topic` | 3 | Queries drawn from the query bank. |
| `--judge` | both | `claude`, `openai`, or `both`. |
| `--output-dir` | `./reports` | Where to save JSON and HTML output. |
| `--no-open` | — | Don't auto-open the report in the browser. |
| `--no-html` | — | Save JSON only, skip HTML generation. |
| `--dry-run` | — | Print plan without calling any APIs. |

### Re-generate a report from saved JSON

```bash
eval-search report reports/eval_20260614_000353.json
```

### Explore providers and queries

```bash
eval-search providers          # List all providers and endpoint IDs
eval-search queries technology # Show the query bank for a topic
```

## Topics

`technology` · `finance` · `entertainment` · `music` · `sports` · `science` · `politics` · `investing` · `health` · `business`

## Query bank

Queries live in [`queries.md`](queries.md) — one `## Topic` header per topic, one bullet per query. Edit that file to add, remove, or reword queries. The CLI picks up changes immediately.

## Report sections

The HTML report is a single self-contained file (no server required):

1. **Executive Summary** — relevance, newsworthiness, cost, and latency per endpoint
2. **Recency** — freshness distribution and age box plot
3. **Relevance & Newsworthiness** — heatmaps per judge, inter-judge agreement scatter and Pearson r
4. **Cost** — stacked breakdown: search cost / summarization cost (product) / judge cost (eval)
5. **Latency** — per-endpoint distribution
6. **Raw Data Explorer** — sortable, filterable table of all results including the summary seen by each judge
7. **Methodology** — judge prompts verbatim

## Cost model

Three components are tracked separately:

- **Search cost** — API call cost to the search provider
- **Summarization cost** — Claude Haiku calls to generate article summaries (product cost; zero for endpoints like `exa_auto_native` that return content natively)
- **Judge cost** — LLM calls for evaluation only; not a production cost

The summary table and cost chart show **Product cost** (search + summarization) so comparisons reflect what you'd actually pay in production.

## LLM judges

By default, results are scored by two independent judges:

- **Claude Haiku** (`claude-haiku-4-5-20251001`)
- **GPT-4o-mini**

Each scores relevance and newsworthiness on a 1–5 scale. The report shows both scores side-by-side and computes Pearson r to surface inter-judge disagreement, which helps detect thin or low-quality content that one judge may be more sensitive to.

## Environment variables

See [`.env.example`](.env.example) for all supported variables. At minimum you need the API key for each provider you test, plus `ANTHROPIC_API_KEY` and/or `OPENAI_API_KEY` for judging.
