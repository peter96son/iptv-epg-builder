from datetime import datetime, timedelta, timezone

from src.xmltv import ARCHIVE_PAST_DAYS, XMLTVSource


def _stamp(dt):
    return dt.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S +0000")


def _source_with_programmes(*starts):
    rows = ['<tv><channel id="c"><display-name>C</display-name></channel>']
    for i, start in enumerate(starts):
        stop = start + timedelta(hours=1)
        rows.append(
            f'<programme channel="c" start="{_stamp(start)}" stop="{_stamp(stop)}">'
            f'<title>P{i}</title></programme>'
        )
    rows.append("</tv>")
    return "".join(rows).encode("utf-8")


def test_default_archive_retention_is_five_days():
    assert ARCHIVE_PAST_DAYS == 5


def test_fresh_programmes_keeps_four_day_old_archive_row():
    now = datetime.now(timezone.utc)
    data = _source_with_programmes(now - timedelta(days=4))
    source = XMLTVSource("test-no-offset", data)
    rows = list(source.fresh_programmes({"c"}))
    assert len(rows) == 1


def test_fresh_programmes_drops_six_day_old_archive_row():
    now = datetime.now(timezone.utc)
    data = _source_with_programmes(now - timedelta(days=6))
    source = XMLTVSource("test-no-offset", data)
    rows = list(source.fresh_programmes({"c"}))
    assert rows == []


def test_explicit_shorter_window_still_supported():
    now = datetime.now(timezone.utc)
    data = _source_with_programmes(now - timedelta(days=4))
    source = XMLTVSource("test-no-offset", data)
    rows = list(source.fresh_programmes({"c"}, past_days=2))
    assert rows == []
