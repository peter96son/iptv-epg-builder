from types import SimpleNamespace
import json

import src.excluded_groups_patch as p


def test_requested_country_groups_are_excluded():
    excluded=p._excluded_groups()
    assert {
        "Турция","Азербайджан","Венгрия","Хорватия",
        "Армения","Греция","Румыния"
    } <= excluded


def test_channel_filter_removes_only_excluded_groups():
    rows=[
        SimpleNamespace(name="TRT",group="Турция"),
        SimpleNamespace(name="AzTV",group="Азербайджан"),
        SimpleNamespace(name="Россия 1",group="Россия"),
        SimpleNamespace(name="BBC",group="UK"),
    ]
    kept=p._filter_channels(rows)
    assert [x.name for x in kept]==["Россия 1","BBC"]


def test_snapshot_filter_uses_same_group_policy(monkeypatch,tmp_path):
    monkeypatch.setattr(
        p,"_ORIGINAL_STATE_LOAD_JSON",
        lambda path,default:[
            {"name":"TRT","group":"Турция"},
            {"name":"Россия 1","group":"Россия"},
        ],
    )
    got=p.load_state_json_filtered(tmp_path/"playlist-snapshot.json",[])
    assert got==[{"name":"Россия 1","group":"Россия"}]
