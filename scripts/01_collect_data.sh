#!/bin/bash
# ============================================================
# GitHub Data Dump — Full history for any GitHub user
# Collects: profile, repos, contribution calendar, commit stats,
#           search commits, and language data.
# Outputs: JSON files in the specified output directory.
# ============================================================

set -euo pipefail

# ============================================================
# Defaults
# ============================================================
DUMP_DIR="./gh_dump"
USERNAME=""

# ============================================================
# Parse arguments
# ============================================================
show_help() {
    cat << 'HELP'
Usage: 01_collect_data.sh [OPTIONS]

Collect GitHub data for generating a delivery velocity report.

Options:
  --username NAME   GitHub username to collect data for
                    (default: auto-detect from 'gh api user')
  --output DIR      Output directory for JSON files
                    (default: ./gh_dump)
  --help            Show this help message

Prerequisites:
  - gh CLI installed and authenticated (https://cli.github.com)
  - jq installed
  - python3 available (for merging paginated JSON)

Examples:
  ./01_collect_data.sh
  ./01_collect_data.sh --username octocat --output /tmp/gh_data
HELP
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --username)
            if [[ $# -lt 2 || "$2" == --* ]]; then
                echo "ERROR: --username requires a value." >&2
                exit 1
            fi
            USERNAME="$2"
            shift 2
            ;;
        --output)
            if [[ $# -lt 2 || "$2" == --* ]]; then
                echo "ERROR: --output requires a value." >&2
                exit 1
            fi
            DUMP_DIR="$2"
            shift 2
            ;;
        --help|-h)
            show_help
            ;;
        *)
            echo "Unknown option: $1" >&2
            echo "Use --help for usage information." >&2
            exit 1
            ;;
    esac
done

# ============================================================
# Validate prerequisites
# ============================================================
if ! command -v gh &>/dev/null; then
    echo "ERROR: 'gh' CLI is not installed." >&2
    echo "Install it: brew install gh  (macOS) or see https://cli.github.com" >&2
    exit 1
fi

if ! gh auth status &>/dev/null; then
    echo "ERROR: 'gh' CLI is not authenticated." >&2
    echo "Run: gh auth login" >&2
    exit 1
fi

if ! command -v jq &>/dev/null; then
    echo "ERROR: 'jq' is not installed." >&2
    echo "Install it: brew install jq  (macOS)" >&2
    exit 1
fi

if ! command -v python3 &>/dev/null; then
    echo "ERROR: 'python3' is not installed." >&2
    exit 1
fi

mkdir -p "$DUMP_DIR"

# ============================================================
# Rate limit helper — pauses if core API remaining is low
# ============================================================
check_core_rate_limit() {
    local remaining
    remaining=$(gh api rate_limit --jq '.resources.core.remaining' 2>/dev/null || echo "5000")
    if [ "$remaining" -lt 50 ]; then
        local reset
        reset=$(gh api rate_limit --jq '.resources.core.reset' 2>/dev/null || echo "0")
        local now
        now=$(date +%s)
        local wait_secs=$(( reset - now + 2 ))
        if [ "$wait_secs" -gt 0 ] && [ "$wait_secs" -lt 3700 ]; then
            echo "  Core API rate limit low ($remaining remaining), waiting ${wait_secs}s for reset..."
            sleep "$wait_secs"
        fi
    fi
}

# ============================================================
# Step 1: User profile
# ============================================================
echo "=== Step 1: User profile ==="
AUTHENTICATED_USER=$(gh api user --jq '.login' 2>/dev/null)
if [ -z "$USERNAME" ]; then
    USERNAME="$AUTHENTICATED_USER"
    gh api user > "$DUMP_DIR/user_profile.json"
    echo "Auto-detected username: $USERNAME"
else
    # Fetch the specified user's profile (may differ from authenticated user)
    if ! gh api "users/$USERNAME" > "$DUMP_DIR/user_profile.json" 2>/dev/null; then
        echo "ERROR: Could not fetch profile for user '$USERNAME'." >&2
        exit 1
    fi
    if [ "$USERNAME" != "$AUTHENTICATED_USER" ]; then
        echo "NOTE: Collecting data for '$USERNAME' (authenticated as '$AUTHENTICATED_USER')."
        echo "      Only public repos will be collected. Private data is not accessible."
    fi
    echo "Using specified username: $USERNAME"
fi
IS_SELF=$( [ "$USERNAME" = "$AUTHENTICATED_USER" ] && echo true || echo false )
echo "Done"

# ============================================================
# Step 2: All repos with metadata
# ============================================================
echo ""
echo "=== Step 2: All repos with metadata ==="
# user/repos returns authenticated user's repos (incl. private); users/X/repos returns public only
if [ "$IS_SELF" = "true" ]; then
    REPOS_ENDPOINT="user/repos"
else
    REPOS_ENDPOINT="users/$USERNAME/repos"
fi
gh api "$REPOS_ENDPOINT" --paginate \
    --jq '[.[] | {
        full_name: .full_name,
        name: .name,
        owner: .owner.login,
        private: .private,
        fork: .fork,
        language: .language,
        created_at: .created_at,
        updated_at: .updated_at,
        pushed_at: .pushed_at,
        size: .size,
        description: .description,
        topics: .topics,
        default_branch: .default_branch
    }]' > "$DUMP_DIR/repos_metadata_raw.json"

# Fix: paginated output creates multiple JSON arrays — merge into one
python3 - "$DUMP_DIR" << 'PYEOF'
import json, sys
dump_dir = sys.argv[1]
with open(f'{dump_dir}/repos_metadata_raw.json') as f:
    content = f.read().strip()
if not content:
    with open(f'{dump_dir}/repos_metadata.json', 'w') as f:
        json.dump([], f, indent=2)
    sys.exit(0)
# Handle multiple JSON arrays concatenated together
arrays = []
decoder = json.JSONDecoder()
pos = 0
while pos < len(content):
    while pos < len(content) and content[pos] in ' \t\n\r':
        pos += 1
    if pos >= len(content):
        break
    obj, end = decoder.raw_decode(content, pos)
    if isinstance(obj, list):
        arrays.extend(obj)
    else:
        arrays.append(obj)
    pos = end
with open(f'{dump_dir}/repos_metadata.json', 'w') as f:
    json.dump(arrays, f, indent=2)
PYEOF
rm -f "$DUMP_DIR/repos_metadata_raw.json"

repo_count=$(jq length "$DUMP_DIR/repos_metadata.json")
echo "Found $repo_count repos"

# ============================================================
# Step 3: Contribution calendar (GraphQL)
# ============================================================
echo ""
echo "=== Step 3: Contribution calendar (GraphQL) ==="

# Determine year range from account creation
account_created=$(jq -r '.created_at' "$DUMP_DIR/user_profile.json" | cut -c1-4)
current_year=$(date +%Y)
account_created_date=$(jq -r '.created_at' "$DUMP_DIR/user_profile.json" | cut -c1-10)
today=$(date +%Y-%m-%d)

> "$DUMP_DIR/contribution_calendar.jsonl"
for year in $(seq "$account_created" "$current_year"); do
    from="${year}-01-01T00:00:00Z"
    to="${year}-12-31T23:59:59Z"

    # Clamp to account creation and today
    if [ "$year" -eq "$account_created" ]; then
        from="${account_created_date}T00:00:00Z"
    fi
    if [ "$year" -eq "$current_year" ]; then
        to="${today}T23:59:59Z"
    fi

    # Use viewer for self, user(login:) for other users
    if [ "$IS_SELF" = "true" ]; then
        GQL_ROOT="viewer"
        GQL_QUERY="{ viewer { contributionsCollection(from: \"$from\", to: \"$to\") {"
    else
        GQL_ROOT="user"
        GQL_QUERY="{ user(login: \"$USERNAME\") { contributionsCollection(from: \"$from\", to: \"$to\") {"
    fi

    gh api graphql -f query="
    ${GQL_QUERY}
          totalCommitContributions
          restrictedContributionsCount
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays {
                contributionCount
                date
              }
            }
          }
          commitContributionsByRepository(maxRepositories: 100) {
            repository {
              nameWithOwner
              primaryLanguage { name }
            }
            contributions {
              totalCount
            }
          }
        }
      }
    }" --jq "{
        year: $year,
        commits: .data.${GQL_ROOT}.contributionsCollection.totalCommitContributions,
        restricted: .data.${GQL_ROOT}.contributionsCollection.restrictedContributionsCount,
        total_contributions: .data.${GQL_ROOT}.contributionsCollection.contributionCalendar.totalContributions,
        days: [.data.${GQL_ROOT}.contributionsCollection.contributionCalendar.weeks[].contributionDays[]],
        repos: [.data.${GQL_ROOT}.contributionsCollection.commitContributionsByRepository[] | {
            repo: .repository.nameWithOwner,
            language: .repository.primaryLanguage.name,
            commits: .contributions.totalCount
        }]
    }" >> "$DUMP_DIR/contribution_calendar.jsonl" 2>/dev/null
    echo "  Year $year done"
    sleep 0.3
done
echo "Done"

# ============================================================
# Step 4: Contributor stats per repo (additions/deletions)
# ============================================================
echo ""
echo "=== Step 4: Contributor stats per repo (additions/deletions) ==="
> "$DUMP_DIR/repo_stats.jsonl"
repo_names=$(jq -r '.[].full_name' "$DUMP_DIR/repos_metadata.json")
total=$repo_count
count=0
found=0

if [ "$repo_count" -gt 0 ]; then
while IFS= read -r repo; do
    [ -z "$repo" ] && continue
    count=$((count + 1))

    # Check core rate limit every 10 repos
    if [ $((count % 10)) -eq 0 ]; then
        check_core_rate_limit
    fi

    # Try up to 5 times (GitHub returns 202 while computing stats)
    for attempt in 1 2 3 4 5; do
        # Use --include to capture HTTP status code for 202 detection
        raw_response=$(gh api "repos/$repo/stats/contributors" --include 2>/dev/null)
        gh_exit=$?

        if [ $gh_exit -ne 0 ]; then
            break  # API error (404, auth, etc.) — skip this repo
        fi

        # Split headers from body (gh --include outputs headers then blank line then body)
        http_status=$(echo "$raw_response" | head -1 | grep -oE '[0-9]{3}')
        response=$(echo "$raw_response" | sed '1,/^$/d')

        # 202 = GitHub is computing stats, retry after delay
        if [ "$http_status" = "202" ]; then
            if [ "$attempt" -lt 5 ]; then
                sleep $((attempt * 2))
                continue
            fi
            echo "  [$count/$total] $repo — still computing (skipped after $attempt retries)"
            break
        fi

        if [ -n "$response" ] && [ "$response" != "null" ] && [ "$response" != "[]" ]; then
            # Extract user's data
            user_data=$(echo "$response" | jq -r --arg user "$USERNAME" '
                [.[] | select(.author.login == $user)] | if length > 0 then .[0] else null end
            ')

            if [ "$user_data" != "null" ] && [ -n "$user_data" ]; then
                echo "$user_data" | jq -c --arg repo "$repo" '{repo: $repo, total_commits: .total, weeks: .weeks}' >> "$DUMP_DIR/repo_stats.jsonl"
                total_c=$(echo "$user_data" | jq '.total')
                found=$((found + 1))
                echo "  [$count/$total] $repo — $total_c commits"
            fi
        fi
        break
    done

    # Small delay to respect rate limits
    sleep 0.15
done <<< "$repo_names"
fi
echo "Found stats for $found repos"

# ============================================================
# Step 5: Search API commits
# ============================================================
echo ""
echo "=== Step 5: Search API commits ==="
remaining=$(gh api rate_limit --jq '.resources.search.remaining')
echo "Search API remaining: $remaining"

if [ "$remaining" -gt 5 ]; then
    > "$DUMP_DIR/search_commits.jsonl"
    total_found=0

    start_year=$account_created
    end_year=$current_year

    for year in $(seq "$start_year" "$end_year"); do
        for month in $(seq 1 12); do
            # Skip months before account creation
            created_month=$(echo "$account_created_date" | cut -c6-7 | sed 's/^0//')
            if [ "$year" -eq "$account_created" ] && [ "$month" -lt "$created_month" ]; then continue; fi

            # Skip future months
            current_month=$(date +%-m)
            if [ "$year" -eq "$current_year" ] && [ "$month" -gt "$current_month" ]; then continue; fi

            start=$(printf "%04d-%02d-01" "$year" "$month")
            if [ "$month" -eq 12 ]; then
                end=$(printf "%04d-01-01" $((year + 1)))
            else
                end=$(printf "%04d-%02d-01" "$year" $((month + 1)))
            fi

            page=1
            month_count=0
            while true; do
                remaining=$(gh api rate_limit --jq '.resources.search.remaining' 2>/dev/null)
                if [ "$remaining" -lt 2 ]; then
                    echo "  Rate limit low ($remaining), waiting 60s..."
                    sleep 62
                fi

                result=$(gh api "search/commits?q=author:${USERNAME}+author-date:${start}..${end}&per_page=100&page=${page}&sort=author-date" \
                    --jq '{total: .total_count, items: [.items[] | {
                        sha: .sha,
                        date: .commit.author.date,
                        message: (.commit.message | split("\n")[0]),
                        repo: .repository.full_name,
                        stats: {additions: .stats.additions, deletions: .stats.deletions, total: .stats.total}
                    }]}' 2>/dev/null)

                if [ $? -ne 0 ] || [ -z "$result" ]; then
                    sleep 5
                    break
                fi

                item_count=$(echo "$result" | jq '.items | length')
                total_in_range=$(echo "$result" | jq '.total')

                if [ "$item_count" = "0" ] || [ "$item_count" = "null" ]; then break; fi

                echo "$result" | jq -c '.items[]' >> "$DUMP_DIR/search_commits.jsonl"
                month_count=$((month_count + item_count))

                if [ "$month_count" -ge "$total_in_range" ] || [ "$page" -ge 10 ]; then break; fi
                page=$((page + 1))
                sleep 2
            done

            if [ "$month_count" -gt 0 ]; then
                total_found=$((total_found + month_count))
                echo "  [$start] $month_count commits (total: $total_found)"
            fi
        done
    done
    echo "Total search commits: $total_found"
else
    echo "Search API rate limited, skipping (will use contribution calendar instead)"
    > "$DUMP_DIR/search_commits.jsonl"
fi

# ============================================================
# Step 6: Language breakdown per repo
# ============================================================
echo ""
echo "=== Step 6: Language breakdown per repo ==="
> "$DUMP_DIR/repo_languages.jsonl"
lang_repo_count=0
if [ "$repo_count" -gt 0 ]; then
while IFS= read -r repo; do
    [ -z "$repo" ] && continue
    lang_repo_count=$((lang_repo_count + 1))

    # Check core rate limit every 10 repos
    if [ $((lang_repo_count % 10)) -eq 0 ]; then
        check_core_rate_limit
    fi

    langs=$(gh api "repos/$repo/languages" 2>/dev/null)
    if [ -n "$langs" ] && [ "$langs" != "{}" ]; then
        echo "$langs" | jq -c --arg repo "$repo" '{repo: $repo, languages: .}' >> "$DUMP_DIR/repo_languages.jsonl"
    fi
    sleep 0.1
done <<< "$(jq -r '.[].full_name' "$DUMP_DIR/repos_metadata.json")"
fi
lang_count=$(wc -l < "$DUMP_DIR/repo_languages.jsonl" | tr -d ' ')
echo "Language data for $lang_count repos"

# ============================================================
# DUMP COMPLETE
# ============================================================
echo ""
echo "=== DUMP COMPLETE ==="
echo "Files in $DUMP_DIR:"
ls -lh "$DUMP_DIR"/*.json* 2>/dev/null
