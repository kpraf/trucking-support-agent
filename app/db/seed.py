"""Reset the database and fill it with fake Laguna/Cavite delivery data.

    uv run python -m app.db.seed                    # anchored on today (or APP_TODAY)
    uv run python -m app.db.seed --today 2026-12-01 --seed 7

The same --today and --seed always give the same rows, so eval runs can reset
to a known state. generate() is pure (no database) so it can be unit tested.
"""

import argparse
import random
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path

import psycopg

from app import config
from app.db import seed_data as sd
from app.db.connection import connect

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
NUM_RECEIVERS = 150
FIRST_WAYBILL = 10001
RESCHEDULABLE = {"booked", "picked_up", "at_hub", "failed_attempt", "on_hold"}


@dataclass
class Dataset:
    receivers: list[dict] = field(default_factory=list)
    shipments: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    reschedules: list[dict] = field(default_factory=list)


def _forward_to_delivery_day(d: date) -> date:
    """Trucks run Monday to Saturday: push a Sunday to Monday."""
    return d + timedelta(days=1) if d.weekday() == 6 else d


def _back_to_delivery_day(d: date) -> date:
    return d - timedelta(days=1) if d.weekday() == 6 else d


class _Generator:
    def __init__(self, today: date, seed: int):
        self.today = today
        self.rng = random.Random(seed)
        self.data = Dataset()
        # the seed treats "now" as today 11:59 Manila; nothing is stamped after it
        self.now = datetime.combine(today, time(11, 59), tzinfo=config.MANILA)

    # ---- helpers -------------------------------------------------------

    def at(self, day: date, lo_hour: int, hi_hour: int) -> datetime:
        """A random time on `day`. Events today stay before 11:00, leaving room before `now`."""
        if day == self.today:
            hi_hour = min(hi_hour, 10)
            lo_hour = min(lo_hour, hi_hour)
        t = time(self.rng.randint(lo_hour, hi_hour), self.rng.randint(0, 59))
        return datetime.combine(day, t, tzinfo=config.MANILA)

    def days_ago(self, lo: int, hi: int) -> date:
        return self.today - timedelta(days=self.rng.randint(lo, hi))

    def event(self, waybill: str, when: datetime, status: str, location: str, note=None):
        self.data.events.append(
            {
                "waybill": waybill,
                "occurred_at": when,
                "status": status,
                "location": location,
                "note": note,
            }
        )

    # ---- receivers ------------------------------------------------------

    def make_receivers(self):
        used_mobiles: set[str] = set()
        cities = list(sd.CITIES)
        for i in range(1, NUM_RECEIVERS + 1):
            name = f"{self.rng.choice(sd.FIRST_NAMES)} {self.rng.choice(sd.LAST_NAMES)}"
            if self.rng.random() < 0.3:  # some people give a middle initial
                name = name.replace(" ", f" {self.rng.choice('ABCDEFGHIJLMNPRSTV')}. ", 1)
            while True:
                mobile = self.rng.choice(sd.MOBILE_PREFIXES) + f"{self.rng.randint(0, 9999999):07d}"
                if mobile not in used_mobiles:
                    used_mobiles.add(mobile)
                    break
            city = self.rng.choice(cities)
            self.data.receivers.append(
                {
                    "id": i,
                    "full_name": name,
                    "mobile": mobile,
                    "city": city,
                    "province": sd.CITIES[city][0],
                }
            )

    def address(self, city: str) -> str:
        province, barangays = sd.CITIES[city]
        brgy = self.rng.choice(barangays)
        style = self.rng.random()
        if style < 0.45:
            line = (
                f"Blk {self.rng.randint(1, 40)} Lot {self.rng.randint(1, 30)}, "
                f"{self.rng.choice(sd.SUBDIVISIONS)}"
            )
        elif style < 0.85:
            line = f"{self.rng.randint(1, 999)} {self.rng.choice(sd.STREETS)} St."
        else:
            line = f"Purok {self.rng.randint(1, 7)}"
        return f"{line}, Brgy. {brgy}, {city}, {province}"

    # ---- shipments ------------------------------------------------------

    def make_shipments(self):
        statuses = [s for s, n in sd.STATUS_COUNTS.items() for _ in range(n)]
        self.rng.shuffle(statuses)

        # every receiver gets at least one shipment, the rest go to repeat receivers
        receiver_ids = [r["id"] for r in self.data.receivers]
        self.rng.shuffle(receiver_ids)
        extra = len(statuses) - len(receiver_ids)
        receiver_ids += [self.rng.choice(receiver_ids) for _ in range(extra)]

        for n, (status, receiver_id) in enumerate(zip(statuses, receiver_ids, strict=True)):
            waybill = f"TRK-{FIRST_WAYBILL + n}"
            receiver = self.data.receivers[receiver_id - 1]
            same_province = [c for c, (p, _) in sd.CITIES.items() if p == receiver["province"]]
            # most deliveries go to the receiver's home city, some to a workplace nearby
            city = receiver["city"] if self.rng.random() < 0.85 else self.rng.choice(same_province)
            shipper = self.rng.choice(list(sd.SHIPPERS))
            origin, items = sd.SHIPPERS[shipper]
            item, pieces = self.rng.choice(items)

            shipment = {
                "waybill": waybill,
                "receiver_id": receiver_id,
                "shipper_name": shipper,
                "item_description": item,
                "pieces": pieces,
                "destination_address": self.address(city),
                "destination_city": city,
                "destination_province": sd.CITIES[city][0],
                "status": status,
                "scheduled_date": None,
                "reschedule_count": 0,
                "delivered_at": None,
                "created_at": None,
            }
            self.build_timeline(shipment, receiver, origin)
            if status in RESCHEDULABLE:
                self.add_reschedule_history(shipment)
            self.data.shipments.append(shipment)

    def build_timeline(self, s: dict, receiver: dict, origin: str):
        """Fill dates and events so they match the shipment's current status."""
        wb, status = s["waybill"], s["status"]
        hub = sd.HUBS[s["destination_city"]]
        dest = f"{s['destination_city']}, {s['destination_province']}"
        origin_loc = f"{origin} (shipper warehouse)"

        if status == "booked":
            booked = self.days_ago(0, 2)
            s["scheduled_date"] = _forward_to_delivery_day(
                self.today + timedelta(days=self.rng.randint(2, 6))
            )
            steps = [(booked, "booked")]
        elif status == "picked_up":
            picked = self.days_ago(0, 1)
            steps = [
                (picked - timedelta(days=self.rng.randint(1, 2)), "booked"),
                (picked, "picked_up"),
            ]
            s["scheduled_date"] = _forward_to_delivery_day(
                self.today + timedelta(days=self.rng.randint(1, 4))
            )
        elif status in ("at_hub", "on_hold"):
            hub_day = self.days_ago(0, 2)
            picked = hub_day - timedelta(days=self.rng.randint(1, 2))
            steps = [
                (picked - timedelta(days=1), "booked"),
                (picked, "picked_up"),
                (hub_day, "at_hub"),
            ]
            if status == "at_hub":
                s["scheduled_date"] = _forward_to_delivery_day(
                    self.today + timedelta(days=self.rng.randint(0, 3))
                )
            else:
                s["scheduled_date"] = _back_to_delivery_day(hub_day)
                steps.append((hub_day, "on_hold"))
        elif status == "out_for_delivery":
            hub_day = self.today - timedelta(days=1)
            steps = [
                (hub_day - timedelta(days=2), "booked"),
                (hub_day - timedelta(days=1), "picked_up"),
                (hub_day, "at_hub"),
                (self.today, "out_for_delivery"),
            ]
            s["scheduled_date"] = self.today
        elif status in ("delivered", "failed_attempt", "returned_to_shipper"):
            if status == "delivered":
                # about 60% inside the 7-day claim window, the rest outside it
                last = self.days_ago(0, 6) if self.rng.random() < 0.6 else self.days_ago(8, 25)
            elif status == "failed_attempt":
                last = self.days_ago(1, 3)
            else:
                last = self.days_ago(3, 15)
            last = _back_to_delivery_day(last)
            hub_day = last - timedelta(days=1)
            steps = [
                (hub_day - timedelta(days=2), "booked"),
                (hub_day - timedelta(days=1), "picked_up"),
                (hub_day, "at_hub"),
                (last, "out_for_delivery"),
                (last, status),
            ]
            if status == "returned_to_shipper":
                first_try = _back_to_delivery_day(last - timedelta(days=2))
                steps = [
                    (first_try - timedelta(days=3), "booked"),
                    (first_try - timedelta(days=2), "picked_up"),
                    (first_try - timedelta(days=1), "at_hub"),
                    (first_try, "out_for_delivery"),
                    (first_try, "failed_attempt"),
                    (last, "out_for_delivery"),
                    (last, "failed_attempt"),
                    (last, "returned_to_shipper"),
                ]
            s["scheduled_date"] = last
        else:
            raise ValueError(f"unknown status {status}")

        hours = {
            "booked": (9, 17),
            "picked_up": (8, 16),
            "at_hub": (18, 23),
            "out_for_delivery": (6, 8),
            "on_hold": (19, 23),
            "delivered": (9, 17),
            "failed_attempt": (9, 17),
            "returned_to_shipper": (18, 21),
        }
        last_time = None
        for day, st in steps:
            when = self.at(day, *hours[st])
            if last_time and when <= last_time:  # keep events in order
                when = last_time + timedelta(minutes=self.rng.randint(20, 90))
                if when > self.now:  # stacked events today: squeeze them in before "now"
                    gap = (self.now - last_time).total_seconds() // 2
                    when = last_time + timedelta(seconds=gap)
            last_time = when
            location, note = {
                "booked": (origin_loc, None),
                "picked_up": (origin_loc, None),
                "at_hub": (hub, None),
                "out_for_delivery": (hub, None),
                "delivered": (dest, None),
                "failed_attempt": (dest, self.rng.choice(sd.FAILED_ATTEMPT_NOTES)),
                "on_hold": (hub, self.rng.choice(sd.ON_HOLD_NOTES)),
                "returned_to_shipper": (hub, "Returned to shipper after 2 failed attempts"),
            }[st]
            if st == "delivered":
                first = receiver["full_name"].split()[0]
                note = (
                    f"Received by {first}"
                    if self.rng.random() < 0.7
                    else "Received by household member"
                )
                s["delivered_at"] = when
            self.event(wb, when, st, location, note)
            if s["created_at"] is None:
                s["created_at"] = when

    def add_reschedule_history(self, s: dict):
        """Some shipments were already moved once or twice (2 is the max, for limit tests)."""
        roll = self.rng.random()
        count = 0 if roll < 0.70 else 1 if roll < 0.88 else 2
        new_date = s["scheduled_date"]
        rows = []
        for _ in range(count):
            old_date = _back_to_delivery_day(new_date - timedelta(days=self.rng.randint(1, 3)))
            created = max(
                s["created_at"] + timedelta(hours=1), self.at(old_date - timedelta(days=1), 9, 18)
            )
            created = min(created, self.now)  # never in the future
            rows.append(
                {
                    "waybill": s["waybill"],
                    "old_date": old_date,
                    "new_date": new_date,
                    "created_at": created,
                }
            )
            new_date = old_date
        rows.reverse()
        self.data.reschedules.extend(rows)
        s["reschedule_count"] = count


def generate(today: date, seed: int = 42) -> Dataset:
    g = _Generator(today, seed)
    g.make_receivers()
    g.make_shipments()
    return g.data


def apply_schema(conn: psycopg.Connection):
    conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))


def insert(conn: psycopg.Connection, data: Dataset):
    def copy(table: str, rows: list[dict]):
        if not rows:
            return
        cols = list(rows[0])
        with conn.cursor().copy(f"COPY {table} ({', '.join(cols)}) FROM STDIN") as cp:
            for row in rows:
                cp.write_row([row[c] for c in cols])

    copy("receivers", data.receivers)
    copy("shipments", data.shipments)
    copy("shipment_events", data.events)
    copy("reschedules", data.reschedules)
    # receivers.id was set explicitly, so move the sequence past it
    conn.execute("SELECT setval('receivers_id_seq', (SELECT max(id) FROM receivers))")


def reset_database(conn: psycopg.Connection, today: date, seed: int = 42) -> Dataset:
    """Drop everything, recreate the schema and load the seed. Used by evals too."""
    data = generate(today, seed)
    with conn.transaction():
        apply_schema(conn)
        insert(conn, data)
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--today",
        type=date.fromisoformat,
        default=None,
        help="anchor date YYYY-MM-DD (default: APP_TODAY or today in Manila)",
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    today = args.today or config.today()

    with connect() as conn:
        data = reset_database(conn, today, args.seed)

    by_status: dict[str, int] = {}
    for s in data.shipments:
        by_status[s["status"]] = by_status.get(s["status"], 0) + 1
    print(
        f"Seeded for {today} (seed {args.seed}): {len(data.receivers)} receivers, "
        f"{len(data.shipments)} shipments, {len(data.events)} events, "
        f"{len(data.reschedules)} reschedules"
    )
    print("  " + ", ".join(f"{k} {v}" for k, v in sorted(by_status.items())))


if __name__ == "__main__":
    main()
