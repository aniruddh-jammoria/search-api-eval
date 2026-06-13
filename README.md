# search-api-eval

Picking a search API for a content pipeline is harder than it looks. Different providers return very different results — in freshness, relevance, and cost — and those differences compound when you're running queries across multiple topics every day.

**search-api-eval** is a benchmarking framework that runs the same queries across multiple search providers, scores the results using two independent LLM judges (Claude and GPT-4o-mini), and produces a self-contained HTML report so you can compare providers on the metrics that actually matter for your use case.

It was built with newsletter generation in mind, but the evaluation criteria — recency, relevance, newsworthiness, and cost — apply to most content pipelines.

A [sample report](https://aniruddh-jammoria.github.io/search-api-eval/sample_reports/exa_auto_native_vs_brave_news_ai_topic.html) is available so you can see what the output looks like before running your own eval.

## How it works

```
Query bank → Search providers → Fetch & summarize → LLM judges → HTML report + recommendation
```

1. **Search** — the same queries are sent to every provider you select
2. **Summarize** — each result's page content is fetched and summarized using Claude Haiku (providers that return article content natively skip this step)
3. **Judge** — Claude Haiku and GPT-4o-mini independently score each result on relevance and newsworthiness (1–5)
4. **Report** — a single HTML file with charts, tables, and a raw data explorer is saved to `./reports/`
5. **Recommend** — Claude generates a plain-prose recommendation and embeds it at the top of the report

---

## Setup

**Requires Python 3.11+**

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # macOS / Linux
.venv\Scripts\activate           # Windows

# 2. Install
pip install -e .

# 3. Configure API keys
cp .env.example .env
# Open .env and fill in keys for the providers and judges you want to use
```

You need:
- An **Anthropic API key** (`ANTHROPIC_API_KEY`) — required for summarization and for the Claude judge
- An **OpenAI API key** (`OPENAI_API_KEY`) — required for the GPT-4o-mini judge
- API keys for whichever **search providers** you want to test (you don't need all of them)

---

## Quick start

```bash
eval-search run --topics technology --providers exa brave
```

This runs 3 queries across Exa and Brave for the technology topic, scores all results, and opens the HTML report in your browser when done.

To preview what would run without making any API calls:

```bash
eval-search run --topics technology --providers exa brave --dry-run
```

---

## Providers and endpoints

Each provider can expose multiple **endpoints** — different search modes that return results differently. You can test all endpoints or pick specific ones with `--endpoints`.

Run `eval-search providers` to see this table in your terminal at any time.

### Brave Search
| Endpoint ID | Description |
|---|---|
| `brave_web` | General web search with freshness filter. Returns a broad mix including homepages and aggregators. |
| `brave_news` | News-specific index with freshness filter. Better for finding individual articles. |

### Exa
| Endpoint ID | Description |
|---|---|
| `exa_auto_native` | Auto search with article highlights returned directly in the API response. No separate fetch/summarize step — content cost is baked into the search cost. |
| `exa_auto_fetch` | Auto search without highlights. Pages are fetched and summarized with Claude Haiku separately. Useful for comparing content quality against native highlights. |
| `exa_auto` | Auto search type with news category filter and highlights. |
| `exa_neural` | Semantic (neural) search with news category filter. Good for conceptual or broad queries. |
| `exa_keyword` | Keyword search without news category filter. Most similar to traditional search behaviour. |

### Tavily
| Endpoint ID | Description |
|---|---|
| `tavily_news` | News topic mode. Note: Tavily does not return publication dates, so recency scoring will show "Unknown" for all results. |
| `tavily_general` | General search at advanced depth. Same limitation on publication dates. |

### Serper
| Endpoint ID | Description |
|---|---|
| `serper_search` | Google web results via Serper with a time filter. |
| `serper_news` | Google News results via Serper with a past-week filter. |

### SerpApi
| Endpoint ID | Description |
|---|---|
| `serpapi_google_news` | Google News via SerpApi (`engine=google_news`). Returns publication timestamps. |
| `serpapi_google_search` | Google web search via SerpApi filtered to the news tab. |

---

## Topics

Eleven topics are available out of the box:

`ai` · `technology` · `finance` · `entertainment` · `music` · `sports` · `science` · `politics` · `investing` · `health` · `business`

The `ai` topic is purpose-built for AI newsletter use cases, with queries covering foundation model releases, big lab product updates, hardware, LLM research, agentic AI, open source models, safety/policy, and infrastructure.

---

## Query bank

The queries sent to each provider live in [`queries.md`](queries.md). The format is simple — one `## Topic` heading per topic, one bullet per query:

```markdown
## Technology
- latest AI model releases this week
- enterprise software funding rounds
- new chip announcements
```

To customize queries for your use case, edit `queries.md` directly. The CLI picks up changes immediately — no restart needed.

You can preview the current queries for any topic:

```bash
eval-search queries technology
```

---

## All CLI options

### `eval-search run`

| Flag | Default | Description |
|---|---|---|
| `--topics` | all | Topics to evaluate. Comma-separated or repeat the flag. |
| `--providers` | all | Providers to include. Comma-separated or repeat the flag. |
| `--endpoints` | all | Specific endpoint IDs to include (comma-separated). |
| `--lookback-days` | `7` | How far back to look for news. |
| `--max-results` | `10` | Results per query per endpoint. |
| `--queries-per-topic` | `3` | How many queries to draw from the query bank per topic. |
| `--judge` | `both` | Which LLM judges to use: `claude`, `openai`, or `both`. |
| `--output-dir` | `./reports` | Where to save the JSON and HTML output. |
| `--no-open` | — | Don't auto-open the report in the browser after the run. |
| `--no-html` | — | Save JSON only, skip HTML generation. |
| `--dry-run` | — | Print what would run without calling any APIs. |

### `eval-search report`

Re-generate the HTML report from a previously saved JSON file. Useful if you've updated the report template or want to re-render old results.

```bash
eval-search report reports/eval_<timestamp>.json
```

### `eval-search providers` / `eval-search queries`

```bash
eval-search providers          # List all providers and endpoints
eval-search queries technology # Show query bank for a topic
```

---

## What's in the report

The output is a single self-contained HTML file — no server needed, just open it in a browser.

| Section | What you'll find |
|---|---|
| **Recommendation** | AI-generated plain-prose recommendation directly below the summary table |
| **Executive Summary** | Relevance, newsworthiness, product cost, and latency per endpoint at a glance |
| **Recency** | How fresh the results are — freshness distribution and age box plot |
| **Relevance & Newsworthiness** | Score heatmaps per judge, inter-judge agreement scatter, and Pearson r |
| **Cost** | Stacked breakdown by component: search / summarization / judge |
| **Latency** | Per-endpoint response time distribution |
| **Raw Data Explorer** | Sortable, filterable table of every result — including the summary shown to each judge |
| **Methodology** | The exact prompts used by each judge |

---

## Cost model

Three components are tracked separately so you can see what you'd actually pay in production versus what's just eval overhead:

| Component | What it covers | Production cost? |
|---|---|---|
| **Search** | API call to the search provider | Yes |
| **Summarization** | Claude Haiku calls to fetch and summarize article content | Yes (zero for endpoints that return content natively, like `exa_auto_native`) |
| **Judge** | LLM calls used to score results | No — eval framework only |

The summary table and cost chart show **Product cost** (search + summarization) so comparisons reflect what you'd pay when running the pipeline for real.

---

## LLM judges

By default, every result is scored by two independent judges:

- **Claude Haiku** (`claude-haiku-4-5-20251001`)
- **GPT-4o-mini**

Each judge scores relevance and newsworthiness on a 1–5 scale. Running two judges helps surface results where the scores diverge sharply — which often signals thin content, paywalled pages, or homepage-style results that one model penalizes more than the other.

The report shows both scores side-by-side and computes Pearson r per endpoint so you can see at a glance how much the judges agree.

The judge prompts are in [`eval_search/judges/prompts.py`](eval_search/judges/prompts.py) and are printed verbatim in the Methodology section of every report.

---

## Customizing for your own use case

eval-search is designed to be adapted. Here's where to make changes:

| What you want to change | Where to change it |
|---|---|
| Search queries | [`queries.md`](queries.md) |
| Topics available | `TopicCategory` enum in [`eval_search/models.py`](eval_search/models.py) |
| Relevance / newsworthiness rubric | [`eval_search/judges/prompts.py`](eval_search/judges/prompts.py) |
| Recommendation prompt and focus | [`eval_search/report/recommendation_prompt.md`](eval_search/report/recommendation_prompt.md) |
| Which providers run by default | `--providers` flag or update defaults in [`eval_search/cli.py`](eval_search/cli.py) |
| Lookback window, result count, concurrency | `--lookback-days`, `--max-results`, or set defaults in `.env` |
| Report appearance | [`eval_search/report/templates/report.html.j2`](eval_search/report/templates/report.html.j2) |

---

## Feedback

If you run into a bug, have a question, or want to suggest a provider or feature, please [open an issue](https://github.com/aniruddh-jammoria/search-api-eval/issues). Contributions are welcome.
