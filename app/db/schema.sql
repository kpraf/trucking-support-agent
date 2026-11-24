-- Trucking support agent schema.
-- Applied by `python -m app.db.seed`, which drops and recreates everything.

DROP TABLE IF EXISTS handoffs, claims, reschedules, shipment_events, shipments, receivers CASCADE;

CREATE TABLE receivers (
    id          SERIAL PRIMARY KEY,
    full_name   TEXT NOT NULL,
    mobile      TEXT NOT NULL UNIQUE CHECK (mobile ~ '^09[0-9]{9}$'),
    city        TEXT NOT NULL,
    province    TEXT NOT NULL CHECK (province IN ('Laguna', 'Cavite'))
);

CREATE TABLE shipments (
    waybill               TEXT PRIMARY KEY CHECK (waybill ~ '^TRK-[0-9]{5}$'),
    receiver_id           INTEGER NOT NULL REFERENCES receivers (id),
    shipper_name          TEXT NOT NULL,
    item_description      TEXT NOT NULL,
    pieces                INTEGER NOT NULL CHECK (pieces > 0),
    destination_address   TEXT NOT NULL,
    destination_city      TEXT NOT NULL,
    destination_province  TEXT NOT NULL CHECK (destination_province IN ('Laguna', 'Cavite')),
    status                TEXT NOT NULL CHECK (status IN (
                              'booked', 'picked_up', 'at_hub', 'out_for_delivery',
                              'delivered', 'failed_attempt', 'on_hold', 'returned_to_shipper')),
    scheduled_date        DATE,
    reschedule_count      INTEGER NOT NULL DEFAULT 0 CHECK (reschedule_count >= 0),
    delivered_at          TIMESTAMPTZ,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((status = 'delivered') = (delivered_at IS NOT NULL))
);

CREATE INDEX shipments_receiver_idx ON shipments (receiver_id);

CREATE TABLE shipment_events (
    id          SERIAL PRIMARY KEY,
    waybill     TEXT NOT NULL REFERENCES shipments (waybill) ON DELETE CASCADE,
    occurred_at TIMESTAMPTZ NOT NULL,
    status      TEXT NOT NULL,
    location    TEXT NOT NULL,
    note        TEXT
);

CREATE INDEX shipment_events_waybill_idx ON shipment_events (waybill, occurred_at);

CREATE TABLE reschedules (
    id          SERIAL PRIMARY KEY,
    waybill     TEXT NOT NULL REFERENCES shipments (waybill) ON DELETE CASCADE,
    old_date    DATE NOT NULL,
    new_date    DATE NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE claims (
    id          SERIAL PRIMARY KEY,
    waybill     TEXT NOT NULL REFERENCES shipments (waybill) ON DELETE CASCADE,
    type        TEXT NOT NULL CHECK (type IN ('damaged', 'missing_item', 'failed_delivery_dispute')),
    description TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'in_review', 'resolved', 'rejected')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- waybill is nullable: a handoff after 3 failed verification tries may not have a valid waybill.
CREATE TABLE handoffs (
    id               SERIAL PRIMARY KEY,
    waybill          TEXT REFERENCES shipments (waybill) ON DELETE CASCADE,
    reason           TEXT NOT NULL,
    conversation_id  TEXT NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
