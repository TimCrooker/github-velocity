---
name: github-velocity
description: Generate a beautiful HTML delivery velocity report from GitHub data
triggers:
  - github velocity
  - delivery velocity
  - github report
  - shipping velocity
  - code velocity
---

# GitHub Delivery Velocity Report

Generate a comprehensive, visual HTML report that tells the story of a developer's GitHub delivery velocity over time, correlated with AI model milestones. The deterministic scripts collect data and compute metrics. YOU generate the creative narrative that makes each report unique.

## Architecture

```
Scripts (deterministic)     →  insights.json      (metrics, charts, timelines)
YOU (creative storyteller)  →  narratives.json     (story, callouts, project profiles)
HTML template               →  consumes BOTH files (renders the full report)
```

The scripts handle numbers. You handle meaning. Don't just describe charts — interpret them. Find the surprising, the personal, the trajectory.

## Workflow

### Step 0: Check Prerequisites (ALWAYS RUN FIRST)

Before anything else, run these checks and auto-install anything missing:

```bash
# Check each prerequisite — install if missing
command -v python3 >/dev/null 2>&1 || { echo "Installing Python..."; brew install python3; }
command -v jq >/dev/null 2>&1 || { echo "Installing jq..."; brew install jq; }
command -v gh >/dev/null 2>&1 || { echo "Installing GitHub CLI..."; brew install gh; }

# Check gh authentication — prompt login if needed
gh auth status >/dev/null 2>&1 || { echo "GitHub CLI not authenticated."; gh auth login; }
```

If `brew` is not available (Linux), use `apt-get install` or `yum install` instead. If `gh auth login` requires interactive input, tell the user to run `! gh auth login` in the prompt so the interactive flow runs in their terminal.

All four must pass before proceeding: `python3 --version && jq --version && gh auth status`

### Step 1: Collect GitHub Data (5-10 min)

```bash
bash ~/.claude/skills/github-velocity/scripts/01_collect_data.sh --output ./gh_dump
```

Flags: `--username NAME` (default: auto-detect), `--output DIR` (default: `./gh_dump`)

Creates: `user_profile.json`, `repos_metadata.json`, `contribution_calendar.jsonl`, `repo_stats.jsonl`, `search_commits.jsonl`, `repo_languages.jsonl`

**Rate limits**: Script respects GitHub API limits. If Search API is rate-limited, it skips gracefully — the report still works. Re-run later to fill gaps.

### Step 2: Compute Metrics

```bash
python3 ~/.claude/skills/github-velocity/scripts/02_analyze.py --input ./gh_dump --output ./gh_dump/insights.json
```

Produces `insights.json` with: monthly timeline, DVI, eras, milestones, language breakdown, top repos, heatmap, data caveats.

### Step 3: Generate Creative Narratives (THIS IS YOUR JOB)

Read `./gh_dump/insights.json` and `./gh_dump/search_commits.jsonl`. Analyze the data deeply, then write `./gh_dump/narratives.json` with these fields:

```json
{
  "hero_tagline": "...",
  "story_intro": "...",
  "section_narratives": {
    "timeline": "...",
    "dvi": "...",
    "lines": "...",
    "lines_per_commit": "...",
    "eras": "...",
    "milestones": "...",
    "languages": "...",
    "repos": "...",
    "heatmap": "...",
    "yearly": "..."
  },
  "anomaly_callouts": ["...", "...", "...", "..."],
  "project_showcases": [
    { "repo": "repo-name", "headline": "THE STARTUP", "narrative": "..." }
  ],
  "work_patterns": "...",
  "closing_statement": "..."
}
```

#### What to analyze:

1. **Commit messages** — Read `search_commits.jsonl` and group by era. Extract dominant themes, vocabulary shifts, what the person was building. The language of commit messages tells a story: are they fixing, building, refactoring, automating?

2. **Heatmap patterns** — Analyze the day-of-week distribution from `insights.json` heatmap data. Are they a weekday coder? Weekend warrior? Do they have streaks? Gaps?

3. **Anomalies** — Find surprising patterns: biggest month-over-month jumps, longest gaps followed by explosions, repos that appeared and disappeared, the relationship between AI milestone dates and velocity changes.

4. **Project identity** — From repo names, descriptions, languages, and commit themes, figure out what each major project IS and write a narrative about it. A repo name alone means nothing — your job is to explain whether it's a SaaS platform, an AI system, a dev tool, etc.

5. **The arc** — What's the overall story? Side-project tinkerer → enterprise engineer → AI-augmented architect? Student → professional → founder? Find the narrative arc in the data.

#### Narrative guidelines:

- **Be specific** — "Your February 2023 spike of 531 commits came two weeks after GPT-4 launched" not "there was a spike in early 2023"
- **Interpret, don't describe** — "The deletion curve keeps pace, meaning code is being actively refactored, not just piled on" not "deletions also increased"
- **Find the human story** — What did they build? Why did they change direction? What does the vocabulary shift reveal?
- **Use the numbers** — Every narrative should reference specific data points from insights.json
- **Hero tagline** — One punchy line that captures the entire trajectory. Use specific numbers.
- **Closing statement** — End with the forward trajectory. What does the acceleration curve suggest?

### Step 4: Assemble the Report

```bash
mkdir -p ~/Desktop/velocity-report
cp ~/.claude/skills/github-velocity/template/velocity.html ~/Desktop/velocity-report/index.html
cp ./gh_dump/insights.json ~/Desktop/velocity-report/insights.json
cp ./gh_dump/narratives.json ~/Desktop/velocity-report/narratives.json
```

### Step 5: View the Report

The HTML loads both JSON files via fetch, so it needs a local server:

```bash
cd ~/Desktop/velocity-report && python3 -m http.server 8080
```

Open `http://localhost:8080` in a browser.

### Step 6: Review and Iterate

Open the report in Playwright or the browser and review. The user may want to:
- Adjust narrative tone or emphasis
- Add/remove anomaly callouts
- Rename eras to reflect their personal journey
- Tweak project showcase descriptions
- Change the color theme (edit CSS `:root` variables)

## Common Issues

| Issue | Fix |
|-------|-----|
| `gh: command not found` | `brew install gh` then `gh auth login` |
| Empty `search_commits.jsonl` | Search API rate-limited. Wait 60s and re-run |
| Charts don't render | Must use HTTP server, not `file://` |
| Very few repos in stats | GitHub stats API needs retries. Re-run collection |
| Narratives feel generic | Read the commit messages more carefully. Find specific project names, themes, vocabulary shifts |

## Output

Single-page HTML with cosmic dark theme, 14+ sections, Chart.js visualizations, AI milestone annotations, and LLM-generated narrative storytelling. Self-contained except for CDN-loaded Chart.js and Google Fonts.
