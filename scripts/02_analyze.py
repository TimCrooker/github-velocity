#!/usr/bin/env python3
"""
GitHub Data Analyzer — Computes delivery velocity metrics and insights
from raw GitHub data dump.

Outputs: insights.json consumed by the HTML visualization.

Usage:
  python3 02_analyze.py [--input DIR] [--output PATH] [--username NAME]
"""

import argparse
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ============================================================
# CLI Arguments
# ============================================================
parser = argparse.ArgumentParser(description="Analyze GitHub data and generate insights.json")
parser.add_argument("--input", default="./gh_dump", help="Directory with raw data files (default: ./gh_dump)")
parser.add_argument("--output", default=None, help="Output path for insights.json (default: <input>/insights.json)")
parser.add_argument("--username", default=None, help="GitHub username for filtering (default: from user_profile.json)")
args = parser.parse_args()

DUMP_DIR = Path(args.input)
OUTPUT = Path(args.output) if args.output else DUMP_DIR / "insights.json"

# ============================================================
# AI Model Milestones (frontier releases that changed coding)
# ============================================================
AI_MILESTONES = [
    {"date": "2020-06-11", "name": "GPT-3", "category": "foundation",
     "description": "First large language model with coding ability. API-only, limited access."},
    {"date": "2021-06-29", "name": "GitHub Copilot Preview", "category": "coding_tool",
     "description": "First AI pair programmer. Autocomplete-style code suggestions in-editor."},
    {"date": "2022-06-21", "name": "GitHub Copilot GA", "category": "coding_tool",
     "description": "Copilot becomes generally available. AI-assisted coding goes mainstream."},
    {"date": "2022-11-30", "name": "ChatGPT", "category": "foundation",
     "description": "GPT-3.5 chat interface. Developers start using conversational AI for coding help."},
    {"date": "2023-03-14", "name": "GPT-4", "category": "foundation",
     "description": "Major reasoning leap. Complex code generation, debugging, architecture design."},
    {"date": "2023-07-11", "name": "Claude 2", "category": "foundation",
     "description": "Anthropic's first widely-available model. 100K context window."},
    {"date": "2024-03-04", "name": "Claude 3 Opus", "category": "foundation",
     "description": "Near-expert coding. Opus sets new bar for complex software engineering."},
    {"date": "2024-05-13", "name": "GPT-4o", "category": "foundation",
     "description": "Faster, multimodal GPT-4. Real-time coding assistance becomes practical."},
    {"date": "2024-06-20", "name": "Claude 3.5 Sonnet", "category": "foundation",
     "description": "Best coding model of its era. Sonnet becomes the developer default."},
    {"date": "2024-10-22", "name": "Claude 3.5 Sonnet (new)", "category": "foundation",
     "description": "Updated Sonnet with computer use. Significant coding improvement."},
    {"date": "2025-01-20", "name": "DeepSeek R1", "category": "foundation",
     "description": "Open-source reasoning model. Chain-of-thought for complex problems."},
    {"date": "2025-02-24", "name": "Claude 3.7 Sonnet", "category": "foundation",
     "description": "Extended thinking. Hybrid fast/deep reasoning for architecture decisions."},
    {"date": "2025-05-22", "name": "Claude 4 Sonnet", "category": "foundation",
     "description": "Claude Code era begins. Agentic coding — full codebase understanding and autonomous implementation."},
    {"date": "2025-06-25", "name": "Claude Opus 4", "category": "foundation",
     "description": "Opus returns. Deep reasoning + massive context for complex engineering."},
    {"date": "2026-02-27", "name": "Claude 4.5/4.6 Family", "category": "foundation",
     "description": "Current generation. 1M context, agentic workflows, full project autonomy."},
]

# ============================================================
# Load data
# ============================================================

def load_jsonl(path):
    items = []
    if not path.exists():
        print(f"  Warning: {path} not found, skipping")
        return items
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return items

print("Loading data...")
contribution_calendar = load_jsonl(DUMP_DIR / "contribution_calendar.jsonl")
repo_stats = load_jsonl(DUMP_DIR / "repo_stats.jsonl")
search_commits = load_jsonl(DUMP_DIR / "search_commits.jsonl")
repo_languages = load_jsonl(DUMP_DIR / "repo_languages.jsonl")

# Load collaboration stats (REST Search API — includes private repos)
collaboration_path = DUMP_DIR / "collaboration.json"
if collaboration_path.exists():
    with open(collaboration_path) as f:
        collaboration_stats = json.load(f)
else:
    collaboration_stats = {}

with open(DUMP_DIR / "repos_metadata.json") as f:
    repos_metadata = json.load(f)

# Build repo description lookup from metadata
repo_descriptions = {}
for repo in repos_metadata:
    repo_descriptions[repo["full_name"]] = repo.get("description") or ""

with open(DUMP_DIR / "user_profile.json") as f:
    user_profile = json.load(f)

# Resolve username
USERNAME = args.username or user_profile.get("login", "unknown")
print(f"  Username: {USERNAME}")

# ============================================================
# 1. Build unified daily timeline from contribution calendar
# ============================================================
print("Building daily timeline...")

daily_contributions = {}  # date_str -> contribution_count
yearly_summary = {}

for year_data in contribution_calendar:
    year = year_data["year"]
    yearly_summary[year] = {
        "commits_graphql": year_data["commits"],
        "restricted": year_data.get("restricted", 0),
        "total_contributions": year_data["total_contributions"],
        "repos": year_data.get("repos", []),
    }
    for day in year_data.get("days", []):
        if day["contributionCount"] > 0:
            daily_contributions[day["date"]] = day["contributionCount"]

# ============================================================
# 2. Build monthly commit/contribution timeline from calendar
#    (Search API data is unreliable — it returns false-positive
#     commits from unrelated repos. The GraphQL contribution
#     calendar is the authoritative source.)
# ============================================================
print("Building monthly contribution timeline...")

monthly_contributions = defaultdict(int)
monthly_active_days = defaultdict(int)

for date_str, count in daily_contributions.items():
    month_key = date_str[:7]  # YYYY-MM
    monthly_contributions[month_key] += count
    monthly_active_days[month_key] += 1

# Build per-year repo mapping from contribution calendar
yearly_repos = {}
for year_data in contribution_calendar:
    year = str(year_data["year"])
    yearly_repos[year] = year_data.get("repos", [])

# For backward compat, alias monthly_contributions as monthly_commits
monthly_commits = monthly_contributions

# Build repo commit counts from calendar yearly repo data (accurate)
repo_commit_counts = defaultdict(int)
for year_data in contribution_calendar:
    for repo_info in year_data.get("repos", []):
        repo_commit_counts[repo_info["repo"]] += repo_info["commits"]

# Monthly repos: approximate from yearly data (distribute evenly)
# since calendar only gives per-year repo breakdown
monthly_repos = defaultdict(set)
for year_data in contribution_calendar:
    year = str(year_data["year"])
    year_repos = {r["repo"] for r in year_data.get("repos", [])}
    # Assign repos to months that had contributions in that year
    for month_key in monthly_contributions:
        if month_key.startswith(year):
            monthly_repos[month_key] = year_repos

commit_dates = list(daily_contributions.keys())

# ============================================================
# 3. Build weekly line stats from repo_stats (additions/deletions)
# ============================================================
print("Building weekly line stats...")

weekly_lines = defaultdict(lambda: {"additions": 0, "deletions": 0, "commits": 0})
repo_totals = {}
repo_active_range = {}  # repo_name -> (first_active_date, last_active_date)
data_caveats = []

# First pass: compute per-repo totals to identify garbage repos
garbage_repos = set()
for repo_data in repo_stats:
    repo_name = repo_data["repo"]
    total_add = sum(w["a"] for w in repo_data["weeks"])
    total_commits = repo_data["total_commits"]
    if total_add <= total_commits and total_add > 0:
        garbage_repos.add(repo_name)

if garbage_repos:
    data_caveats.append(
        f"{len(garbage_repos)} repos excluded from line counts due to clearly invalid "
        f"GitHub Stats API data (additions <= commits)."
    )

# Second pass: build weekly/repo stats, skipping garbage repos
for repo_data in repo_stats:
    repo_name = repo_data["repo"]
    if repo_name in garbage_repos:
        continue

    total_add = 0
    total_del = 0
    total_commits = repo_data["total_commits"]
    active_dates = []

    for week in repo_data["weeks"]:
        # week timestamp is Unix epoch (start of week)
        week_date = datetime.fromtimestamp(week["w"], tz=timezone.utc).strftime("%Y-%m-%d")
        weekly_lines[week_date]["additions"] += week["a"]
        weekly_lines[week_date]["deletions"] += week["d"]
        weekly_lines[week_date]["commits"] += week["c"]
        total_add += week["a"]
        total_del += week["d"]
        # Track weeks with actual activity (commits, additions, or deletions > 0)
        if week["c"] > 0 or week["a"] > 0 or week["d"] > 0:
            active_dates.append(week_date)

    if active_dates:
        repo_active_range[repo_name] = (min(active_dates), max(active_dates))

    repo_totals[repo_name] = {
        "commits": total_commits,
        "additions": total_add,
        "deletions": total_del,
        "net_lines": total_add - total_del,
    }

# ============================================================
# 4. Compute monthly aggregations from weekly data
# ============================================================
print("Computing monthly aggregations...")

monthly_lines = defaultdict(lambda: {"additions": 0, "deletions": 0, "commits": 0})
for week_date, data in sorted(weekly_lines.items()):
    month_key = week_date[:7]
    monthly_lines[month_key]["additions"] += data["additions"]
    monthly_lines[month_key]["deletions"] += data["deletions"]
    monthly_lines[month_key]["commits"] += data["commits"]

# ============================================================
# 5. Compute velocity metrics
# ============================================================
print("Computing velocity metrics...")

# Auto-detect pre-AI era start: first month with commits
if commit_dates:
    min_date = min(commit_dates)
    max_date = max(commit_dates)
elif daily_contributions:
    sorted_days = sorted(daily_contributions.keys())
    min_date = sorted_days[0]
    max_date = sorted_days[-1]
else:
    min_date = user_profile.get("created_at", "2020-01-01")[:10]
    max_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

pre_ai_start = min_date[:7]  # YYYY-MM of first activity
today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

# Build complete monthly timeline
all_months = []
current = datetime.strptime(min_date[:7], "%Y-%m")
end = datetime.strptime(max_date[:7], "%Y-%m")
while current <= end:
    month_key = current.strftime("%Y-%m")
    all_months.append(month_key)
    if current.month == 12:
        current = current.replace(year=current.year + 1, month=1)
    else:
        current = current.replace(month=current.month + 1)

# Build timeline with all metrics
timeline = []
cumulative_additions = 0
cumulative_deletions = 0
cumulative_commits = 0
cumulative_net = 0

for month in all_months:
    commits_search = monthly_commits.get(month, 0)
    lines_data = monthly_lines.get(month, {"additions": 0, "deletions": 0, "commits": 0})
    repos_active = len(monthly_repos.get(month, set()))

    cumulative_additions += lines_data["additions"]
    cumulative_deletions += lines_data["deletions"]
    cumulative_net += lines_data["additions"] - lines_data["deletions"]
    cumulative_commits += commits_search

    # Lines per commit for this month
    lpc = round(lines_data["additions"] / commits_search, 1) if commits_search > 0 else 0

    timeline.append({
        "month": month,
        "commits": commits_search,
        "additions": lines_data["additions"],
        "deletions": lines_data["deletions"],
        "net_lines": lines_data["additions"] - lines_data["deletions"],
        "lines_per_commit": lpc,
        "cumulative_additions": cumulative_additions,
        "cumulative_deletions": cumulative_deletions,
        "cumulative_net": cumulative_net,
        "cumulative_commits": cumulative_commits,
        "active_repos": repos_active,
    })

# ============================================================
# 6. Rolling averages (3-month window)
# ============================================================
print("Computing rolling averages...")

for i, entry in enumerate(timeline):
    window = timeline[max(0, i - 2):i + 1]
    entry["commits_3mo_avg"] = round(sum(w["commits"] for w in window) / len(window), 1)
    entry["additions_3mo_avg"] = round(sum(w["additions"] for w in window) / len(window), 1)
    entry["net_lines_3mo_avg"] = round(sum(w["net_lines"] for w in window) / len(window), 1)
    lpc_values = [w["lines_per_commit"] for w in window if w["lines_per_commit"] > 0]
    entry["lpc_3mo_avg"] = round(sum(lpc_values) / len(lpc_values), 1) if lpc_values else 0

# ============================================================
# 7. Delivery Velocity Index (DVI)
# ============================================================
print("Computing Delivery Velocity Index...")

# DVI = weighted composite of commits, net lines, and repo breadth
# Normalized to the peak month = 100
dvi_raw = []
for entry in timeline:
    raw = (
        entry["commits"] * 1.0 +
        max(0, entry["net_lines"]) * 0.001 +
        entry["active_repos"] * 5.0
    )
    dvi_raw.append(raw)

peak_dvi = max(dvi_raw) if dvi_raw else 1
for i, entry in enumerate(timeline):
    entry["dvi"] = round(dvi_raw[i] / peak_dvi * 100, 1)

    # 3-month rolling DVI
    window_start = max(0, i - 2)
    window = dvi_raw[window_start:i + 1]
    entry["dvi_3mo_avg"] = round(sum(window) / len(window) / peak_dvi * 100, 1)

# ============================================================
# 8. Era analysis (aligned with AI milestones)
# ============================================================
print("Analyzing eras...")

eras = [
    {"name": "Pre-AI", "start": pre_ai_start, "end": "2021-05",
     "description": "Manual coding, no AI assistance. Learning fundamentals."},
    {"name": "Copilot Era", "start": "2021-06", "end": "2022-10",
     "description": "GitHub Copilot preview to GA. First taste of AI-assisted development."},
    {"name": "ChatGPT Awakening", "start": "2022-11", "end": "2023-06",
     "description": "ChatGPT + GPT-4. Conversational AI becomes a coding partner."},
    {"name": "Foundation Model Arms Race", "start": "2023-07", "end": "2024-05",
     "description": "Claude 2/3, GPT-4 Turbo. Models get good enough for serious engineering."},
    {"name": "Sonnet Dominance", "start": "2024-06", "end": "2025-04",
     "description": "Claude 3.5 Sonnet era. AI becomes the primary coding tool."},
    {"name": "Agentic Coding", "start": "2025-05", "end": today_str[:7],
     "description": "Claude Code, autonomous agents. AI handles entire features end-to-end."},
]

era_stats = []
for era in eras:
    era_months = [e for e in timeline
                  if era["start"] <= e["month"] <= era["end"]]
    if era_months:
        total_commits = sum(e["commits"] for e in era_months)
        total_additions = sum(e["additions"] for e in era_months)
        total_deletions = sum(e["deletions"] for e in era_months)
        avg_monthly_commits = round(total_commits / len(era_months), 1)
        avg_monthly_net = round((total_additions - total_deletions) / len(era_months), 1)
        avg_dvi = round(sum(e["dvi"] for e in era_months) / len(era_months), 1)
        active_months = len([e for e in era_months if e["commits"] > 0])

        era_stats.append({
            **era,
            "months": len(era_months),
            "active_months": active_months,
            "total_commits": total_commits,
            "total_additions": total_additions,
            "total_deletions": total_deletions,
            "total_net_lines": total_additions - total_deletions,
            "avg_monthly_commits": avg_monthly_commits,
            "avg_monthly_net_lines": avg_monthly_net,
            "avg_dvi": avg_dvi,
        })

# ============================================================
# 8.5. Estimated Development Hours
# ============================================================
print("Computing estimated development hours...")

# Model I: 2h session base + 60min per contribution, capped at 14h
# No AI dampening — hours measure time investment, not output efficiency
# Non-contributing weekdays (2021+) get 3h for invisible work (debugging, design, review)
IDLE_DAY_HOURS = 3.0
DAILY_CAP = 14.0

def estimate_base_hours(contributions):
    """Session-based: fixed overhead + per-contribution work time."""
    return min(2.0 + contributions * 1.0, DAILY_CAP)

# Compute per-day hours
daily_hours = {}  # date_str -> hours
monthly_hours = defaultdict(lambda: {
    "human_hours": 0.0, "active_days": 0, "idle_days": 0
})

# Active days (any day with contributions)
for date_str, count in sorted(daily_contributions.items()):
    hours = estimate_base_hours(count)
    daily_hours[date_str] = hours
    month_key = date_str[:7]
    monthly_hours[month_key]["human_hours"] += hours
    monthly_hours[month_key]["active_days"] += 1

# Non-contributing weekdays (2021+) get idle hours
idle_day_count = 0
for year_data in contribution_calendar:
    for day in year_data.get("days", []):
        if day["contributionCount"] == 0 and day["date"] >= "2021-01-01":
            dt = datetime.strptime(day["date"], "%Y-%m-%d")
            if dt.weekday() < 5:  # Mon-Fri
                month_key = day["date"][:7]
                monthly_hours[month_key]["human_hours"] += IDLE_DAY_HOURS
                monthly_hours[month_key]["idle_days"] += 1
                idle_day_count += 1

# Build monthly timeline with cumulative values
dev_hours_timeline = []
cum_hours = 0.0
for month in all_months:
    mh = monthly_hours.get(month, {"human_hours": 0, "active_days": 0, "idle_days": 0})
    cum_hours += mh["human_hours"]
    total_days = mh["active_days"] + mh["idle_days"]
    dev_hours_timeline.append({
        "month": month,
        "human_hours": round(mh["human_hours"], 1),
        "active_days": mh["active_days"],
        "idle_days": mh["idle_days"],
        "avg_hours_per_day": round(mh["human_hours"] / total_days, 1) if total_days > 0 else 0,
        "cumulative_hours": round(cum_hours, 1),
    })

# 3-month rolling averages
for i, entry in enumerate(dev_hours_timeline):
    window = dev_hours_timeline[max(0, i - 2):i + 1]
    entry["human_hours_3mo_avg"] = round(
        sum(w["human_hours"] for w in window) / len(window), 1
    )

# Era rollup
era_hours = defaultdict(lambda: {"human_hours": 0.0, "active_days": 0, "idle_days": 0})
for entry in dev_hours_timeline:
    for era in eras:
        if era["start"] <= entry["month"] <= era["end"]:
            era_hours[era["name"]]["human_hours"] += entry["human_hours"]
            era_hours[era["name"]]["active_days"] += entry["active_days"]
            era_hours[era["name"]]["idle_days"] += entry["idle_days"]
            break

dev_hours_eras = []
for era in eras:
    eh = era_hours.get(era["name"], {"human_hours": 0, "active_days": 0, "idle_days": 0})
    total_days = eh["active_days"] + eh["idle_days"]
    dev_hours_eras.append({
        "name": era["name"],
        "start": era["start"],
        "end": era["end"],
        "total_hours": round(eh["human_hours"], 1),
        "active_days": eh["active_days"],
        "idle_days": eh["idle_days"],
        "avg_hours_per_day": round(eh["human_hours"] / total_days, 1) if total_days > 0 else 0,
    })

# Summary highlights
total_hours = sum(entry["human_hours"] for entry in dev_hours_timeline)
peak_month_entry = max(dev_hours_timeline, key=lambda x: x["human_hours"]) if dev_hours_timeline else None

dev_hours_highlights = {
    "total_hours": round(total_hours, 1),
    "active_days": len(daily_hours),
    "idle_days": idle_day_count,
    "total_work_days": len(daily_hours) + idle_day_count,
    "peak_month": peak_month_entry["month"] if peak_month_entry else None,
    "peak_month_hours": peak_month_entry["human_hours"] if peak_month_entry else 0,
    "avg_daily_hours": round(total_hours / (len(daily_hours) + idle_day_count), 1) if (len(daily_hours) + idle_day_count) > 0 else 0,
    "work_weeks": round(total_hours / 40, 1),
    "formula": "min(2.0 + contributions × 1.0, 14) per active day; 3.0 per non-contributing weekday",
}

# ============================================================
# 8.6. Delivery Speed (output per hour of dev time)
# ============================================================
print("Computing delivery speed...")

delivery_speed_timeline = []
for i, month in enumerate(all_months):
    mh = monthly_hours.get(month, {"human_hours": 0, "active_days": 0, "idle_days": 0})
    hours = mh["human_hours"]
    lines_data = monthly_lines.get(month, {"additions": 0, "deletions": 0})
    contribs = monthly_contributions.get(month, 0)

    additions = lines_data["additions"]
    deletions = lines_data["deletions"]
    net = additions - deletions

    lines_per_hour = round(additions / hours, 1) if hours > 0 else 0
    net_per_hour = round(net / hours, 1) if hours > 0 else 0
    contribs_per_hour = round(contribs / hours, 2) if hours > 0 else 0

    delivery_speed_timeline.append({
        "month": month,
        "hours": round(hours, 1),
        "additions": additions,
        "net_lines": net,
        "contributions": contribs,
        "lines_per_hour": lines_per_hour,
        "net_per_hour": net_per_hour,
        "contribs_per_hour": contribs_per_hour,
    })

# 3-month rolling averages
for i, entry in enumerate(delivery_speed_timeline):
    window = delivery_speed_timeline[max(0, i - 2):i + 1]
    active_window = [w for w in window if w["hours"] > 0]
    if active_window:
        entry["lines_per_hour_3mo"] = round(
            sum(w["additions"] for w in active_window) / sum(w["hours"] for w in active_window), 1
        )
        entry["contribs_per_hour_3mo"] = round(
            sum(w["contributions"] for w in active_window) / sum(w["hours"] for w in active_window), 2
        )
    else:
        entry["lines_per_hour_3mo"] = 0
        entry["contribs_per_hour_3mo"] = 0

# Era delivery speed
delivery_speed_eras = []
for era in eras:
    era_entries = [e for e in delivery_speed_timeline if era["start"] <= e["month"] <= era["end"]]
    total_hrs = sum(e["hours"] for e in era_entries)
    total_adds = sum(e["additions"] for e in era_entries)
    total_net = sum(e["net_lines"] for e in era_entries)
    total_contribs = sum(e["contributions"] for e in era_entries)

    delivery_speed_eras.append({
        "name": era["name"],
        "total_hours": round(total_hrs, 1),
        "total_additions": total_adds,
        "total_contributions": total_contribs,
        "lines_per_hour": round(total_adds / total_hrs, 1) if total_hrs > 0 else 0,
        "net_per_hour": round(total_net / total_hrs, 1) if total_hrs > 0 else 0,
        "contribs_per_hour": round(total_contribs / total_hrs, 2) if total_hrs > 0 else 0,
    })

# ============================================================
# 8.7. Community Engagement Score
# ============================================================
print("Computing community engagement...")

# Aggregate collaboration data from contribution calendar
yearly_engagement = []
total_prs = 0
total_reviews = 0
total_issues = 0
total_new_repos = 0
engagement_months = 0  # months with any non-commit activity

for year_data in contribution_calendar:
    prs = year_data.get("pull_requests", 0)
    reviews = year_data.get("reviews", 0)
    issues = year_data.get("issues", 0)
    new_repos = year_data.get("new_repos", 0)
    total_prs += prs
    total_reviews += reviews
    total_issues += issues
    total_new_repos += new_repos

    yearly_engagement.append({
        "year": year_data["year"],
        "pull_requests": prs,
        "reviews": reviews,
        "issues": issues,
        "new_repos": new_repos,
        "commits": year_data.get("commits", 0),
        "restricted": year_data.get("restricted", 0),
        "total_contributions": year_data.get("total_contributions", 0),
    })

# Use REST Search API collaboration data (includes private repos) if available,
# fall back to GraphQL data (public only) otherwise
rest_prs = collaboration_stats.get("prs_authored", 0)
rest_reviews = collaboration_stats.get("prs_reviewed", 0)
rest_issues = collaboration_stats.get("issues_filed", 0)
rest_comments = collaboration_stats.get("pr_comments", 0)

# Prefer REST data (includes private repos) over GraphQL (public only)
real_prs = max(rest_prs, total_prs)
real_reviews = max(rest_reviews, total_reviews)
real_issues = max(rest_issues, total_issues)
real_comments = rest_comments

# Compute engagement sub-scores (each 0-100)
total_active_months = len([m for m in all_months if monthly_contributions.get(m, 0) > 0])
_account_created = user_profile.get("created_at", "")[:10]
_years = (datetime.now(timezone.utc) - datetime.strptime(_account_created, "%Y-%m-%d").replace(tzinfo=timezone.utc)).days / 365.25 if _account_created else 1

# 1. Review Activity (30%) — PR reviews filed
# Benchmark: active reviewer does 50+ reviews/year
review_score = min(100, (real_reviews / max(_years, 1)) / 50 * 100)

# 2. Discussion (25%) — Issues filed + PRs opened + PR comments
# Benchmark: active participant has 100+ discussion interactions per year
discussion_activity = real_issues + real_prs + real_comments
discussion_score = min(100, (discussion_activity / max(_years, 1)) / 100 * 100)

# 3. Collaboration Breadth (25%) — repos contributed to beyond your own
# Use unique repos from calendar data
all_collab_repos = set()
for year_data in contribution_calendar:
    for repo in year_data.get("repos", []):
        all_collab_repos.add(repo["repo"])
unique_repo_count = len(all_collab_repos)
# Benchmark: 20+ repos = high breadth
breadth_score = min(100, unique_repo_count / 20 * 100)

# 4. Consistency (20%) — what % of active months had contributions
consistency_score = min(100, (total_active_months / max(len(all_months), 1)) * 100)

# Weighted composite
engagement_composite = (
    review_score * 0.30 +
    discussion_score * 0.25 +
    breadth_score * 0.25 +
    consistency_score * 0.20
)

# Letter grade
if engagement_composite >= 80:
    grade = "A"
    grade_label = "Team Multiplier"
elif engagement_composite >= 65:
    grade = "B"
    grade_label = "Active Collaborator"
elif engagement_composite >= 50:
    grade = "C"
    grade_label = "Engaged Builder"
elif engagement_composite >= 35:
    grade = "D"
    grade_label = "Solo Builder"
else:
    grade = "F"
    grade_label = "Lone Wolf"

# Era engagement
engagement_eras = []
for era in eras:
    era_years = [y for y in yearly_engagement
                 if str(y["year"])[:4] >= era["start"][:4] and str(y["year"])[:4] <= era["end"][:4]]
    era_prs = sum(y["pull_requests"] for y in era_years)
    era_reviews = sum(y["reviews"] for y in era_years)
    era_issues = sum(y["issues"] for y in era_years)
    era_restricted = sum(y["restricted"] for y in era_years)
    engagement_eras.append({
        "name": era["name"],
        "pull_requests": era_prs,
        "reviews": era_reviews,
        "issues": era_issues,
        "restricted": era_restricted,
    })

community_engagement = {
    "grade": grade,
    "grade_label": grade_label,
    "score": round(engagement_composite, 1),
    "sub_scores": {
        "review_activity": round(review_score, 1),
        "discussion": round(discussion_score, 1),
        "breadth": round(breadth_score, 1),
        "consistency": round(consistency_score, 1),
    },
    "totals": {
        "pull_requests": real_prs,
        "reviews": real_reviews,
        "issues": real_issues,
        "pr_comments": real_comments,
        "new_repos": total_new_repos,
        "unique_repos": unique_repo_count,
    },
    "yearly": yearly_engagement,
    "eras": engagement_eras,
}

# ============================================================
# 9. Language breakdown
# ============================================================
print("Computing language breakdown...")

lang_bytes = defaultdict(int)
for entry in repo_languages:
    for lang, bytes_count in entry["languages"].items():
        lang_bytes[lang] += bytes_count

total_bytes = sum(lang_bytes.values()) or 1
languages = [
    {"name": lang, "bytes": b, "percentage": round(b / total_bytes * 100, 2)}
    for lang, b in sorted(lang_bytes.items(), key=lambda x: -x[1])
]

# ============================================================
# 10. Top repos by impact
# ============================================================
print("Computing top repos...")

# Build repo-to-years mapping from contribution calendar for accurate date ranges
repo_calendar_years = defaultdict(set)
for year_data in contribution_calendar:
    for repo_info in year_data.get("repos", []):
        repo_calendar_years[repo_info["repo"]].add(year_data["year"])

top_repos = sorted(
    [
        {
            "name": name,
            "short_name": name.split("/")[-1],
            "org": name.split("/")[0],
            "description": repo_descriptions.get(name, ""),
            "first_active": repo_active_range[name][0] if name in repo_active_range else None,
            "last_active": repo_active_range[name][1] if name in repo_active_range else None,
            **stats,
        }
        for name, stats in repo_totals.items()
    ],
    key=lambda x: -x["commits"]
)

# Also add repos from calendar data that aren't in repo_stats
for repo, count in sorted(repo_commit_counts.items(), key=lambda x: -x[1]):
    if repo not in repo_totals:
        years = sorted(repo_calendar_years.get(repo, set()))
        first_active = f"{years[0]}-01-01" if years else None
        last_active = f"{years[-1]}-12-31" if years else None
        top_repos.append({
            "name": repo,
            "short_name": repo.split("/")[-1],
            "org": repo.split("/")[0],
            "description": repo_descriptions.get(repo, ""),
            "commits": count,
            "additions": None,
            "deletions": None,
            "net_lines": None,
            "first_active": first_active,
            "last_active": last_active,
        })

# ============================================================
# 11. Contribution heatmap (daily data)
# ============================================================
print("Building contribution heatmap...")

heatmap_data = []
for date_str, count in sorted(daily_contributions.items()):
    heatmap_data.append({"date": date_str, "count": count})

# ============================================================
# 12. Key highlight stats
# ============================================================
print("Computing highlight stats...")

total_contributions = sum(d["total_contributions"] for d in contribution_calendar)
total_graphql_commits = sum(d.get("commits", 0) + d.get("restricted", 0) for d in contribution_calendar)
total_additions_all = sum(r.get("additions", 0) for r in repo_totals.values())
total_deletions_all = sum(r.get("deletions", 0) for r in repo_totals.values())
total_net = total_additions_all - total_deletions_all
total_repos_touched = len(repos_metadata)
total_active_days = len(daily_contributions)

# Peak month
peak_month = max(timeline, key=lambda x: x["commits"]) if timeline else None
# Peak day
peak_day = max(heatmap_data, key=lambda x: x["count"]) if heatmap_data else None

# Streak calculation
sorted_dates = sorted(daily_contributions.keys())
max_streak = 0
current_streak = 1
for i in range(1, len(sorted_dates)):
    d1 = datetime.strptime(sorted_dates[i - 1], "%Y-%m-%d")
    d2 = datetime.strptime(sorted_dates[i], "%Y-%m-%d")
    if (d2 - d1).days == 1:
        current_streak += 1
        max_streak = max(max_streak, current_streak)
    else:
        current_streak = 1
max_streak = max(max_streak, current_streak) if sorted_dates else 0

# Current streak (from today backwards)
today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
current_streak_val = 0
check_date = today
while check_date.strftime("%Y-%m-%d") in daily_contributions:
    current_streak_val += 1
    check_date -= timedelta(days=1)

# Yearly breakdown from contribution calendar
yearly_commits = {}
for year_data in contribution_calendar:
    yearly_commits[str(year_data["year"])] = year_data["total_contributions"]

# Repos per org
org_repos = defaultdict(list)
for repo in top_repos:
    org_repos[repo["org"]].append(repo)

# Account creation date
account_created = user_profile.get("created_at", "")[:10]
now = datetime.now(timezone.utc)
if account_created:
    created_dt = datetime.strptime(account_created, "%Y-%m-%d")
    years_active = round((now - created_dt.replace(tzinfo=timezone.utc)).days / 365.25, 1)
else:
    years_active = 0

# Data caveats
data_caveats.append(
    "GitHub Stats API line counts can be inflated for repos with large vendored files, "
    "generated code, or force-pushed history rewrites."
)

data_caveats.append(
    "Contribution counts come from the GitHub GraphQL contribution calendar and include "
    "all contribution types (commits, issues, PRs, reviews)."
)

restricted_total = sum(d.get("restricted", 0) for d in contribution_calendar)
if restricted_total > 0:
    pct = round(restricted_total / max(total_contributions, 1) * 100, 1)
    data_caveats.append(
        f"Approximately {pct}% of contributions ({restricted_total:,}) are from private repos. "
        f"Line-level stats are only available for repos where the Stats API returned data."
    )

highlights = {
    "total_commits": total_graphql_commits,
    "total_contributions": total_contributions,
    "total_additions": total_additions_all,
    "total_deletions": total_deletions_all,
    "total_net_lines": total_net,
    "total_repos": total_repos_touched,
    "total_repos_with_stats": len(repo_totals),
    "total_active_days": total_active_days,
    "max_streak_days": max_streak,
    "current_streak_days": current_streak_val,
    "peak_month": peak_month["month"] if peak_month else None,
    "peak_month_commits": peak_month["commits"] if peak_month else 0,
    "peak_day": peak_day["date"] if peak_day else None,
    "peak_day_contributions": peak_day["count"] if peak_day else 0,
    "account_created": account_created,
    "years_active": years_active,
    "yearly_commits": dict(yearly_commits),
    "total_estimated_hours": dev_hours_highlights["total_hours"],
    "engagement_grade": community_engagement["grade"],
    "data_caveats": data_caveats,
}

# ============================================================
# 13. Velocity change at each AI milestone
# ============================================================
print("Computing velocity at AI milestones...")

milestone_velocity = []
for milestone in AI_MILESTONES:
    m_date = milestone["date"]
    m_month = m_date[:7]

    # Get 3-month average DVI before and after the milestone
    m_idx = None
    for i, entry in enumerate(timeline):
        if entry["month"] == m_month:
            m_idx = i
            break

    if m_idx is not None:
        before = timeline[max(0, m_idx - 3):m_idx]
        after = timeline[m_idx:min(len(timeline), m_idx + 3)]

        before_commits = sum(e["commits"] for e in before) / max(len(before), 1)
        after_commits = sum(e["commits"] for e in after) / max(len(after), 1)
        before_dvi = sum(e["dvi"] for e in before) / max(len(before), 1)
        after_dvi = sum(e["dvi"] for e in after) / max(len(after), 1)

        change_pct = round((after_dvi - before_dvi) / max(before_dvi, 0.1) * 100, 1)
    else:
        before_commits = 0
        after_commits = 0
        before_dvi = 0
        after_dvi = 0
        change_pct = 0

    milestone_velocity.append({
        **milestone,
        "before_avg_commits": round(before_commits, 1),
        "after_avg_commits": round(after_commits, 1),
        "before_dvi": round(before_dvi, 1),
        "after_dvi": round(after_dvi, 1),
        "dvi_change_pct": change_pct,
    })

# ============================================================
# Output
# ============================================================
print("Writing insights.json...")

insights = {
    "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "user": {
        "login": user_profile.get("login", "unknown"),
        "name": user_profile.get("name", ""),
        "avatar_url": user_profile.get("avatar_url", ""),
        "created_at": user_profile.get("created_at", ""),
        "bio": user_profile.get("bio", ""),
    },
    "highlights": highlights,
    "timeline": timeline,
    "heatmap": heatmap_data,
    "eras": era_stats,
    "milestones": milestone_velocity,
    "languages": languages[:20],
    "top_repos": top_repos[:30],
    "org_breakdown": {
        org: {
            "repos": len(repos),
            "total_commits": sum(r["commits"] for r in repos),
            "total_additions": sum(r.get("additions") or 0 for r in repos),
            "total_deletions": sum(r.get("deletions") or 0 for r in repos),
        }
        for org, repos in org_repos.items()
    },
    "yearly_summary": {
        str(year): data for year, data in yearly_summary.items()
    },
    "dvi_definition": {
        "name": "Delivery Velocity Index (DVI)",
        "formula": "commits x 1.0 + max(0, net_lines) x 0.001 + active_repos x 5.0",
        "normalization": "Peak month = 100",
        "description": "A composite metric that weights commit frequency, net code output, and project breadth. Normalized so the most productive month scores 100.",
    },
    "dev_hours_timeline": dev_hours_timeline,
    "dev_hours_eras": dev_hours_eras,
    "dev_hours_highlights": dev_hours_highlights,
    "delivery_speed_timeline": delivery_speed_timeline,
    "delivery_speed_eras": delivery_speed_eras,
    "community_engagement": community_engagement,
}

with open(OUTPUT, "w") as f:
    json.dump(insights, f, indent=2)

print(f"\nDone! Output: {OUTPUT}")
print(f"  Timeline: {len(timeline)} months")
print(f"  Heatmap: {len(heatmap_data)} active days")
print(f"  Repos: {len(top_repos)} repos")
print(f"  Milestones: {len(milestone_velocity)} AI milestones")
print(f"  Eras: {len(era_stats)} eras")
print(f"  Languages: {len(languages)} languages")
print(f"  Caveats: {len(data_caveats)} data quality notes")

# Quick validation
print(f"\n=== Key Numbers ===")
print(f"  Total commits (GraphQL): {highlights['total_commits']:,}")
print(f"  Total contributions (calendar): {highlights['total_contributions']:,}")
print(f"  Lines added: {highlights['total_additions']:,}")
print(f"  Lines deleted: {highlights['total_deletions']:,}")
print(f"  Net lines: {highlights['total_net_lines']:,}")
print(f"  Active days: {highlights['total_active_days']}")
print(f"  Max streak: {highlights['max_streak_days']} days")
print(f"  Years active: {highlights['years_active']}")
print(f"  Dev hours: {dev_hours_highlights['total_hours']:,.0f} estimated")
print(f"  Work weeks: {dev_hours_highlights['work_weeks']:,.1f}")
print(f"  Engagement: {community_engagement['grade']} ({community_engagement['score']:.0f}/100) — {community_engagement['grade_label']}")
