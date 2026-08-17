from __future__ import annotations
from pathlib import Path
from html import escape

def build_markdown(status: dict, changes: dict, history: list[dict]) -> str:
    lines = []
    lines.append("# IPTV EPG Dashboard")
    lines.append("")
    lines.append(f"- Generated: `{status.get('generated_at','')}`")
    lines.append(f"- Playlist channels: **{status.get('playlist_channels',0)}**")
    lines.append(f"- Baseline covered: **{status.get('baseline_matched_channels',0)}**")
    lines.append(f"- Final covered: **{status.get('final_matched_channels',0)}**")
    lines.append(f"- Added by fallbacks: **+{status.get('added_by_fallback_channels',0)}**")
    lines.append(f"- Unmatched: **{status.get('unmatched_channels',0)}**")
    lines.append(f"- Programmes: **{status.get('programmes',0)}**")
    mp = status.get("movie_priority", {})
    if mp:
        lines.append(f"- Movie coverage: **{mp.get('final',0)}/{sum(status.get('group_totals',{}).get(g,0) for g in mp.get('groups',[]))}** (+{mp.get('added',0)})")
    lines.append("")
    lines.append("## Playlist changes")
    lines.append("")
    for label, key in [
        ("New channels", "added_count"),
        ("Removed channels", "removed_count"),
        ("Renamed", "renamed_count"),
        ("Stream URL changed", "stream_url_changed_count"),
        ("Category changed", "group_changed_count"),
    ]:
        lines.append(f"- {label}: **{changes.get(key,0)}**")
    lines.append("")
    lines.append("## Coverage by group")
    lines.append("")
    lines.append("| Group | Total | Baseline | Final | Added | Coverage |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    coverage = status.get("group_coverage", {})
    for group, row in sorted(coverage.items(), key=lambda kv: (-kv[1].get("added",0), kv[0])):
        lines.append(f"| {group} | {row.get('total',0)} | {row.get('baseline',0)} | {row.get('final',0)} | +{row.get('added',0)} | {row.get('final_pct',0)}% |")
    lines.append("")
    lines.append("## Source contribution")
    lines.append("")
    lines.append("| Source | Status | Added |")
    lines.append("|---|---|---:|")
    for row in status.get("sources", []):
        lines.append(f"| {row.get('source','')} | {row.get('status','')} | {row.get('matched',0)} |")
    lines.append("")
    lines.append("## Recent history")
    lines.append("")
    lines.append("| Generated | Covered | Unmatched | Programmes |")
    lines.append("|---|---:|---:|---:|")
    for h in history[-20:]:
        lines.append(f"| {h.get('generated_at','')} | {h.get('final_matched_channels',0)} | {h.get('unmatched_channels',0)} | {h.get('programmes',0)} |")
    lines.append("")
    return "\n".join(lines) + "\n"

def build_html(status: dict, changes: dict, history: list[dict]) -> str:
    rows = []
    for group, row in sorted(status.get("group_coverage", {}).items(), key=lambda kv: (-kv[1].get("added",0), kv[0])):
        rows.append(
            f"<tr><td>{escape(group)}</td><td>{row.get('total',0)}</td><td>{row.get('baseline',0)}</td>"
            f"<td>{row.get('final',0)}</td><td>+{row.get('added',0)}</td><td>{row.get('final_pct',0)}%</td></tr>"
        )
    src_rows = []
    for s in status.get("sources", []):
        src_rows.append(f"<tr><td>{escape(s.get('source',''))}</td><td>{escape(s.get('status',''))}</td><td>{s.get('matched',0)}</td></tr>")
    hist_rows = []
    for h in history[-20:]:
        hist_rows.append(f"<tr><td>{escape(h.get('generated_at',''))}</td><td>{h.get('final_matched_channels',0)}</td><td>{h.get('unmatched_channels',0)}</td><td>{h.get('programmes',0)}</td></tr>")

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>IPTV EPG Dashboard</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Arial,sans-serif;max-width:1100px;margin:30px auto;padding:0 16px;line-height:1.4}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:18px 0}}
.card{{border:1px solid #ddd;border-radius:10px;padding:14px}} .big{{font-size:28px;font-weight:700}}
table{{border-collapse:collapse;width:100%;margin:12px 0 28px}} th,td{{border-bottom:1px solid #ddd;padding:8px;text-align:left}}
th{{position:sticky;top:0;background:white}} code{{word-break:break-all}}
</style></head>
<body>
<h1>IPTV EPG Dashboard</h1>
<p>Generated: <code>{escape(status.get('generated_at',''))}</code></p>
<div class="cards">
<div class="card"><div>Channels</div><div class="big">{status.get('playlist_channels',0)}</div></div>
<div class="card"><div>Covered</div><div class="big">{status.get('final_matched_channels',0)}</div></div>
<div class="card"><div>Fallback gain</div><div class="big">+{status.get('added_by_fallback_channels',0)}</div></div>
<div class="card"><div>Unmatched</div><div class="big">{status.get('unmatched_channels',0)}</div></div>
<div class="card"><div>Programmes</div><div class="big">{status.get('programmes',0)}</div></div>
</div>

<h2>Playlist changes</h2>
<ul>
<li>New: <b>{changes.get('added_count',0)}</b></li>
<li>Removed: <b>{changes.get('removed_count',0)}</b></li>
<li>Renamed: <b>{changes.get('renamed_count',0)}</b></li>
<li>Stream URL changes: <b>{changes.get('stream_url_changed_count',0)}</b></li>
<li>Category changes: <b>{changes.get('group_changed_count',0)}</b></li>
</ul>

<h2>Coverage by group</h2>
<table><tr><th>Group</th><th>Total</th><th>Baseline</th><th>Final</th><th>Added</th><th>Coverage</th></tr>
{''.join(rows)}</table>

<h2>Source contribution</h2>
<table><tr><th>Source</th><th>Status</th><th>Added</th></tr>{''.join(src_rows)}</table>

<h2>Recent history</h2>
<table><tr><th>Generated</th><th>Covered</th><th>Unmatched</th><th>Programmes</th></tr>{''.join(hist_rows)}</table>
</body></html>"""
