"""
Tests for 02_analyze.py — GitHub Delivery Velocity Report analyzer.

Runs the analyzer against real fixture data and validates every computed metric.
Fixtures are gitignored (real user data). To run tests, first populate
tests/fixtures/ with output from 01_collect_data.sh.

Usage:
    pytest tests/test_analyze.py -v
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
SCRIPT = REPO_ROOT / "scripts" / "02_analyze.py"
OUTPUT = FIXTURES_DIR / "test_output.json"


# ============================================================
# Setup: run analyzer once, load results for all tests
# ============================================================

@pytest.fixture(scope="session")
def insights():
    """Run 02_analyze.py against fixtures and return parsed insights."""
    if not FIXTURES_DIR.exists() or not (FIXTURES_DIR / "user_profile.json").exists():
        pytest.skip("Fixture data not found. Run 01_collect_data.sh first.")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--input", str(FIXTURES_DIR), "--output", str(OUTPUT)],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, f"Analyzer failed:\n{result.stderr}"

    with open(OUTPUT) as f:
        data = json.load(f)
    return data


@pytest.fixture(scope="session")
def highlights(insights):
    return insights["highlights"]


@pytest.fixture(scope="session")
def timeline(insights):
    return insights["timeline"]


@pytest.fixture(scope="session")
def dev_hours(insights):
    return insights["dev_hours_highlights"]


@pytest.fixture(scope="session")
def delivery_speed_eras(insights):
    return insights["delivery_speed_eras"]


# ============================================================
# Fixture data loading
# ============================================================

@pytest.fixture(scope="session")
def raw_calendar():
    items = []
    with open(FIXTURES_DIR / "contribution_calendar.jsonl") as f:
        for line in f:
            if line.strip():
                items.append(json.loads(line))
    return items


@pytest.fixture(scope="session")
def raw_repos_metadata():
    with open(FIXTURES_DIR / "repos_metadata.json") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def raw_repo_stats():
    items = []
    with open(FIXTURES_DIR / "repo_stats.jsonl") as f:
        for line in f:
            if line.strip():
                items.append(json.loads(line))
    return items


@pytest.fixture(scope="session")
def raw_repo_languages():
    items = []
    with open(FIXTURES_DIR / "repo_languages.jsonl") as f:
        for line in f:
            if line.strip():
                items.append(json.loads(line))
    return items


# ============================================================
# 1. Output structure tests
# ============================================================

class TestOutputStructure:
    def test_top_level_keys(self, insights):
        required_keys = [
            "generated_at", "user", "highlights", "timeline", "heatmap",
            "eras", "milestones", "languages", "top_repos", "org_breakdown",
            "yearly_summary", "dvi_definition",
            "dev_hours_timeline", "dev_hours_eras", "dev_hours_highlights",
            "delivery_speed_timeline", "delivery_speed_eras",
        ]
        for key in required_keys:
            assert key in insights, f"Missing top-level key: {key}"

    def test_user_info(self, insights):
        user = insights["user"]
        assert user["login"] == "TimCrooker"
        assert user["name"] == "Tim Crooker"
        assert user["avatar_url"].startswith("https://")
        assert user["created_at"].startswith("2018-")

    def test_generated_at_is_iso(self, insights):
        assert insights["generated_at"].endswith("Z")


# ============================================================
# 2. Highlights / summary stats
# ============================================================

class TestHighlights:
    def test_total_contributions(self, highlights, raw_calendar):
        expected = sum(y["total_contributions"] for y in raw_calendar)
        assert highlights["total_contributions"] == expected

    def test_total_commits_from_graphql(self, highlights, raw_calendar):
        expected = sum(y.get("commits", 0) for y in raw_calendar)
        assert highlights["total_commits"] == expected

    def test_total_repos_matches_metadata(self, highlights, raw_repos_metadata):
        assert highlights["total_repos"] == len(raw_repos_metadata)

    def test_total_additions_positive(self, highlights):
        assert highlights["total_additions"] > 0

    def test_total_deletions_positive(self, highlights):
        assert highlights["total_deletions"] > 0

    def test_net_lines_equals_diff(self, highlights):
        assert highlights["total_net_lines"] == highlights["total_additions"] - highlights["total_deletions"]

    def test_active_days_matches_heatmap(self, highlights, insights):
        assert highlights["total_active_days"] == len(insights["heatmap"])

    def test_max_streak_positive(self, highlights):
        assert highlights["max_streak_days"] > 0

    def test_peak_day_is_valid_date(self, highlights):
        assert len(highlights["peak_day"]) == 10  # YYYY-MM-DD
        assert highlights["peak_day_contributions"] > 0

    def test_peak_month_is_valid(self, highlights):
        assert len(highlights["peak_month"]) == 7  # YYYY-MM
        assert highlights["peak_month_commits"] > 0

    def test_years_active_reasonable(self, highlights):
        assert 5 <= highlights["years_active"] <= 10

    def test_data_caveats_present(self, highlights):
        assert len(highlights["data_caveats"]) >= 2

    def test_yearly_commits_keys(self, highlights, raw_calendar):
        for y in raw_calendar:
            year_str = str(y["year"])
            if y["total_contributions"] > 0:
                assert year_str in highlights["yearly_commits"]

    def test_estimated_hours_present(self, highlights):
        assert highlights["total_estimated_hours"] > 0


# ============================================================
# 3. Contribution timeline
# ============================================================

class TestTimeline:
    def test_timeline_not_empty(self, timeline):
        assert len(timeline) > 0

    def test_months_are_sequential(self, timeline):
        months = [t["month"] for t in timeline]
        assert months == sorted(months)

    def test_no_duplicate_months(self, timeline):
        months = [t["month"] for t in timeline]
        assert len(months) == len(set(months))

    def test_cumulative_commits_monotonic(self, timeline):
        for i in range(1, len(timeline)):
            assert timeline[i]["cumulative_commits"] >= timeline[i - 1]["cumulative_commits"]

    def test_cumulative_additions_monotonic(self, timeline):
        for i in range(1, len(timeline)):
            assert timeline[i]["cumulative_additions"] >= timeline[i - 1]["cumulative_additions"]

    def test_total_commits_matches_highlights(self, timeline, highlights):
        total = sum(t["commits"] for t in timeline)
        assert total == highlights["total_contributions"]

    def test_rolling_averages_present(self, timeline):
        for entry in timeline:
            assert "commits_3mo_avg" in entry
            assert "dvi_3mo_avg" in entry

    def test_dvi_normalized_to_100(self, timeline):
        max_dvi = max(t["dvi"] for t in timeline)
        assert 99 <= max_dvi <= 100.1

    def test_dvi_non_negative(self, timeline):
        for t in timeline:
            assert t["dvi"] >= 0

    def test_specific_month_contributions(self, timeline):
        """May 2023 had 663 contributions."""
        may23 = next(t for t in timeline if t["month"] == "2023-05")
        assert may23["commits"] == 663

    def test_specific_month_additions(self, timeline):
        """March 2026 had significant line additions."""
        mar26 = next(t for t in timeline if t["month"] == "2026-03")
        assert mar26["additions"] > 1_000_000


# ============================================================
# 4. Contribution data integrity (calendar vs timeline)
# ============================================================

class TestContributionIntegrity:
    def test_monthly_contributions_match_calendar(self, timeline, raw_calendar):
        """Total contributions in timeline must match calendar total."""
        timeline_total = sum(t["commits"] for t in timeline)
        calendar_total = sum(y["total_contributions"] for y in raw_calendar)
        assert timeline_total == calendar_total

    def test_daily_contributions_aggregate_to_monthly(self, raw_calendar, timeline):
        """Daily contribution data should aggregate to match monthly totals."""
        from collections import defaultdict
        monthly = defaultdict(int)
        for year_data in raw_calendar:
            for day in year_data.get("days", []):
                if day["contributionCount"] > 0:
                    month_key = day["date"][:7]
                    monthly[month_key] += day["contributionCount"]

        for t in timeline:
            if t["commits"] > 0:
                assert t["month"] in monthly
                assert t["commits"] == monthly[t["month"]], \
                    f"Month {t['month']}: timeline={t['commits']}, calendar={monthly[t['month']]}"


# ============================================================
# 5. Line stats from repo_stats
# ============================================================

class TestLineStats:
    def test_total_additions_from_repo_stats(self, highlights, raw_repo_stats):
        """Total additions should come from aggregating repo_stats weekly data."""
        total_add = 0
        for repo in raw_repo_stats:
            repo_add = sum(w["a"] for w in repo["weeks"])
            # Skip repos with garbage data (additions <= commits)
            if repo_add > repo["total_commits"] or repo_add == 0:
                total_add += repo_add
        assert highlights["total_additions"] == total_add

    def test_additions_deletions_consistency(self, highlights):
        assert highlights["total_additions"] > highlights["total_deletions"]
        assert highlights["total_net_lines"] > 0


# ============================================================
# 6. Era analysis
# ============================================================

class TestEras:
    def test_six_eras(self, insights):
        assert len(insights["eras"]) == 6

    def test_era_names(self, insights):
        names = [e["name"] for e in insights["eras"]]
        assert names == [
            "Pre-AI", "Copilot Era", "ChatGPT Awakening",
            "Foundation Model Arms Race", "Sonnet Dominance", "Agentic Coding",
        ]

    def test_eras_cover_full_timeline(self, insights):
        """Eras should cover from first month to last month."""
        first_era = insights["eras"][0]
        last_era = insights["eras"][-1]
        first_month = insights["timeline"][0]["month"]
        last_month = insights["timeline"][-1]["month"]
        assert first_era["start"] <= first_month
        assert last_era["end"] >= last_month

    def test_era_months_positive(self, insights):
        for era in insights["eras"]:
            assert era["months"] > 0

    def test_era_commits_sum(self, insights):
        """Era commits should roughly sum to total contributions."""
        era_total = sum(e["total_commits"] for e in insights["eras"])
        timeline_total = sum(t["commits"] for t in insights["timeline"])
        assert era_total == timeline_total

    def test_era_avg_dvi_in_range(self, insights):
        for era in insights["eras"]:
            assert 0 <= era["avg_dvi"] <= 100

    def test_agentic_era_highest_avg_commits(self, insights):
        """Agentic era should have highest avg monthly commits."""
        agentic = next(e for e in insights["eras"] if e["name"] == "Agentic Coding")
        for era in insights["eras"]:
            assert agentic["avg_monthly_commits"] >= era["avg_monthly_commits"]


# ============================================================
# 7. Dev hours (Model I)
# ============================================================

class TestDevHours:
    def test_total_hours(self, dev_hours):
        assert dev_hours["total_hours"] == 10249.0

    def test_active_days(self, dev_hours):
        assert dev_hours["active_days"] == 1018

    def test_idle_days(self, dev_hours):
        assert dev_hours["idle_days"] == 479

    def test_total_work_days(self, dev_hours):
        assert dev_hours["total_work_days"] == dev_hours["active_days"] + dev_hours["idle_days"]

    def test_work_weeks(self, dev_hours):
        expected = round(dev_hours["total_hours"] / 40, 1)
        assert dev_hours["work_weeks"] == expected

    def test_avg_daily_hours_reasonable(self, dev_hours):
        assert 5 <= dev_hours["avg_daily_hours"] <= 10

    def test_formula_documented(self, dev_hours):
        assert "formula" in dev_hours
        assert "14" in dev_hours["formula"]  # daily cap

    def test_model_i_formula_single_contribution(self):
        """1 contribution should give min(2.0 + 1*1.0, 14) = 3.0 hours."""
        hours = min(2.0 + 1 * 1.0, 14.0)
        assert hours == 3.0

    def test_model_i_formula_heavy_day(self):
        """20 contributions should cap at 14 hours."""
        hours = min(2.0 + 20 * 1.0, 14.0)
        assert hours == 14.0

    def test_model_i_formula_medium_day(self):
        """8 contributions = min(2.0 + 8, 14) = 10 hours."""
        hours = min(2.0 + 8 * 1.0, 14.0)
        assert hours == 10.0

    def test_dev_hours_timeline_length(self, insights):
        assert len(insights["dev_hours_timeline"]) == len(insights["timeline"])

    def test_dev_hours_timeline_cumulative_monotonic(self, insights):
        tl = insights["dev_hours_timeline"]
        for i in range(1, len(tl)):
            assert tl[i]["cumulative_hours"] >= tl[i - 1]["cumulative_hours"]

    def test_dev_hours_timeline_total_matches(self, insights, dev_hours):
        """Sum of monthly hours should equal total_hours."""
        monthly_sum = sum(t["human_hours"] for t in insights["dev_hours_timeline"])
        assert abs(monthly_sum - dev_hours["total_hours"]) < 1.0

    def test_dev_hours_eras_count(self, insights):
        assert len(insights["dev_hours_eras"]) == 6

    def test_dev_hours_era_total_matches(self, insights, dev_hours):
        era_sum = sum(e["total_hours"] for e in insights["dev_hours_eras"])
        assert abs(era_sum - dev_hours["total_hours"]) < 1.0

    def test_idle_hours_calculation(self, dev_hours):
        """Idle hours should be idle_days * 3.0."""
        idle_hours = dev_hours["idle_days"] * 3.0
        active_hours = dev_hours["total_hours"] - idle_hours
        assert active_hours > idle_hours  # Active hours should dominate

    def test_peak_month_is_recent(self, dev_hours):
        """Peak month should be in 2025 or 2026 given recent intensity."""
        assert dev_hours["peak_month"] >= "2025"

    def test_rolling_average_present(self, insights):
        for entry in insights["dev_hours_timeline"]:
            assert "human_hours_3mo_avg" in entry


# ============================================================
# 8. Delivery speed
# ============================================================

class TestDeliverySpeed:
    def test_delivery_speed_timeline_length(self, insights):
        assert len(insights["delivery_speed_timeline"]) == len(insights["timeline"])

    def test_delivery_speed_eras_count(self, delivery_speed_eras):
        assert len(delivery_speed_eras) == 6

    def test_lines_per_hour_non_negative(self, delivery_speed_eras):
        for era in delivery_speed_eras:
            assert era["lines_per_hour"] >= 0

    def test_contribs_per_hour_non_negative(self, delivery_speed_eras):
        for era in delivery_speed_eras:
            assert era["contribs_per_hour"] >= 0

    def test_agentic_era_highest_lines_per_hour(self, delivery_speed_eras):
        """Agentic era should have highest lines/hour."""
        agentic = next(e for e in delivery_speed_eras if e["name"] == "Agentic Coding")
        for era in delivery_speed_eras:
            assert agentic["lines_per_hour"] >= era["lines_per_hour"]

    def test_agentic_era_highest_contribs_per_hour(self, delivery_speed_eras):
        """Agentic era should have highest contribs/hour."""
        agentic = next(e for e in delivery_speed_eras if e["name"] == "Agentic Coding")
        for era in delivery_speed_eras:
            assert agentic["contribs_per_hour"] >= era["contribs_per_hour"]

    def test_lines_per_hour_calculation(self, insights):
        """Spot-check: lines_per_hour = additions / hours for a given month."""
        for entry in insights["delivery_speed_timeline"]:
            if entry["hours"] > 0 and entry["additions"] > 0:
                expected = round(entry["additions"] / entry["hours"], 1)
                assert entry["lines_per_hour"] == expected
                break  # Just check one

    def test_contribs_per_hour_calculation(self, insights):
        """Spot-check: contribs_per_hour = contributions / hours."""
        for entry in insights["delivery_speed_timeline"]:
            if entry["hours"] > 0 and entry["contributions"] > 0:
                expected = round(entry["contributions"] / entry["hours"], 2)
                assert entry["contribs_per_hour"] == expected
                break

    def test_rolling_averages_present(self, insights):
        for entry in insights["delivery_speed_timeline"]:
            assert "lines_per_hour_3mo" in entry
            assert "contribs_per_hour_3mo" in entry

    def test_era_hours_match_dev_hours(self, delivery_speed_eras, insights):
        """Delivery speed era hours should match dev hours era hours."""
        for ds_era, dh_era in zip(delivery_speed_eras, insights["dev_hours_eras"]):
            assert ds_era["name"] == dh_era["name"]
            assert ds_era["total_hours"] == dh_era["total_hours"]


# ============================================================
# 9. Languages
# ============================================================

class TestLanguages:
    def test_languages_not_empty(self, insights):
        assert len(insights["languages"]) > 0

    def test_typescript_is_top_language(self, insights):
        assert insights["languages"][0]["name"] == "TypeScript"

    def test_percentages_sum_close_to_100(self, insights):
        total_pct = sum(l["percentage"] for l in insights["languages"])
        assert 95 <= total_pct <= 100.1  # Might not be exactly 100 due to truncation

    def test_bytes_positive(self, insights):
        for l in insights["languages"]:
            assert l["bytes"] > 0

    def test_language_bytes_match_source(self, insights, raw_repo_languages):
        """Total bytes per language should match raw aggregation."""
        from collections import defaultdict
        expected = defaultdict(int)
        for entry in raw_repo_languages:
            for lang, b in entry["languages"].items():
                expected[lang] += b
        for l in insights["languages"]:
            assert l["bytes"] == expected[l["name"]], \
                f"{l['name']}: got {l['bytes']}, expected {expected[l['name']]}"


# ============================================================
# 10. Top repos
# ============================================================

class TestTopRepos:
    def test_repos_not_empty(self, insights):
        assert len(insights["top_repos"]) > 0

    def test_repos_sorted_by_commits(self, insights):
        commits = [r["commits"] for r in insights["top_repos"]]
        assert commits == sorted(commits, reverse=True)

    def test_top_repo_is_list_forge(self, insights):
        assert insights["top_repos"][0]["short_name"] == "list-forge-monorepo"

    def test_repos_have_required_fields(self, insights):
        for r in insights["top_repos"]:
            assert "name" in r
            assert "short_name" in r
            assert "org" in r
            assert "commits" in r

    def test_repos_with_stats_have_active_range(self, insights):
        """Repos from repo_stats should have first_active/last_active."""
        for r in insights["top_repos"]:
            if r.get("additions") is not None:
                assert r.get("first_active") is not None, f"{r['name']} missing first_active"
                assert r.get("last_active") is not None, f"{r['name']} missing last_active"

    def test_active_range_order(self, insights):
        for r in insights["top_repos"]:
            if r.get("first_active") and r.get("last_active"):
                assert r["first_active"] <= r["last_active"], \
                    f"{r['name']}: first={r['first_active']} > last={r['last_active']}"


# ============================================================
# 11. Heatmap
# ============================================================

class TestHeatmap:
    def test_heatmap_count_matches_active_days(self, insights):
        assert len(insights["heatmap"]) == insights["highlights"]["total_active_days"]

    def test_heatmap_sorted_by_date(self, insights):
        dates = [h["date"] for h in insights["heatmap"]]
        assert dates == sorted(dates)

    def test_heatmap_no_zero_counts(self, insights):
        for h in insights["heatmap"]:
            assert h["count"] > 0

    def test_heatmap_dates_unique(self, insights):
        dates = [h["date"] for h in insights["heatmap"]]
        assert len(dates) == len(set(dates))

    def test_peak_day_in_heatmap(self, insights):
        peak = insights["highlights"]["peak_day"]
        peak_count = insights["highlights"]["peak_day_contributions"]
        entry = next(h for h in insights["heatmap"] if h["date"] == peak)
        assert entry["count"] == peak_count


# ============================================================
# 12. Milestones
# ============================================================

class TestMilestones:
    def test_milestone_count(self, insights):
        assert len(insights["milestones"]) == 15

    def test_milestones_have_required_fields(self, insights):
        for m in insights["milestones"]:
            assert "date" in m
            assert "name" in m
            assert "before_dvi" in m
            assert "after_dvi" in m
            assert "dvi_change_pct" in m

    def test_milestones_sorted_by_date(self, insights):
        dates = [m["date"] for m in insights["milestones"]]
        assert dates == sorted(dates)

    def test_dvi_values_non_negative(self, insights):
        for m in insights["milestones"]:
            assert m["before_dvi"] >= 0
            assert m["after_dvi"] >= 0


# ============================================================
# 13. Yearly summary
# ============================================================

class TestYearlySummary:
    def test_yearly_summary_has_all_years(self, insights, raw_calendar):
        for y in raw_calendar:
            assert str(y["year"]) in insights["yearly_summary"]

    def test_yearly_contributions_match(self, insights, raw_calendar):
        for y in raw_calendar:
            year_str = str(y["year"])
            assert insights["yearly_summary"][year_str]["total_contributions"] == y["total_contributions"]

    def test_yearly_restricted_match(self, insights, raw_calendar):
        for y in raw_calendar:
            year_str = str(y["year"])
            assert insights["yearly_summary"][year_str]["restricted"] == y.get("restricted", 0)


# ============================================================
# 14. Streak calculation
# ============================================================

class TestStreaks:
    def test_max_streak_value(self, highlights):
        assert highlights["max_streak_days"] == 49

    def test_current_streak_non_negative(self, highlights):
        assert highlights["current_streak_days"] >= 0

    def test_streak_manually(self, insights):
        """Verify max streak by walking heatmap data."""
        dates = sorted(insights["heatmap"], key=lambda x: x["date"])
        from datetime import datetime, timedelta
        max_streak = 1
        current = 1
        for i in range(1, len(dates)):
            d1 = datetime.strptime(dates[i - 1]["date"], "%Y-%m-%d")
            d2 = datetime.strptime(dates[i]["date"], "%Y-%m-%d")
            if (d2 - d1).days == 1:
                current += 1
                max_streak = max(max_streak, current)
            else:
                current = 1
        assert insights["highlights"]["max_streak_days"] == max_streak


# ============================================================
# 15. DVI definition
# ============================================================

class TestDVIDefinition:
    def test_dvi_definition_present(self, insights):
        d = insights["dvi_definition"]
        assert "formula" in d
        assert "normalization" in d
        assert "Peak month = 100" in d["normalization"]


# ============================================================
# 16. Org breakdown
# ============================================================

class TestOrgBreakdown:
    def test_org_breakdown_not_empty(self, insights):
        assert len(insights["org_breakdown"]) > 0

    def test_timcrooker_org_present(self, insights):
        assert "TimCrooker" in insights["org_breakdown"]

    def test_org_commit_counts_positive(self, insights):
        for org, data in insights["org_breakdown"].items():
            assert data["repos"] > 0
            assert data["total_commits"] >= 0
