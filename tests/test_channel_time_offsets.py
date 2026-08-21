from pathlib import Path

from src.channel_time_offsets import load_channel_time_offsets, channel_time_offset_minutes
from src.utils import shift_xmltv_timestamp


def test_all_openbox_cps_channels_shift_plus_two_hours():
    load_channel_time_offsets.cache_clear()
    assert channel_time_offset_minutes("openbox-tsd", "cps-ussr") == 120
    assert channel_time_offset_minutes("openbox-tsd", "cps-drama") == 120
    assert channel_time_offset_minutes("openbox-tsd", "cps-comedy") == 120
    assert channel_time_offset_minutes("openbox-tsd", "cps-new-channel") == 120


def test_non_cps_and_other_sources_are_not_shifted():
    load_channel_time_offsets.cache_clear()
    assert channel_time_offset_minutes("openbox-tsd", "mm-ussr-drama") == 0
    assert channel_time_offset_minutes("runigma", "cps-ussr") == 0


def test_plus_two_hours_rolls_into_next_day():
    assert shift_xmltv_timestamp("20260821233000 -0700", 120) == "20260822013000 -0700"


def test_loader_accepts_prefix_rule(tmp_path: Path):
    path = tmp_path / "offsets.csv"
    path.write_text(
        "enabled,source,source_id,offset_minutes,notes\n"
        "1,openbox-tsd,cps-*,120,ok\n",
        encoding="utf-8",
    )
    rules = load_channel_time_offsets(path)
    assert rules == {("openbox-tsd", "cps-*"): 120}
