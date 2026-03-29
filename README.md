# GitHub Velocity

Turn your GitHub commit history into a beautiful, interactive velocity report with AI-generated storytelling.

14+ charts. AI milestone annotations. A Delivery Velocity Index that tracks how frontier model releases changed your output. Every report is unique because an LLM reads *your* data and writes *your* story.

## Install

```bash
npx skills add TimCrooker/github-velocity
```

Works with Claude Code, Cursor, Codex CLI, Gemini CLI, and 40+ other agents.

## Use

Just tell your agent:

> generate my github velocity report

Or invoke it directly:

```
/github-velocity
```

The agent takes it from there. It collects your GitHub data, computes the metrics, writes your narrative, and opens the report in your browser.

## Prerequisites

These get auto-installed if you have Homebrew, but just in case:

- [GitHub CLI](https://cli.github.com/) (run `gh auth login` after installing)
- Python 3.8+
- jq (`brew install jq`)

## What You Get

A single-page HTML report with:

- Commit velocity timeline with AI milestone markers
- Delivery Velocity Index (a composite shipping metric)
- Cumulative lines of code: added, deleted, and net
- Six AI eras compared side-by-side
- Impact analysis for each frontier model release
- Language distribution across your stack
- Top repos ranked by impact
- Project showcase with LLM-written descriptions
- Contribution heatmap and annual output charts
- Anomaly callouts for surprising patterns in your data

## How It Works

```
Scripts (deterministic)  >  insights.json    (metrics, charts)
LLM (creative)           >  narratives.json  (your story)
HTML template            >  renders both     (the report)
```

The scripts crunch numbers. The LLM finds meaning. The template renders everything in a cosmic dark theme with glassmorphism, animated starfield, and neon glow charts.

## License

MIT
