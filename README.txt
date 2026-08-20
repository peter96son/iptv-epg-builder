EPG channel fixes

Replace data/tvg_id_fixes.csv with the included file.
Optionally copy tests/test_verified_schedule_fixes.py.

Then run the normal Update EPG workflow.

What this does:
- Forces Premiere-group-like movie channels away from generic X... ids to dedicated t-s-d/Openbox ids.
- Forces KLI USSR to Runigma's dedicated kli-sssr-hd id.
- Forces Russian 'Наше любимое кино' away from the Ukrainian schedule.

CPS USSR is intentionally not remapped here because its dedicated source id is already cps-ussr; its problem is not an id collision and needs a separate timing/source investigation.
