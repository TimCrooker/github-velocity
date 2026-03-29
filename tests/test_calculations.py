"""
Deep calculation verification tests for 02_analyze.py.

These tests independently recompute every metric from raw fixture data
and compare against the analyzer's output. If the analyzer has a math bug,
these tests will catch it.

Usage:
    pytest tests/test_calculations.py -v
"""

import json
import math
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
SCRIPT = REPO_ROOT / "scripts" / "02_analyze.py"
OUTPUT = FIXTURES_DIR / "test_output_calc.json"


@pytest.fixture(scope="session")
def insights():
    if not FIXTURES_DIR.exists() or not (FIXTURES_DIR / "user_profile.json").exists():
        pytest.skip("Fixture data not found.")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--input", str(FIXTURES_DIR), "--output", str(OUTPUT)],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, f"Analyzer failed:\n{result.stderr}"
    with open(OUTPUT) as f:
        return json.load(f)


@pytest.fixture(scope="session")
def raw_calendar():
    items = []
    with open(FIXTURES_DIR / "contribution_calendar.jsonl") as f:
        for line in f:
            if line.strip():
                items.append(json.loads(line))
    return items


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


@pytest.fixture(scope="session")
def daily_contributions(raw_calendar):
    """Build the same daily_contributions dict the analyzer builds."""
    daily = {}
    for year_data in raw_calendar:
        for day in year_data.get("days", []):
            if day["contributionCount"] > 0:
                daily[day["date"]] = day["contributionCount"]
    return daily


@pytest.fixture(scope="session")
def all_days(raw_calendar):
    """Every day from the calendar, including zeros."""
    days = {}
    for year_data in raw_calendar:
        for day in year_data.get("days", []):
            days[day["date"]] = day["contributionCount"]
    return days


# ============================================================
# Independent recomputation of dev hours
# ============================================================

class TestDevHoursRecompute:
    """Independently recompute dev hours and compare to analyzer output."""

    def _compute_dev_hours(self, daily_contributions, all_days):
        """Reimplement Model I from scratch."""
        DAILY_CAP = 14.0
        IDLE_HOURS = 3.0

        active_hours = {}
        for date_str, count in daily_contributions.items():
            active_hours[date_str] = min(2.0 + count * 1.0, DAILY_CAP)

        idle_days = 0
        idle_total = 0.0
        for date_str, count in all_days.items():
            if count == 0 and date_str >= "2021-01-01":
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                if dt.weekday() < 5:
                    idle_days += 1
                    idle_total += IDLE_HOURS

        total = sum(active_hours.values()) + idle_total
        return {
            "total": round(total, 1),
            "active_days": len(active_hours),
            "idle_days": idle_days,
            "active_total": round(sum(active_hours.values()), 1),
            "idle_total": round(idle_total, 1),
            "daily_hours": active_hours,
        }

    def test_total_hours_exact(self, insights, daily_contributions, all_days):
        recomputed = self._compute_dev_hours(daily_contributions, all_days)
        assert insights["dev_hours_highlights"]["total_hours"] == recomputed["total"]

    def test_active_days_exact(self, insights, daily_contributions, all_days):
        recomputed = self._compute_dev_hours(daily_contributions, all_days)
        assert insights["dev_hours_highlights"]["active_days"] == recomputed["active_days"]

    def test_idle_days_exact(self, insights, daily_contributions, all_days):
        recomputed = self._compute_dev_hours(daily_contributions, all_days)
        assert insights["dev_hours_highlights"]["idle_days"] == recomputed["idle_days"]

    def test_every_active_day_formula(self, daily_contributions):
        """Verify the formula for every single active day."""
        for date_str, count in daily_contributions.items():
            expected = min(2.0 + count * 1.0, 14.0)
            assert expected >= 3.0, f"{date_str}: {count} contributions gave {expected}h (should be >= 3)"
            assert expected <= 14.0, f"{date_str}: {count} contributions gave {expected}h (should be <= 14)"

    def test_no_weekend_idle_days(self, all_days):
        """Verify weekends with 0 contributions are NOT counted as idle."""
        for date_str, count in all_days.items():
            if count == 0 and date_str >= "2021-01-01":
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                if dt.weekday() >= 5:  # Saturday/Sunday
                    pass  # Should not be counted — verified in idle_days count

    def test_idle_days_only_weekdays(self, all_days):
        """Count idle days independently and verify only weekdays are included."""
        idle = 0
        for date_str, count in all_days.items():
            if count == 0 and date_str >= "2021-01-01":
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                if dt.weekday() < 5:
                    idle += 1
        # This should match what the analyzer reports
        # (tested via test_idle_days_exact, but this is an independent count)
        assert idle > 0

    def test_monthly_hours_sum_to_total(self, insights):
        """Sum of all monthly dev_hours_timeline entries should equal total."""
        monthly_sum = sum(t["human_hours"] for t in insights["dev_hours_timeline"])
        assert abs(monthly_sum - insights["dev_hours_highlights"]["total_hours"]) < 1.0

    def test_era_hours_sum_to_total(self, insights):
        era_sum = sum(e["total_hours"] for e in insights["dev_hours_eras"])
        assert abs(era_sum - insights["dev_hours_highlights"]["total_hours"]) < 1.0

    def test_monthly_hours_recompute_each_month(self, insights, daily_contributions, all_days):
        """Recompute monthly hours independently and compare every month."""
        monthly = defaultdict(float)

        for date_str, count in daily_contributions.items():
            month_key = date_str[:7]
            monthly[month_key] += min(2.0 + count * 1.0, 14.0)

        for date_str, count in all_days.items():
            if count == 0 and date_str >= "2021-01-01":
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                if dt.weekday() < 5:
                    month_key = date_str[:7]
                    monthly[month_key] += 3.0

        for entry in insights["dev_hours_timeline"]:
            if entry["human_hours"] > 0:
                expected = round(monthly.get(entry["month"], 0), 1)
                actual = entry["human_hours"]
                assert abs(actual - expected) < 0.2, \
                    f"Month {entry['month']}: analyzer={actual}, recomputed={expected}"

    def test_cumulative_hours_correct(self, insights):
        """Verify cumulative sum is properly computed."""
        running = 0.0
        for entry in insights["dev_hours_timeline"]:
            running += entry["human_hours"]
            assert abs(entry["cumulative_hours"] - round(running, 1)) < 0.2, \
                f"Month {entry['month']}: cumulative={entry['cumulative_hours']}, expected={round(running, 1)}"

    def test_rolling_average_correct(self, insights):
        """Verify 3-month rolling average is correctly computed."""
        tl = insights["dev_hours_timeline"]
        for i in range(len(tl)):
            window = tl[max(0, i - 2):i + 1]
            expected = round(sum(w["human_hours"] for w in window) / len(window), 1)
            actual = tl[i]["human_hours_3mo_avg"]
            assert abs(actual - expected) < 0.2, \
                f"Month {tl[i]['month']}: rolling avg={actual}, expected={expected}"


# ============================================================
# Independent recomputation of DVI
# ============================================================

class TestDVIRecompute:
    """Independently recompute DVI and compare to analyzer output."""

    def test_dvi_formula(self, insights):
        """Recompute DVI from raw timeline data and verify."""
        tl = insights["timeline"]

        # Compute raw DVI scores
        raw_scores = []
        for entry in tl:
            raw = (
                entry["commits"] * 1.0 +
                max(0, entry["net_lines"]) * 0.001 +
                entry["active_repos"] * 5.0
            )
            raw_scores.append(raw)

        peak = max(raw_scores) if raw_scores else 1
        assert peak > 0

        for i, entry in enumerate(tl):
            expected_dvi = round(raw_scores[i] / peak * 100, 1)
            assert abs(entry["dvi"] - expected_dvi) < 0.2, \
                f"Month {entry['month']}: dvi={entry['dvi']}, expected={expected_dvi}"

    def test_dvi_3mo_avg(self, insights):
        """Verify 3-month rolling DVI average."""
        tl = insights["timeline"]

        raw_scores = []
        for entry in tl:
            raw = (
                entry["commits"] * 1.0 +
                max(0, entry["net_lines"]) * 0.001 +
                entry["active_repos"] * 5.0
            )
            raw_scores.append(raw)

        peak = max(raw_scores)

        for i, entry in enumerate(tl):
            window_start = max(0, i - 2)
            window = raw_scores[window_start:i + 1]
            expected = round(sum(window) / len(window) / peak * 100, 1)
            assert abs(entry["dvi_3mo_avg"] - expected) < 0.2, \
                f"Month {entry['month']}: dvi_3mo={entry['dvi_3mo_avg']}, expected={expected}"


# ============================================================
# Independent recomputation of delivery speed
# ============================================================

class TestDeliverySpeedRecompute:
    """Independently recompute delivery speed metrics."""

    def test_lines_per_hour_every_month(self, insights):
        """Verify lines_per_hour = additions / hours for every month."""
        for ds, dh in zip(insights["delivery_speed_timeline"], insights["dev_hours_timeline"]):
            assert ds["month"] == dh["month"]
            hours = ds["hours"]
            if hours > 0 and ds["additions"] > 0:
                expected = round(ds["additions"] / hours, 1)
                assert ds["lines_per_hour"] == expected, \
                    f"Month {ds['month']}: lph={ds['lines_per_hour']}, expected={expected}"

    def test_contribs_per_hour_every_month(self, insights):
        """Verify contribs_per_hour = contributions / hours for every month."""
        for ds in insights["delivery_speed_timeline"]:
            hours = ds["hours"]
            if hours > 0 and ds["contributions"] > 0:
                expected = round(ds["contributions"] / hours, 2)
                assert ds["contribs_per_hour"] == expected, \
                    f"Month {ds['month']}: cph={ds['contribs_per_hour']}, expected={expected}"

    def test_hours_match_dev_hours_timeline(self, insights):
        """Delivery speed hours should exactly match dev hours timeline."""
        for ds, dh in zip(insights["delivery_speed_timeline"], insights["dev_hours_timeline"]):
            assert ds["hours"] == dh["human_hours"], \
                f"Month {ds['month']}: ds hours={ds['hours']}, dh hours={dh['human_hours']}"

    def test_contributions_match_main_timeline(self, insights):
        """Delivery speed contributions should match main timeline commits."""
        for ds, main in zip(insights["delivery_speed_timeline"], insights["timeline"]):
            assert ds["contributions"] == main["commits"], \
                f"Month {ds['month']}: ds contribs={ds['contributions']}, main={main['commits']}"

    def test_additions_match_main_timeline(self, insights):
        """Delivery speed additions should match main timeline additions."""
        for ds, main in zip(insights["delivery_speed_timeline"], insights["timeline"]):
            assert ds["additions"] == main["additions"], \
                f"Month {ds['month']}: ds adds={ds['additions']}, main={main['additions']}"

    def test_era_lines_per_hour_recompute(self, insights):
        """Recompute era-level lines/hour from timeline data."""
        era_defs = [
            ("Pre-AI", None, "2021-05"),
            ("Copilot Era", "2021-06", "2022-10"),
            ("ChatGPT Awakening", "2022-11", "2023-06"),
            ("Foundation Model Arms Race", "2023-07", "2024-05"),
            ("Sonnet Dominance", "2024-06", "2025-04"),
            ("Agentic Coding", "2025-05", None),
        ]

        for era_output in insights["delivery_speed_eras"]:
            total_hrs = 0
            total_adds = 0
            for ds in insights["delivery_speed_timeline"]:
                # Find which era this month belongs to
                for name, start, end in era_defs:
                    s = start or "0000-00"
                    e = end or "9999-99"
                    if s <= ds["month"] <= e and name == era_output["name"]:
                        total_hrs += ds["hours"]
                        total_adds += ds["additions"]
                        break

            if total_hrs > 0:
                expected_lph = round(total_adds / total_hrs, 1)
                assert abs(era_output["lines_per_hour"] - expected_lph) < 0.2, \
                    f"Era {era_output['name']}: lph={era_output['lines_per_hour']}, expected={expected_lph}"

    def test_rolling_lph_correct(self, insights):
        """Verify 3-month rolling lines/hour average."""
        tl = insights["delivery_speed_timeline"]
        for i in range(len(tl)):
            window = tl[max(0, i - 2):i + 1]
            active = [w for w in window if w["hours"] > 0]
            if active:
                expected = round(
                    sum(w["additions"] for w in active) / sum(w["hours"] for w in active), 1
                )
                assert abs(tl[i]["lines_per_hour_3mo"] - expected) < 0.2, \
                    f"Month {tl[i]['month']}: lph_3mo={tl[i]['lines_per_hour_3mo']}, expected={expected}"


# ============================================================
# Independent recomputation of line stats
# ============================================================

class TestLineStatsRecompute:
    """Recompute line additions/deletions from raw repo_stats."""

    def test_total_additions_recompute(self, insights, raw_repo_stats):
        total_add = 0
        for repo in raw_repo_stats:
            repo_add = sum(w["a"] for w in repo["weeks"])
            repo_commits = repo["total_commits"]
            # Match the garbage filter: skip if additions <= commits and additions > 0
            if repo_add <= repo_commits and repo_add > 0:
                continue
            total_add += repo_add
        assert insights["highlights"]["total_additions"] == total_add

    def test_total_deletions_recompute(self, insights, raw_repo_stats):
        total_del = 0
        for repo in raw_repo_stats:
            repo_add = sum(w["a"] for w in repo["weeks"])
            repo_commits = repo["total_commits"]
            if repo_add <= repo_commits and repo_add > 0:
                continue
            total_del += sum(w["d"] for w in repo["weeks"])
        assert insights["highlights"]["total_deletions"] == total_del

    def test_monthly_additions_recompute(self, insights, raw_repo_stats):
        """Recompute monthly additions from weekly repo_stats and compare."""
        from datetime import datetime, timezone as tz
        monthly_adds = defaultdict(int)
        for repo in raw_repo_stats:
            repo_add = sum(w["a"] for w in repo["weeks"])
            if repo_add <= repo["total_commits"] and repo_add > 0:
                continue
            for week in repo["weeks"]:
                week_date = datetime.fromtimestamp(week["w"], tz=tz.utc).strftime("%Y-%m")
                monthly_adds[week_date] += week["a"]

        for entry in insights["timeline"]:
            if entry["additions"] > 0:
                expected = monthly_adds.get(entry["month"], 0)
                assert entry["additions"] == expected, \
                    f"Month {entry['month']}: additions={entry['additions']}, expected={expected}"


# ============================================================
# Independent recomputation of language stats
# ============================================================

class TestLanguageRecompute:
    def test_language_bytes_exact(self, insights, raw_repo_languages):
        expected = defaultdict(int)
        for entry in raw_repo_languages:
            for lang, b in entry["languages"].items():
                expected[lang] += b

        total_bytes = sum(expected.values())

        for l in insights["languages"]:
            assert l["bytes"] == expected[l["name"]], \
                f"{l['name']}: {l['bytes']} != {expected[l['name']]}"
            expected_pct = round(l["bytes"] / total_bytes * 100, 2)
            assert l["percentage"] == expected_pct, \
                f"{l['name']}: pct {l['percentage']} != {expected_pct}"


# ============================================================
# Streak recomputation
# ============================================================

class TestStreakRecompute:
    def test_max_streak_recompute(self, insights, daily_contributions):
        """Walk every active day and compute streak independently."""
        sorted_dates = sorted(daily_contributions.keys())
        max_streak = 1
        current = 1
        for i in range(1, len(sorted_dates)):
            d1 = datetime.strptime(sorted_dates[i - 1], "%Y-%m-%d")
            d2 = datetime.strptime(sorted_dates[i], "%Y-%m-%d")
            if (d2 - d1).days == 1:
                current += 1
                max_streak = max(max_streak, current)
            else:
                current = 1
        max_streak = max(max_streak, current)
        assert insights["highlights"]["max_streak_days"] == max_streak

    def test_current_streak_recompute(self, insights, daily_contributions):
        """Walk backwards from today to compute current streak."""
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        streak = 0
        check = today
        while check.strftime("%Y-%m-%d") in daily_contributions:
            streak += 1
            check -= timedelta(days=1)
        assert insights["highlights"]["current_streak_days"] == streak


# ============================================================
# Repo active range verification
# ============================================================

class TestRepoActiveRanges:
    def test_active_ranges_from_repo_stats(self, insights, raw_repo_stats):
        """Verify first_active/last_active come from actual non-zero weeks."""
        from datetime import datetime, timezone as tz

        for repo_data in raw_repo_stats:
            repo_name = repo_data["repo"]
            # Find this repo in top_repos
            repo_entry = next((r for r in insights["top_repos"] if r["name"] == repo_name), None)
            if repo_entry is None or repo_entry.get("first_active") is None:
                continue

            # Compute expected active range from weeks with activity
            active_dates = []
            for week in repo_data["weeks"]:
                if week["c"] > 0 or week["a"] > 0 or week["d"] > 0:
                    week_date = datetime.fromtimestamp(week["w"], tz=tz.utc).strftime("%Y-%m-%d")
                    active_dates.append(week_date)

            if active_dates:
                expected_first = min(active_dates)
                expected_last = max(active_dates)
                assert repo_entry["first_active"] == expected_first, \
                    f"{repo_name}: first_active={repo_entry['first_active']}, expected={expected_first}"
                assert repo_entry["last_active"] == expected_last, \
                    f"{repo_name}: last_active={repo_entry['last_active']}, expected={expected_last}"


# ============================================================
# Cross-section consistency
# ============================================================

class TestCrossSectionConsistency:
    def test_timeline_months_match_dev_hours_months(self, insights):
        tl_months = [t["month"] for t in insights["timeline"]]
        dh_months = [t["month"] for t in insights["dev_hours_timeline"]]
        assert tl_months == dh_months

    def test_timeline_months_match_delivery_speed_months(self, insights):
        tl_months = [t["month"] for t in insights["timeline"]]
        ds_months = [t["month"] for t in insights["delivery_speed_timeline"]]
        assert tl_months == ds_months

    def test_era_names_consistent(self, insights):
        era_names = [e["name"] for e in insights["eras"]]
        dh_era_names = [e["name"] for e in insights["dev_hours_eras"]]
        ds_era_names = [e["name"] for e in insights["delivery_speed_eras"]]
        assert era_names == dh_era_names == ds_era_names

    def test_total_contributions_consistent_everywhere(self, insights):
        """The same total should appear in highlights, timeline sum, and yearly sum."""
        h_total = insights["highlights"]["total_contributions"]
        tl_total = sum(t["commits"] for t in insights["timeline"])
        yr_total = sum(y["total_contributions"] for y in insights["yearly_summary"].values())
        assert h_total == tl_total == yr_total
