import pytest

from app.db.queries import normalize_waybill


@pytest.mark.parametrize("raw", ["TRK-10293", "trk-10293", "TRK10293", "trk 10293", " TRK-10293 "])
def test_normalize_waybill(raw):
    assert normalize_waybill(raw) == "TRK-10293"


@pytest.mark.parametrize("raw", ["10293", "TRK-1029", "TRK-102931", "ABC-10293", ""])
def test_normalize_waybill_rejects(raw):
    assert normalize_waybill(raw) is None
