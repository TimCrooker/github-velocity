#!/usr/bin/env python3
"""
GitHub Data Collector — Fast, parallel collection of GitHub profile data.

Replaces the bash collection script with reliable Python implementation.
Uses `gh` CLI for authentication, parallel requests for speed.

Usage:
    python3 01_collect_data.py [--output DIR] [--username NAME] [--fast]
"""

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# ============================================================
# CLI Arguments
# ============================================================
parser = argparse.ArgumentParser(description="Collect GitHub data for velocity report")
parser.add_argument("--output", default="./gh_dump", help="Output directory (default: ./gh_dump)")
parser.add_argument("--username", default=None, help="GitHub username (default: auto-detect)")
parser.add_argument("--fast", action="store_true", help="Skip repo stats (faster, no line-level data)")
args = parser.parse_args()

DUMP_DIR = Path(args.output)
DUMP_DIR.mkdir(parents=True, exist_ok=True)

MAX_WORKERS = 8  # Parallel API requests (safe for GitHub rate limits)
REPO_STATS_RETRIES = 1
REPO_STATS_RETRY_WAIT = 3


# ============================================================
# GitHub API helpers
# ============================================================

def gh_api(endpoint, graphql_query=None, paginate=False):
    """Call GitHub API via gh CLI. Returns parsed JSON or None on error."""
    cmd = ["gh", "api"]
    if graphql_query:
        cmd += ["graphql", "-f", f"query={graphql_query}"]
    else:
        cmd.append(endpoint)
        if paginate:
            cmd.append("--paginate")
    cmd.append("-q")
    cmd.append(".")  # raw JSON output

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return None
        if not result.stdout.strip():
            return None
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        return None


def gh_api_raw(endpoint):
    """Call GitHub API and return raw response + HTTP status."""
    try:
        result = subprocess.run(
            ["gh", "api", endpoint, "--include"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return None, 0

        lines = result.stdout.split("\n")
        # First line contains HTTP status
        status = 0
        if lines and lines[0].startswith("HTTP/"):
            parts = lines[0].split()
            if len(parts) >= 2:
                try:
                    status = int(parts[1])
                except ValueError:
                    pass

        # Body is after the blank line
        body = ""
        blank_found = False
        for line in lines:
            if blank_found:
                body += line + "\n"
            elif line.strip() == "":
                blank_found = True

        if body.strip():
            try:
                return json.loads(body), status
            except json.JSONDecodeError:
                return None, status
        return None, status
    except subprocess.TimeoutExpired:
        return None, 0


def check_rate_limit():
    """Check GitHub API rate limit, return remaining requests."""
    data = gh_api("rate_limit")
    if data and "resources" in data:
        core = data["resources"].get("core", {})
        return core.get("remaining", 5000), core.get("reset", 0)
    return 5000, 0


def wait_for_rate_limit(min_remaining=50):
    """Pause if rate limit is low."""
    remaining, reset_time = check_rate_limit()
    if remaining < min_remaining:
        wait = max(0, reset_time - int(time.time())) + 2
        if 0 < wait < 3700:
            print(f"  Rate limit low ({remaining} remaining), waiting {wait}s...")
            time.sleep(wait)


# ============================================================
# Validators
# ============================================================

def check_prerequisites():
    """Verify gh CLI is installed and authenticated."""
    try:
        result = subprocess.run(["gh", "--version"], capture_output=True, timeout=5)
        if result.returncode != 0:
            print("ERROR: 'gh' CLI is not installed.", file=sys.stderr)
            print("  macOS:  brew install gh", file=sys.stderr)
            print("  Linux:  see https://cli.github.com", file=sys.stderr)
            sys.exit(1)
    except FileNotFoundError:
        print("ERROR: 'gh' CLI is not installed.", file=sys.stderr)
        sys.exit(1)

    result = subprocess.run(["gh", "auth", "status"], capture_output=True, timeout=10)
    if result.returncode != 0:
        print("ERROR: 'gh' CLI is not authenticated.", file=sys.stderr)
        print("  Run: gh auth login", file=sys.stderr)
        sys.exit(1)


# ============================================================
# Step 1: User profile
# ============================================================

def collect_user_profile(username=None):
    print("=== Step 1: User profile ===")
    if username:
        profile = gh_api(f"users/{username}")
    else:
        profile = gh_api("user")

    if not profile:
        print("ERROR: Could not fetch user profile.", file=sys.stderr)
        sys.exit(1)

    login = profile.get("login", "unknown")
    print(f"  Username: {login}")

    with open(DUMP_DIR / "user_profile.json", "w") as f:
        json.dump(profile, f, indent=2)

    return login, profile


# ============================================================
# Step 2: Repository metadata
# ============================================================

def collect_repos(username, is_self):
    print("\n=== Step 2: Repository metadata ===")
    endpoint = "user/repos" if is_self else f"users/{username}/repos"

    # Paginate manually to avoid gh --paginate JSON concat issues
    all_repos = []
    page = 1
    while True:
        data = gh_api(f"{endpoint}?per_page=100&page={page}")
        if not data or not isinstance(data, list) or len(data) == 0:
            break
        all_repos.extend(data)
        if len(data) < 100:
            break
        page += 1

    # Extract relevant fields
    repos = [
        {
            "full_name": r["full_name"],
            "name": r["name"],
            "owner": r["owner"]["login"],
            "private": r["private"],
            "fork": r["fork"],
            "language": r.get("language"),
            "created_at": r.get("created_at"),
            "updated_at": r.get("updated_at"),
            "pushed_at": r.get("pushed_at"),
            "size": r.get("size"),
            "description": r.get("description"),
            "topics": r.get("topics", []),
            "default_branch": r.get("default_branch"),
        }
        for r in all_repos
    ]

    print(f"  Found {len(repos)} repos")
    with open(DUMP_DIR / "repos_metadata.json", "w") as f:
        json.dump(repos, f, indent=2)

    return repos


# ============================================================
# Step 3: Contribution calendar (GraphQL)
# ============================================================

def collect_contribution_calendar(username, is_self, profile):
    print("\n=== Step 3: Contribution calendar (GraphQL) ===")

    account_created = profile.get("created_at", "2020-01-01")[:10]
    start_year = int(account_created[:4])
    current_year = int(time.strftime("%Y"))
    today = time.strftime("%Y-%m-%d")

    results = []
    for year in range(start_year, current_year + 1):
        from_date = f"{year}-01-01T00:00:00Z"
        to_date = f"{year}-12-31T23:59:59Z"

        if year == start_year:
            from_date = f"{account_created}T00:00:00Z"
        if year == current_year:
            to_date = f"{today}T23:59:59Z"

        if is_self:
            root = "viewer"
            query_start = f'{{ viewer {{ contributionsCollection(from: "{from_date}", to: "{to_date}") {{'
        else:
            root = "user"
            query_start = f'{{ user(login: "{username}") {{ contributionsCollection(from: "{from_date}", to: "{to_date}") {{'

        query = f"""{query_start}
            totalCommitContributions
            restrictedContributionsCount
            totalPullRequestContributions
            totalPullRequestReviewContributions
            totalIssueContributions
            totalRepositoryContributions
            contributionCalendar {{
                totalContributions
                weeks {{
                    contributionDays {{
                        contributionCount
                        date
                    }}
                }}
            }}
            commitContributionsByRepository(maxRepositories: 100) {{
                repository {{
                    nameWithOwner
                    primaryLanguage {{ name }}
                }}
                contributions {{
                    totalCount
                }}
            }}
        }} }} }}"""

        data = gh_api(None, graphql_query=query)
        if data and "data" in data:
            coll = data["data"].get(root, {}).get("contributionsCollection", {})
            cal = coll.get("contributionCalendar", {})
            repos = coll.get("commitContributionsByRepository", [])

            entry = {
                "year": year,
                "commits": coll.get("totalCommitContributions", 0),
                "restricted": coll.get("restrictedContributionsCount", 0),
                "pull_requests": coll.get("totalPullRequestContributions", 0),
                "reviews": coll.get("totalPullRequestReviewContributions", 0),
                "issues": coll.get("totalIssueContributions", 0),
                "new_repos": coll.get("totalRepositoryContributions", 0),
                "total_contributions": cal.get("totalContributions", 0),
                "days": [
                    day
                    for week in cal.get("weeks", [])
                    for day in week.get("contributionDays", [])
                ],
                "repos": [
                    {
                        "repo": r["repository"]["nameWithOwner"],
                        "language": (r["repository"].get("primaryLanguage") or {}).get("name"),
                        "commits": r["contributions"]["totalCount"],
                    }
                    for r in repos
                ],
            }
            results.append(entry)
            print(f"  Year {year}: {entry['total_contributions']} contributions")

        time.sleep(0.3)

    with open(DUMP_DIR / "contribution_calendar.jsonl", "w") as f:
        for entry in results:
            f.write(json.dumps(entry) + "\n")

    print("  Done")
    return results


# ============================================================
# Step 4: Repo stats (additions/deletions) — parallelized
# ============================================================

def _fetch_repo_stats(repo_name, username):
    """Fetch contributor stats for a single repo. Returns dict or None."""
    for attempt in range(1 + REPO_STATS_RETRIES):
        data, status = gh_api_raw(f"repos/{repo_name}/stats/contributors")

        if status == 202:
            if attempt < REPO_STATS_RETRIES:
                time.sleep(REPO_STATS_RETRY_WAIT)
                continue
            return None  # Still computing, skip

        if data and isinstance(data, list):
            for contributor in data:
                if (contributor.get("author") or {}).get("login") == username:
                    return {
                        "repo": repo_name,
                        "total_commits": contributor["total"],
                        "weeks": contributor["weeks"],
                    }
        return None
    return None


def collect_repo_stats(repos, username):
    print("\n=== Step 4: Repo stats (parallel) ===")
    wait_for_rate_limit(min_remaining=len(repos) + 50)

    repo_names = [r["full_name"] for r in repos]
    results = []
    completed = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(_fetch_repo_stats, name, username): name
            for name in repo_names
        }
        for future in as_completed(futures):
            completed += 1
            name = futures[future]
            try:
                result = future.result()
                if result:
                    results.append(result)
            except Exception:
                pass

            if completed % 25 == 0 or completed == len(repo_names):
                print(f"  [{completed}/{len(repo_names)}] {len(results)} repos with stats")

    with open(DUMP_DIR / "repo_stats.jsonl", "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")

    print(f"  Done: {len(results)} repos with contributor stats")
    return results


# ============================================================
# Step 5: Language breakdown — parallelized
# ============================================================

def _fetch_repo_languages(repo_name):
    """Fetch languages for a single repo."""
    data = gh_api(f"repos/{repo_name}/languages")
    if data and isinstance(data, dict) and len(data) > 0:
        return {"repo": repo_name, "languages": data}
    return None


def collect_languages(repos):
    print("\n=== Step 5: Language breakdown (parallel) ===")
    wait_for_rate_limit(min_remaining=len(repos) + 50)

    repo_names = [r["full_name"] for r in repos]
    results = []
    completed = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(_fetch_repo_languages, name): name
            for name in repo_names
        }
        for future in as_completed(futures):
            completed += 1
            try:
                result = future.result()
                if result:
                    results.append(result)
            except Exception:
                pass

            if completed % 50 == 0 or completed == len(repo_names):
                print(f"  [{completed}/{len(repo_names)}] {len(results)} repos with languages")

    with open(DUMP_DIR / "repo_languages.jsonl", "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")

    print(f"  Done: {len(results)} repos with language data")
    return results


# ============================================================
# Step 6: Collaboration stats (REST Search API — includes private repos)
# ============================================================

def collect_collaboration(username):
    print("\n=== Step 6: Collaboration stats ===")

    queries = {
        "prs_authored": f"author:{username}+type:pr",
        "prs_reviewed": f"reviewed-by:{username}+type:pr",
        "issues_filed": f"author:{username}+type:issue",
        "pr_comments": f"commenter:{username}+type:pr",
    }

    results = {}
    for key, query in queries.items():
        data = gh_api(f"search/issues?q={query}&per_page=1")
        if data and "total_count" in data:
            results[key] = data["total_count"]
            print(f"  {key}: {data['total_count']}")
        else:
            results[key] = 0
        time.sleep(2)  # Search API: 30 req/min

    with open(DUMP_DIR / "collaboration.json", "w") as f:
        json.dump(results, f, indent=2)

    print("  Done")
    return results


# ============================================================
# Main
# ============================================================

def main():
    check_prerequisites()

    # Step 1: User profile
    username, profile = collect_user_profile(args.username)

    # Detect if collecting for self
    auth_user = gh_api("user")
    is_self = auth_user and auth_user.get("login") == username

    # Step 2: Repos
    repos = collect_repos(username, is_self)

    # Step 3: Contribution calendar
    collect_contribution_calendar(username, is_self, profile)

    # Step 4: Repo stats (skip in fast mode, preserve existing data)
    if args.fast:
        stats_path = DUMP_DIR / "repo_stats.jsonl"
        if stats_path.exists() and stats_path.stat().st_size > 0:
            print(f"\n=== Step 4: Repo stats — SKIPPED (--fast mode, keeping existing data) ===")
        else:
            print(f"\n=== Step 4: Repo stats — SKIPPED (--fast mode) ===")
            stats_path.touch()
    else:
        collect_repo_stats(repos, username)

    # Step 5: Languages (always — it's fast with parallelization)
    collect_languages(repos)

    # Step 6: Collaboration stats
    collect_collaboration(username)

    # Create empty search_commits.jsonl (not used, but analyzer expects it)
    with open(DUMP_DIR / "search_commits.jsonl", "w") as f:
        pass

    # Summary
    print(f"\n=== COLLECTION COMPLETE ===")
    for path in sorted(DUMP_DIR.iterdir()):
        size = path.stat().st_size
        unit = "KB" if size > 1024 else "B"
        val = size / 1024 if size > 1024 else size
        print(f"  {path.name}: {val:.1f} {unit}")


if __name__ == "__main__":
    main()
