"""Seed data invariants. Pure Python, no database needed."""

import re
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta

import pytest

from app import config
from app.db import seed_data as sd
from app.db.seed import generate

TODAY = date(2026, 12, 2)  # a Wednesday
NOW = datetime.combine(TODAY, time(11, 59), tzinfo=config.MANILA)


@pytest.fixture(scope="module")
def data():
    return generate(TODAY, seed=42)


def test_counts(data):
    assert len(data.receivers) == 150
    assert len(data.shipments) == 200
    assert Counter(s["status"] for s in data.shipments) == sd.STATUS_COUNTS


def test_same_seed_same_data():
    a, b = generate(TODAY, seed=1), generate(TODAY, seed=1)
    assert a.shipments == b.shipments and a.events == b.events
    assert generate(TODAY, seed=2).shipments != a.shipments


def test_receivers(data):
    mobiles = [r["mobile"] for r in data.receivers]
    assert len(set(mobiles)) == len(mobiles)
    assert all(re.fullmatch(r"09\d{9}", m) for m in mobiles)
    per_receiver = Counter(s["receiver_id"] for s in data.shipments)
    assert set(per_receiver) == {r["id"] for r in data.receivers}
    assert any(n > 1 for n in per_receiver.values()), "need some repeat receivers"


def test_events_match_status(data):
    events = defaultdict(list)
    for e in data.events:
        events[e["waybill"]].append(e)
    for s in data.shipments:
        evs = events[s["waybill"]]
        times = [e["occurred_at"] for e in evs]
        assert times == sorted(times), s["waybill"]
        assert len(set(times)) == len(times), s["waybill"]
        assert times[-1] <= NOW, f"{s['waybill']} has an event in the future"
        assert evs[0]["status"] == "booked"
        assert evs[-1]["status"] == s["status"]
        assert s["created_at"] == times[0]
        if s["status"] == "delivered":
            assert s["delivered_at"] == times[-1]
        else:
            assert s["delivered_at"] is None


def test_scheduled_dates(data):
    for s in data.shipments:
        assert s["scheduled_date"] is not None
        if s["status"] in ("booked", "picked_up", "at_hub"):
            assert s["scheduled_date"] >= TODAY
            assert s["scheduled_date"].weekday() != 6, "no Sunday deliveries"
        if s["status"] == "out_for_delivery":
            assert s["scheduled_date"] == TODAY


def test_claim_window_has_both_sides(data):
    ages = [
        (TODAY - s["delivered_at"].date()).days
        for s in data.shipments
        if s["status"] == "delivered"
    ]
    assert any(a <= 7 for a in ages) and any(a > 7 for a in ages)


def test_reschedule_history(data):
    rows = Counter(r["waybill"] for r in data.reschedules)
    by_wb = {s["waybill"]: s for s in data.shipments}
    for s in data.shipments:
        assert s["reschedule_count"] == rows.get(s["waybill"], 0)
        assert 0 <= s["reschedule_count"] <= 2
    assert any(s["reschedule_count"] == 2 for s in data.shipments), "need max-limit cases"
    for r in data.reschedules:
        s = by_wb[r["waybill"]]
        assert r["old_date"] < r["new_date"]
        assert s["created_at"] <= r["created_at"] <= NOW
    # the latest move lands on the current scheduled date
    latest = {}
    for r in data.reschedules:
        latest[r["waybill"]] = r
    for wb, r in latest.items():
        assert r["new_date"] == by_wb[wb]["scheduled_date"]


def test_destinations_stay_in_province(data):
    receivers = {r["id"]: r for r in data.receivers}
    for s in data.shipments:
        assert s["destination_province"] == receivers[s["receiver_id"]]["province"]
        assert s["destination_address"].endswith(
            f"{s['destination_city']}, {s['destination_province']}"
        )


@pytest.mark.parametrize("today", [TODAY + timedelta(days=i) for i in range(7)])
def test_any_weekday_anchor(today):
    """The generator shouldn't break when 'today' is a Saturday or Sunday."""
    d = generate(today, seed=3)
    now = datetime.combine(today, time(11, 59), tzinfo=config.MANILA)
    assert all(e["occurred_at"] <= now for e in d.events)
