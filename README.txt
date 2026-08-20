EPG source pin fix

Replace/add these files preserving paths:
  src/config.py
  src/matcher.py
  data/source_pins.csv
  data/tvg_id_fixes.csv
  tests/test_source_pins.py

Why:
1) Existing tvg_id_fixes.csv used playlist_name, but config.py did not read it.
2) A tvg-id override alone cannot force a source. An earlier EPG source can still steal the channel.
3) source_pins.csv adds hard_pin=1. Matcher rejects all other sources BEFORE exact-id matching.

CPS USSR is NOT hard-pinned here because its issue was not yet isolated to a specific source;
existing aliases can continue to try Runigma/Openbox in normal order.

After replacement:
  python -m pytest -q
  python run.py
Then inspect output/mapping.csv: affected channels should show the pinned source/source_id.
