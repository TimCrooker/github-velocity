# GitHub Velocity

Turn your GitHub commit history into a beautiful, interactive velocity report — with AI-generated storytelling.

14+ charts. AI milestone annotations. A "Delivery Velocity Index" tracking how each frontier model changed your output. Every report is unique because the narrative is written by an LLM analyzing *your* data.

## Install

```bash
npx skills add TimCrooker/github-velocity
```

Works with Claude Code, Cursor, Codex CLI, Gemini CLI, and 40+ other agents.

## Use

Say this to your agent:

> generate my github velocity report

Or invoke directly:

```
/github-velocity
```

That's it. The agent handles the rest — collecting your GitHub data, computing metrics, writing your story, and opening the report in your browser.

## Prerequisites

- **`gh` CLI** — [install](https://cli.github.com/) and run `gh auth login`
- **Python 3.8+**
- **jq** — `brew install jq`

## What You Get

A single-page HTML report with:

- Commit velocity timeline with AI milestone markers
- Delivery Velocity Index (DVI) — a composite shipping metric
- Cumulative lines of code (added, deleted, net)
- Six AI eras compared side-by-side
- Impact analysis for each frontier model release
- Language distribution across your stack
- Top repos ranked by impact
- Project showcase with LLM-written descriptions
- Contribution heatmap and annual output charts
- Anomaly callouts — surprising patterns in your data

## How It Works

```
Scripts (deterministic)  →  insights.json    (metrics, charts)
LLM (creative)           →  narratives.json  (your story)
HTML template            →  renders both     (the report)
```

The scripts crunch numbers. The LLM finds meaning. The template renders everything in a cosmic dark theme with glassmorphism, animated starfield, and neon glow charts.

## License

MIT
