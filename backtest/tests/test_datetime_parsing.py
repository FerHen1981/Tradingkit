"""DateTime parsing across the shapes our data sources actually produce.

Two failure modes are guarded here, both silent-by-nature:

1. A multi-year ET export crosses a DST boundary, so December bars carry -05:00
   and August bars -04:00. pandas raises "Mixed timezones detected" during
   parsing — before `errors="coerce"` can do anything — so a 2011-2026 file
   simply blew up on load.
2. The fix for (1) is `utc=True`, which is WRONG for a naive column: pandas
   reads the wall clock as UTC and converts it to ET five hours off, moving
   every bar into a different session. That would corrupt the 18:00 ET session
   boundary (ground rule 3) without raising anything at all.
"""
from __future__ import annotations

import pandas as pd
import pytest

from backtest.data import _has_offset, _parse_datetimes

# label -> (raw values, expected first timestamp as ET wall clock)
SHAPES = {
    "constant offset":     (["04-12-2011 09:30:00 -0500", "05-12-2011 09:30:00 -0500"],
                            "2011-12-04 09:30"),
    "dst boundary":        (["04-12-2011 09:30:00 -0500", "16-08-2026 09:30:00 -0400"],
                            "2011-12-04 09:30"),
    "offset with colon":   (["04-12-2011 09:30:00 -05:00", "16-08-2026 09:30:00 -04:00"],
                            "2011-12-04 09:30"),
    "naive day-first":     (["04-12-2011 09:30:00", "16-08-2026 09:30:00"],
                            "2011-12-04 09:30"),
    "iso with offsets":    (["2011-12-04 09:30:00-05:00", "2026-08-16 09:30:00-04:00"],
                            "2011-12-04 09:30"),
    "iso naive":           (["2011-12-04 09:30:00", "2026-08-16 09:30:00"],
                            "2011-12-04 09:30"),
    "zulu":                (["2011-12-04 14:30:00Z", "2026-08-16 13:30:00Z"],
                            "2011-12-04 09:30"),
}


def _as_et(series):
    return (series.dt.tz_localize("America/New_York") if series.dt.tz is None
            else series.dt.tz_convert("America/New_York"))


@pytest.mark.parametrize("label", sorted(SHAPES))
def test_shape_parses_to_the_right_wall_clock(label):
    raw, want = SHAPES[label]
    et = _as_et(_parse_datetimes(pd.Series(raw)))
    assert et.dt.strftime("%Y-%m-%d %H:%M").iloc[0] == want
    assert not et.isna().any()


def test_a_naive_column_is_never_treated_as_utc():
    """The regression that matters most: a five-hour shift is invisible in the
    data but moves bars across the 18:00 ET session boundary."""
    naive = pd.Series(["04-12-2011 09:30:00", "16-08-2026 09:30:00"])
    assert _has_offset(naive) is False
    et = _as_et(_parse_datetimes(naive))
    assert list(et.dt.hour) == [9, 9], "wall clock shifted — parsed as UTC"


def test_offsets_are_detected_where_they_exist():
    assert _has_offset(pd.Series(["04-12-2011 09:30:00 -0500"])) is True
    assert _has_offset(pd.Series(["04-12-2011 09:30:00 -05:00"])) is True
    assert _has_offset(pd.Series(["2011-12-04 14:30:00Z"])) is True
    assert _has_offset(pd.Series(["04-12-2011 09:30:00"])) is False
    assert _has_offset(pd.Series([""])) is False


def test_unparseable_values_still_raise():
    with pytest.raises(ValueError):
        _parse_datetimes(pd.Series(["niet een datum", "ook niet"]))


def test_a_dst_crossing_file_loads_end_to_end(tmp_path):
    """The actual VPS shape: a file whose first bar is EST and last bar EDT."""
    import numpy as np

    from backtest import data as dm

    idx = pd.DatetimeIndex(
        list(pd.date_range("2011-12-04 09:30", periods=30, freq="1min",
                           tz="America/New_York"))
        + list(pd.date_range("2026-08-16 09:30", periods=30, freq="1min",
                             tz="America/New_York")))
    n = len(idx)
    df = pd.DataFrame({
        "DateTime": idx.strftime("%d-%m-%Y %H:%M:%S %z"),
        "Open": np.full(n, 100.0), "High": np.full(n, 101.0),
        "Low": np.full(n, 99.0), "Close": np.full(n, 100.5),
        "Volume": np.full(n, 10.0), "Delta": np.zeros(n),
    })
    csv = tmp_path / "dst.csv"
    df.to_csv(csv, index=False)

    out = dm.load(str(csv), cache=False)
    assert len(out) == n
    assert str(out["et"].dt.tz) == "America/New_York"
    assert out["et"].iloc[0].strftime("%Y-%m-%d %H:%M") == "2011-12-04 09:30"
    assert out["et"].iloc[-1].strftime("%Y-%m-%d %H:%M") == "2026-08-16 09:59"
