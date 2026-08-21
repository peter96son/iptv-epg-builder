from pathlib import Path

from src.channel_time_offsets import load_channel_time_offsets, channel_time_offset_minutes
from src.utils import shift_xmltv_timestamp, convert_xmltv_timestamp


def test_cps_ussr_rule_is_exactly_plus_14_hours():
    load_channel_time_offsets.cache_clear()
    assert channel_time_offset_minutes("openbox-tsd", "cps-ussr") == 14 * 60


def test_cps_sibling_channels_are_not_shifted():
    load_channel_time_offsets.cache_clear()
    assert channel_time_offset_minutes("openbox-tsd", "cps-drama") == 0
    assert channel_time_offset_minutes("openbox-tsd", "cps-comedy") == 0
    assert channel_time_offset_minutes("iptv-online-primary", "cps-ussr") == 0


def test_plus_14h_matches_observed_0711_to_2111_los_angeles():
    shifted = shift_xmltv_timestamp("20260820071100 -0700", 14 * 60)
    assert shifted == "20260820211100 -0700"
    assert convert_xmltv_timestamp(shifted, "America/Los_Angeles") == "20260820211100 -0700"


def test_plus_14h_rolls_programme_times_into_next_day():
    shifted = shift_xmltv_timestamp("20260820150000 -0700", 14 * 60)
    assert shifted == "20260821050000 -0700"


def test_loader_fails_closed_on_malformed_rows(tmp_path: Path):
    path = tmp_path / "offsets.csv"
    path.write_text(
        "enabled,source,source_id,offset_minutes,notes\n"
        "1,openbox-tsd,cps-ussr,840,ok\n"
        "1,openbox-tsd,cps-drama,nope,bad\n"
        "1,openbox-tsd,cps-comedy,60,bad,extra\n",
        encoding="utf-8",
    )
    rules = load_channel_time_offsets(path)
    assert rules == {("openbox-tsd", "cps-ussr"): 840}
