"""Scheduled report delivery timing.

The failure mode that matters is a schedule that silently stops sending — so
these focus on due-ness and on what happens to `last_sent_at` when a send fails.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.models.report_schedule import ReportSchedule
from app.services.report_scheduler import is_due, _recipients


def make(**kwargs) -> ReportSchedule:
    defaults = dict(
        name="Weekly",
        frequency="weekly",
        send_hour=7,
        send_day=0,  # Monday
        period="7d",
        recipients=json.dumps(["ops@example.com"]),
        enabled=True,
        last_sent_at=None,
        send_count=0,
    )
    defaults.update(kwargs)
    return ReportSchedule(**defaults)


# A Monday at 08:00 UTC.
MONDAY_0800 = datetime(2026, 9, 7, 8, 0, tzinfo=timezone.utc)


class TestRecipients:
    def test_parses_json_list(self):
        assert _recipients(make()) == ["ops@example.com"]

    def test_empty_when_unset(self):
        assert _recipients(make(recipients="[]")) == []

    def test_survives_malformed_json(self):
        assert _recipients(make(recipients="not json")) == []


class TestDueness:
    def test_due_on_its_day_and_hour(self):
        assert is_due(make(), MONDAY_0800) is True

    def test_not_due_before_send_hour(self):
        assert is_due(make(), MONDAY_0800.replace(hour=6)) is False

    def test_not_due_on_the_wrong_weekday(self):
        tuesday = MONDAY_0800 + timedelta(days=1)
        assert is_due(make(), tuesday) is False

    def test_disabled_is_never_due(self):
        assert is_due(make(enabled=False), MONDAY_0800) is False

    def test_no_recipients_is_never_due(self):
        assert is_due(make(recipients="[]"), MONDAY_0800) is False

    def test_not_resent_within_the_same_week(self):
        just_sent = make(last_sent_at=MONDAY_0800 - timedelta(hours=1))
        assert is_due(just_sent, MONDAY_0800) is False

    def test_due_again_the_following_week(self):
        last_week = make(last_sent_at=MONDAY_0800 - timedelta(days=7))
        assert is_due(last_week, MONDAY_0800) is True

    def test_naive_last_sent_is_treated_as_utc(self):
        """Postgres can hand back a naive datetime; comparing it to an aware
        `now` would raise and take the whole scheduler loop down."""
        naive = make(last_sent_at=(MONDAY_0800 - timedelta(days=7)).replace(tzinfo=None))
        assert is_due(naive, MONDAY_0800) is True

    def test_daily_uses_a_shorter_gap(self):
        daily = make(frequency="daily", send_day=None,
                     last_sent_at=MONDAY_0800 - timedelta(hours=21))
        assert is_due(daily, MONDAY_0800) is True

        recent = make(frequency="daily", send_day=None,
                      last_sent_at=MONDAY_0800 - timedelta(hours=2))
        assert is_due(recent, MONDAY_0800) is False

    def test_monthly_fires_on_its_day_of_month(self):
        monthly = make(frequency="monthly", send_day=7)
        assert is_due(monthly, MONDAY_0800) is True

        assert is_due(make(frequency="monthly", send_day=15), MONDAY_0800) is False

    def test_a_missed_slot_is_still_sent_later_that_day(self):
        """A container that was down at 07:00 should still send at 14:00 rather
        than skipping the week entirely."""
        assert is_due(make(), MONDAY_0800.replace(hour=14)) is True
