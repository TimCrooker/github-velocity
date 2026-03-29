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

for repo_data in repo_stats:
    repo_name = repo_data["repo"]
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

# Filter repos with garbage stats (additions <= commits is clearly wrong)
filtered_repo_totals = {}
data_caveats = []
garbage_count = 0
for name, stats in repo_totals.items():
    if stats["additions"] <= stats["commits"] and stats["additions"] > 0:
        garbage_count += 1
        continue
    filtered_repo_totals[name] = stats

if garbage_count > 0:
    data_caveats.append(
        f"{garbage_count} repos excluded from line counts due to clearly invalid "
        f"GitHub Stats API data (additions <= commits)."
    )

repo_totals = filtered_repo_totals

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
total_graphql_commits = sum(d.get("commits", 0) for d in contribution_calendar)
total_additions_all = sum(r.get("additions", 0) for r in repo_totals.values())
total_deletions_all = sum(r.get("deletions", 0) for r in repo_totals.values())
total_net = total_additions_all - total_deletions_all
total_repos_touched = len(repo_commit_counts)
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
