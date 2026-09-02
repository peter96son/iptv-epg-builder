v15.6 — remove unwanted country categories

Requested groups removed:
- Турция
- Азербайджан
- Венгрия
- Хорватия
- Армения
- Греция
- Румыния

Integration:
1. data/playlist_rules.json adds the groups to exclude_groups. The existing
   Cloudflare Worker already removes any group in exclude_groups from the
   delivered UHF/UniPlayer playlist.
2. src/excluded_groups_patch.py is imported before src.builder and filters the
   same groups before EPG matching/source selection.
3. The previous playlist snapshot is filtered by the same rule set before
   collapse-protection comparison, preventing a false "playlist collapsed"
   safety stop caused by intentional removals.
4. movie_epg_audit already honors playlist_rules exclude_groups, so these
   countries do not appear in movie gaps/diagnostics.

No changes to source pins, aliases, Premiere/4ever selection, or metadata.
