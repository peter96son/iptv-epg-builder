from src.channel_time_offsets import load_channel_time_offsets, channel_time_offset_minutes
from src.utils import shift_xmltv_timestamp

def test_openbox_cps_family_shift_plus_two_hours():
    load_channel_time_offsets.cache_clear()
    assert channel_time_offset_minutes("openbox-tsd","cps-ussr") == 120
    assert channel_time_offset_minutes("openbox-tsd","cps-drama") == 120
    assert channel_time_offset_minutes("openbox-tsd","cps-comedy") == 120

def test_non_cps_unchanged():
    load_channel_time_offsets.cache_clear()
    assert channel_time_offset_minutes("openbox-tsd","mm-ussr-drama") == 0
    assert channel_time_offset_minutes("runigma","cps-ussr") == 0

def test_plus_two_hours_rollover():
    assert shift_xmltv_timestamp("20260821233000 -0700",120) == "20260822013000 -0700"
