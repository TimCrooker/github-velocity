# GitHub Velocity Report -- Technical Reference

## Data Sources

### 1. user_profile.json
- **API**: `gh api user`
- **Contents**: Login, name, avatar URL, bio, account creation date, public repo count
- **Used for**: Hero section identity, calculating years active

### 2. repos_metadata.json
- **API**: `gh api user/repos --paginate`
- **Contents**: Array of repo objects with: full_name, name, owner, private, fork, language, created_at, updated_at, pushed_at, size, description, topics, default_branch
- **Note**: Paginated responses produce multiple JSON arrays. The collection script merges them into a single flat array using a Python one-liner.
- **Used for**: Repo count, descriptions for "What Was Built" showcase, feeding other API calls

### 3. contribution_calendar.jsonl
- **API**: GraphQL `contributionsCollection` with year-by-year date ranges
- **Contents**: One JSON object per year with: total commit contributions, restricted contributions, daily contribution counts with dates, per-repository commit breakdowns with primary language
- **Used for**: Heatmap visualization, yearly summary, repo activity timeline
- **Note**: Restricted contributions count private repo activity that the API does not break down further

### 4. repo_stats.jsonl
- **API**: `repos/{owner}/{repo}/stats/contributors`
- **Contents**: One JSON object per repo with: total commits, weekly breakdown of additions (a), deletions (d), commits (c), and week timestamp (w)
- **Used for**: Lines of code calculations, monthly line aggregations, per-repo impact rankings
- **Note**: GitHub returns HTTP 202 while computing stats. The script retries up to 4 times with 2-second delays. Week timestamps are Unix epochs (start of week, Sunday).

### 5. search_commits.jsonl
- **API**: `search/commits?q=author:{username}+author-date:{start}..{end}`
- **Contents**: One JSON object per commit with: sha, date, message (first line), repo full name
- **Used for**: Monthly commit counts, repo commit counts, active repo tracking
- **Rate limit**: 30 requests/minute for search API. Script checks remaining quota and waits if needed.
- **Note**: Limited to 1000 results per query. The script uses monthly date ranges to stay under this cap.

### 6. repo_languages.jsonl
- **API**: `repos/{owner}/{repo}/languages`
- **Contents**: One JSON object per repo with a map of language name to byte count
- **Used for**: Language distribution chart, language bar visualization

## Delivery Velocity Index (DVI)

### Formula

```
DVI_raw = commits * 1.0 + max(0, net_lines) * 0.001 + active_repos * 5.0
DVI = DVI_raw / peak_DVI_raw * 100
```

### Components

| Component | Weight | Rationale |
|-----------|--------|-----------|
| Commits | 1.0 (direct) | Raw shipping frequency -- the most reliable signal |
| Net Lines | 0.001 (scaled down) | Code impact (additions minus deletions). Scaled down because line counts are orders of magnitude larger than commit counts |
| Active Repos | 5.0 (scaled up) | Breadth of work across projects. Weighted up because touching 5 repos in a month is more impressive than it sounds |

### Normalization

Peak month = 100. All other months are expressed as a percentage of the peak. This makes DVI comparable across different developers regardless of absolute output levels.

### Rolling Average

3-month rolling window applied to DVI, commits, additions, and net lines. Smooths out vacation weeks, holidays, and sprint variability.

## AI Milestone Dates

These dates mark the public release of frontier AI models that changed how developers code:

| Date | Model | Category | Significance |
|------|-------|----------|-------------|
| 2020-06-11 | GPT-3 | Foundation | First LLM with coding ability (API-only) |
| 2021-06-29 | GitHub Copilot Preview | Coding Tool | First AI pair programmer |
| 2022-06-21 | GitHub Copilot GA | Coding Tool | AI-assisted coding goes mainstream |
| 2022-11-30 | ChatGPT | Foundation | Conversational AI for coding help |
| 2023-03-14 | GPT-4 | Foundation | Complex code generation and architecture |
| 2023-07-11 | Claude 2 | Foundation | 100K context window |
| 2024-03-04 | Claude 3 Opus | Foundation | Near-expert coding |
| 2024-05-13 | GPT-4o | Foundation | Real-time multimodal coding assistance |
| 2024-06-20 | Claude 3.5 Sonnet | Foundation | Best coding model of its era |
| 2024-10-22 | Claude 3.5 Sonnet (new) | Foundation | Computer use, significant coding improvement |
| 2025-01-20 | DeepSeek R1 | Foundation | Open-source reasoning model |
| 2025-02-24 | Claude 3.7 Sonnet | Foundation | Extended thinking for architecture |
| 2025-05-22 | Claude 4 Sonnet | Foundation | Agentic coding era begins |
| 2025-09-25 | Claude 3.6 Opus | Foundation | Deep reasoning + massive context |
| 2026-02-27 | Claude 4.5/4.6 Family | Foundation | 1M context, full project autonomy |

Milestone impact is measured by comparing 3-month average DVI before vs after each release date.

## Era Definitions

Eras segment the developer's history into phases defined by the dominant AI tools available:

| Era | Default Period | Description |
|-----|---------------|-------------|
| Pre-AI | First active month to 2021-05 | Manual coding, no AI assistance |
| Copilot Era | 2021-06 to 2022-10 | GitHub Copilot preview through GA |
| ChatGPT Awakening | 2022-11 to 2023-06 | ChatGPT + GPT-4 as coding partners |
| Foundation Model Arms Race | 2023-07 to 2024-05 | Claude 2/3, GPT-4 Turbo -- models get serious |
| Sonnet Dominance | 2024-06 to 2025-04 | Claude 3.5 Sonnet becomes the developer default |
| Agentic Coding | 2025-05 to present | Claude Code, autonomous agents handle features end-to-end |

The Pre-AI era start date is auto-detected from the first month with commits in the timeline data, not hardcoded.

## Visualization Details

### Commit Timeline Chart
- Bar chart with monthly commit counts
- 3-month rolling average overlay (line)
- AI milestone annotations as vertical dashed lines with rotated labels
- Gradient bar colors transitioning from blue (early) to purple-pink (recent)

### DVI Chart
- Line chart with raw DVI and 3-month rolling average
- Era background annotations as colored boxes
- Y-axis capped at 105 for readability

### Lines of Code Chart
- Stacked area chart: cumulative additions (green), cumulative deletions (red)
- Net lines as dashed blue overlay
- Tooltips show formatted numbers (K/M suffixes)

### Lines per Commit Chart
- Bar chart showing monthly lines_per_commit (additions/commits for that month)
- 3-month rolling average overlay
- Helps identify whether increased output came from more commits or larger commits

### Era Comparison Chart
- Grouped bar chart with average monthly commits per era
- DVI overlay on secondary Y-axis
- Each era gets a distinct color

### Language Distribution
- Doughnut chart with 60% cutout for top languages by byte count
- Color-coded stacked bar at the top showing proportional distribution
- Legend with percentages and language color dots

### Contribution Heatmap
- GitHub-style grid: columns = weeks, rows = days of week
- Color intensity scales from transparent (0) to deep purple (peak)
- Spans from first active year through present

### Repo Activity Timeline
- Horizontal floating bar chart
- Each bar spans from first to last active year for a repository
- Sorted by first active year, filtered to repos with >10 commits

### What Was Built (Project Showcase)
- Top 5 repos displayed as cards with name, org, description, and commit stats
- Descriptions pulled from repos_metadata.json

### Annual Output Chart
- Bar chart with actual commits per year
- Final year includes projected annualized figure (extrapolated from months elapsed)

## Known Limitations of the GitHub API

1. **Stats API 202 responses**: The `stats/contributors` endpoint returns HTTP 202 and empty data while GitHub computes statistics in the background. The script retries 4 times but some repos may still return no data on first run.

2. **Search API rate limit**: 30 requests/minute, 1000 results per query. For very active developers, some commits in dense months may be missed.

3. **Stats API line count inflation**: The stats/contributors API sometimes reports wildly inflated line counts (e.g., 500K additions for a repo with 20 commits). The analysis script filters repos where `additions <= commits` as clearly garbage data.

4. **Private repo visibility**: Contribution calendar shows private repo commit counts but not repo names. The `restricted` field captures this count. Repo-level data is only available for repos the authenticated user can access.

5. **Fork attribution**: Forked repos may include upstream commit history in their stats, inflating numbers for the fork owner.

6. **Language byte counts**: GitHub's language detection counts bytes, not lines. Vendored files, generated code, and lock files can skew language percentages.

7. **Contribution calendar vs Search API**: These can disagree on commit counts. The calendar includes all contributions (issues, PRs, reviews, commits). Search commits are strictly author-date filtered commits. The report uses both: calendar for heatmap/yearly, search for monthly timeline.
