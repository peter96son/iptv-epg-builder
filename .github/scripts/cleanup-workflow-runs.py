from __future__ import annotations
import json, os, sys, urllib.request, urllib.error

repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
token = os.environ.get("GITHUB_TOKEN", "").strip()
current = str(os.environ.get("GITHUB_RUN_ID", "")).strip()
keep = max(5, int(os.environ.get("WORKFLOW_RUNS_KEEP", "20")))

if not repo or not token:
    print("[cleanup-runs] missing GitHub context; skip")
    raise SystemExit(0)

headers = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "iptv-epg-builder-cleanup",
}

def request(url, method="GET"):
    req = urllib.request.Request(url, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        if r.status == 204:
            return None
        return json.loads(r.read().decode("utf-8"))

base = f"https://api.github.com/repos/{repo}"
workflows = request(base + "/actions/workflows?per_page=100").get("workflows", [])
deleted = 0

for wf in workflows:
    wid = wf.get("id")
    name = wf.get("name") or str(wid)
    if not wid:
        continue
    runs = []
    page = 1
    while page <= 10:
        data = request(
            f"{base}/actions/workflows/{wid}/runs?status=completed&per_page=100&page={page}"
        )
        batch = data.get("workflow_runs", [])
        runs.extend(batch)
        if len(batch) < 100:
            break
        page += 1

    # GitHub returns newest first. Preserve the newest N completed runs and
    # never delete the currently executing run if it appears unexpectedly.
    victims = [r for r in runs[keep:] if str(r.get("id")) != current]
    for run in victims:
        rid = run.get("id")
        if not rid:
            continue
        try:
            request(f"{base}/actions/runs/{rid}", "DELETE")
            deleted += 1
        except urllib.error.HTTPError as exc:
            # Cleanup must never fail a healthy EPG build.
            print(f"[cleanup-runs] {name} run {rid}: HTTP {exc.code}; continue")

print(f"[cleanup-runs] kept={keep} per workflow; deleted={deleted}")
