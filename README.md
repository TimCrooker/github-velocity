# GitHub Velocity

An AI-powered delivery velocity report that turns your entire GitHub commit history into an interactive visual story.

Scripts collect your data deterministically. An LLM interprets the data and writes a narrative unique to your journey. The result is a single-page HTML report with 14+ interactive charts, AI milestone annotations, and a "Delivery Velocity Index" that tracks how frontier model releases changed your output.

## Quick Install

```bash
npx skills add TimCrooker/github-velocity
```

This installs the skill to Claude Code, Cursor, Codex CLI, or any agent that supports the universal SKILL.md format.

Then invoke it:
```
/github-velocity
```

Or say: *"generate my github velocity report"*

## Manual Setup

**Prerequisites:** `gh` CLI (authenticated), Python 3.8+, `jq`

```bash
# 1. Collect GitHub data (~5-10 min)
bash scripts/01_collect_data.sh --output ./gh_dump

# 2. Compute metrics
python3 scripts/02_analyze.py --input ./gh_dump --output ./gh_dump/insights.json

# 3. Generate narratives (LLM reads data, writes the story)
# This step is done by the AI agent — it reads insights.json + search_commits.jsonl
# and writes narratives.json with personalized storytelling

# 4. Assemble and serve
mkdir -p ./report
cp template/velocity.html ./report/index.html
cp ./gh_dump/insights.json ./report/
cp ./gh_dump/narratives.json ./report/
cd ./report && python3 -m http.server 8080
```

Open `http://localhost:8080`

## What You Get

- **Hero section** with total commits, lines added/deleted, net lines, streak, contributions
- **Commit timeline** with AI milestone annotations (GPT-3 through Claude 4.5/4.6)
- **Delivery Velocity Index (DVI)** — composite metric with era-shaded chart
- **Lines of code** — cumulative additions, deletions, net (the code that stayed)
- **Lines per commit** — are AI-era commits bigger or just more frequent?
- **Six eras** — Pre-AI through Agentic Coding, with metrics per era
- **Era comparison** — side-by-side acceleration chart
- **AI milestone impact** — DVI change after each frontier model release
- **Language universe** — distribution across your tech stack
- **Top repositories** — ranked by commits and line impact
- **Project showcase** — LLM-written narratives for your top 5 repos
- **Activity timeline** — Gantt chart of when each project was active
- **Contribution heatmap** — daily activity grid
- **Annual output** — yearly totals with projection for the current year
- **Anomaly callouts** — surprising patterns the LLM found in your data

## Architecture

```
Scripts (deterministic)     →  insights.json      (metrics, charts, timelines)
LLM (creative storyteller)  →  narratives.json     (story, callouts, project profiles)
HTML template               →  consumes BOTH files (renders the full report)
```

The template works without `narratives.json` (renders generic data-driven text), but the LLM-generated narratives are what make each report unique and compelling.

## Flags

### 01_collect_data.sh
| Flag | Default | Description |
|------|---------|-------------|
| `--username` | Auto-detect from `gh` | GitHub username to collect |
| `--output` | `./gh_dump` | Output directory |

### 02_analyze.py
| Flag | Default | Description |
|------|---------|-------------|
| `--input` | `./gh_dump` | Directory with raw data |
| `--output` | `./gh_dump/insights.json` | Where to write insights |
| `--username` | From `user_profile.json` | Username for filtering |

## License

MIT
