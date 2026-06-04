"""Altitude metric consistency (Phase 1 hotfix).

The Verify tab's MAX ALTITUDE previously read GPS.Alt first and showed 0.0 m (GPS.Alt
is an unpopulated ~0 denormal on these logs). It must now match the Debrief MAX
ALTITUDE, which uses the authoritative FlightMetrics.max_altitude (POS.RelHomeAlt
hierarchy, GPS excluded).
"""
import os
import pytest

from core.flight_metrics import FlightMetrics

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.mark.parametrize('fname,expected', [
    ('00000002.BIN', '10.0 m'),
    ('00000011.BIN', '4.8 m'),
    ('00000012.BIN', '14.0 m'),
])
def test_verify_altitude_matches_debrief(qtbot, fname, expected):
    path = os.path.join(_ROOT, 'logs', fname)
    if not os.path.isfile(path):
        pytest.skip(f'{fname} not present')
    from core.log_parser import DataFlashParser
    from ui.widgets.flight_summary import FlightSummaryWidget

    data = DataFlashParser().parse(path)
    debrief_txt = FlightMetrics.max_altitude(data)[1]   # the value Debrief shows

    w = FlightSummaryWidget(); qtbot.addWidget(w)
    w.update_data(data)
    verify_txt = w._alt._val.text()                     # the Verify-tab card

    assert verify_txt == debrief_txt        # Verify == Debrief (the requirement)
    assert verify_txt == expected           # and the expected metres
    assert verify_txt != '0.0 m'            # never the old GPS-first bug
