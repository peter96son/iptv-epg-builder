v15.1 — real source selection

Root cause fixed:
The generic builder is first-match-wins. A channel can be claimed by an early
source with only a short remaining schedule, preventing later sources with a
much longer guide from ever being considered.

v15.1 adds a deterministic source-selection phase for every channel listed in
data/source_policy_v15.csv:
- downloads every allowed policy source;
- evaluates the exact policy source_id in every source;
- measures usable programmes and last-stop horizon;
- chooses the first policy source with >= EPG_POLICY_TARGET_HOURS (default 6h);
- if all live candidates are shorter, chooses the one with the longest positive horizon;
- replaces the original first-match schedule in epg.xml.gz;
- updates mapping.csv and uhf-mapping.json;
- reapplies local SQLite metadata;
- writes output/source-selection-v15.json with all candidates and the winner.

This is source selection, not another horizon threshold patch.
