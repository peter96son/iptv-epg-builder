import json

def test_safe_mapping_shape():
    payload = {
        "generated_at": "2026-08-16T20:00:00-07:00",
        "epg_url": "https://example/epg.xml.gz",
        "channels": {"Magic Horror": "magic-horror"},
    }
    encoded = json.dumps(payload)
    assert "stream_url" not in encoded
    assert "/play/" not in encoded
