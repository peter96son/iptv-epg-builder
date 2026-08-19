from pathlib import Path
def test_single_xml_write_pipeline():
    wf=Path(".github/workflows/update.yml").read_text(encoding="utf-8")
    builder=Path("src/builder.py").read_text(encoding="utf-8")
    assert "run: python run.py" in wf
    assert "python -m src.metadata_backfill" not in wf
    assert "python -m src.apply_metadata_to_epg" not in wf
    assert builder.index("backfill_tree(tv,mappings") < builder.index('tmp = OUTPUT / "epg.xml"')
