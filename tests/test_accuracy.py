from src.accuracy import infer_id_region, assess_mapping


def test_infer_country_suffix():
    assert infer_id_region("XZoom.il") == "IL"
    assert infer_id_region("SPORT.TV1.HD.pt") == "PT"
    assert infer_id_region("Xsomething") == ""


def test_country_conflict_is_quarantined():
    result = assess_mapping({
        "playlist_name": "Zoom",
        "region": "UA",
        "source_id": "XZoom.il",
        "output_tvg_id": "XZoom.il",
        "source": "example",
        "method": "id",
        "confidence": 99,
    })
    assert result["accuracy_status"] == "wrong"
    assert result["quarantine"] is True


def test_strong_exact_without_conflict_is_probable():
    result = assess_mapping({
        "playlist_name": "НТВ",
        "region": "RU",
        "source_id": "Xntv",
        "output_tvg_id": "Xntv",
        "source": "primary",
        "method": "id",
        "confidence": 99,
    })
    assert result["accuracy_status"] == "probable"
    assert result["quarantine"] is False


def test_synthetic_schedule_is_quarantined():
    result = assess_mapping({
        "playlist_name": "DITV Карпов",
        "region": "",
        "source_id": "ditv-karpov",
        "output_tvg_id": "ditv-karpov",
        "source": "ditv-local-fallback",
        "method": "synthetic-ditv",
        "confidence": 10,
    })
    assert result["quarantine"] is True


def test_builder_does_not_publish_synthetic_ditv_fallback():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    text = (root / "src" / "builder.py").read_text(encoding="utf-8")
    assert "build_ditv_fallback(" not in text
    assert '"ditv_fallback_mode": "disabled-real-epg-only"' in text
