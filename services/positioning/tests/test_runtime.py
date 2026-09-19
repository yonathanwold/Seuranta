from __future__ import annotations

from datetime import datetime, timedelta

from services.data.models import AnchorDefinition, Mode, SignalObservation, utc_now
from services.positioning.runtime import InternalPositioner


def _observation(anchor_id: str, rssi_dbm: int, sequence_number: int, observed_at: datetime) -> SignalObservation:
    return SignalObservation(
        observation_id=f"{anchor_id}-{sequence_number}",
        observed_at=observed_at,
        timestamp_ms=1767268800000,
        run_id="run-1",
        deployment_id="demo-1",
        building_id="room-1",
        floor_id="floor-1",
        anchor_id=anchor_id,
        session_id="iphone-demo",
        rssi_dbm=rssi_dbm,
        channel=37,
        source="ble",
        mode=Mode.REAL,
        sequence_number=sequence_number,
    )


def test_positioner_uses_the_median_rssi_for_each_anchor_scan():
    positioner = InternalPositioner([
        AnchorDefinition(anchor_id="pi-1", x_m=0, y_m=0),
        AnchorDefinition(anchor_id="pi-2", x_m=6, y_m=0),
        AnchorDefinition(anchor_id="pi-3", x_m=0, y_m=4),
        AnchorDefinition(anchor_id="pi-4", x_m=6, y_m=4),
    ])
    observed_at = utc_now()
    readings = [
        _observation("pi-1", -58, 1, observed_at), _observation("pi-1", -62, 2, observed_at), _observation("pi-1", -60, 3, observed_at),
        _observation("pi-2", -63, 4, observed_at), _observation("pi-2", -67, 5, observed_at), _observation("pi-2", -65, 6, observed_at),
        _observation("pi-3", -60, 7, observed_at), _observation("pi-3", -64, 8, observed_at), _observation("pi-3", -62, 9, observed_at),
        _observation("pi-4", -66, 10, observed_at), _observation("pi-4", -70, 11, observed_at), _observation("pi-4", -68, 12, observed_at),
    ]

    positions = positioner.ingest(readings)

    key = positioner._key(readings[0])
    assert {anchor_id: item.rssi_dbm for anchor_id, item in positioner._recent[key].items()} == {
        "pi-1": -60,
        "pi-2": -65,
        "pi-3": -62,
        "pi-4": -68,
    }
    assert len(positions) == 1
    assert positions[0].observation_count == 4


def test_positioner_uses_the_median_of_recent_scans_for_an_anchor():
    positioner = InternalPositioner([
        AnchorDefinition(anchor_id="pi-1", x_m=0, y_m=0),
        AnchorDefinition(anchor_id="pi-2", x_m=6, y_m=0),
        AnchorDefinition(anchor_id="pi-3", x_m=0, y_m=4),
    ])
    observed_at = utc_now()
    scans = [
        _observation("pi-1", -70, 1, observed_at),
        _observation("pi-1", -50, 2, observed_at + timedelta(seconds=8)),
        _observation("pi-1", -60, 3, observed_at + timedelta(seconds=16)),
    ]

    aggregate = positioner._aggregate_recent_scans(positioner._key(scans[0]), "pi-1", scans)

    assert aggregate.rssi_dbm == -60
    assert aggregate.observation_id not in {scan.observation_id for scan in scans}
