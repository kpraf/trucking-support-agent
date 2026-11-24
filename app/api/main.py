"""FastAPI app. Run with: uv run uvicorn app.api.main:app --reload"""

from datetime import date, datetime
from typing import Annotated

import psycopg
from fastapi import APIRouter, Depends, FastAPI, HTTPException
from pydantic import AfterValidator, BaseModel

from app import config
from app.db import queries
from app.db.connection import get_conn

Conn = Annotated[psycopg.Connection, Depends(get_conn)]
# Timestamps are stored as timestamptz; always show them in Manila time.
ManilaTime = Annotated[datetime, AfterValidator(lambda d: d.astimezone(config.MANILA))]


class ShipmentEvent(BaseModel):
    occurred_at: ManilaTime
    status: str
    location: str
    note: str | None


class Shipment(BaseModel):
    waybill: str
    status: str
    shipper_name: str
    item_description: str
    pieces: int
    receiver_name: str
    receiver_mobile: str
    destination_address: str
    destination_city: str
    destination_province: str
    scheduled_date: date | None
    reschedule_count: int
    delivered_at: ManilaTime | None
    events: list[ShipmentEvent]


# Raw lookups with no identity check, for development and debugging only.
# The agent's tools will mask the address and mobile and require verification first.
dev = APIRouter(prefix="/dev", tags=["dev"])


@dev.get("/shipments/{waybill}", response_model=Shipment)
def get_shipment(waybill: str, conn: Conn):
    canonical = queries.normalize_waybill(waybill)
    if canonical is None:
        raise HTTPException(422, f"'{waybill}' is not a waybill number (expected TRK-12345)")
    shipment = queries.get_shipment(conn, canonical)
    if shipment is None:
        raise HTTPException(404, f"No shipment with waybill {canonical}")
    return {**shipment, "events": queries.get_shipment_events(conn, canonical)}


app = FastAPI(title="Trucking Support Agent")


@app.get("/health")
def health(conn: Conn):
    conn.execute("SELECT 1")
    return {"status": "ok", "today": config.today().isoformat(), "env": config.APP_ENV}


if config.APP_ENV != "prod":
    app.include_router(dev)
