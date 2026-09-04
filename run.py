import src.metadata_quality_patch  # noqa: F401
import src.title_normalization_patch  # noqa: F401
import src.year_safe_metadata_patch  # noqa: F401
import src.v15_policy_patch  # noqa: F401
import src.horizon_guard_patch  # noqa: F401
import src.excluded_groups_patch  # noqa: F401
import src.live_verified_source_pins_patch  # noqa: F401
from src.builder import build
from src.source_reselector import reselect_policy_sources
from src.source_catalog import snapshot_missing_source_catalog
from src.verified_metadata_fixes import apply_verified_metadata_fixes
from src.live_ocr_epg_overlay import run as apply_live_ocr_epg_overlay

if __name__ == "__main__":
    build()
    selection = reselect_policy_sources()
    print(
        f"[source-selection] selected={selection.get('selected', 0)}; "
        f"changed={selection.get('changed', 0)}"
    )
    catalog = snapshot_missing_source_catalog()
    print(
        f"[source-catalog] sources={catalog.get('sources', 0)}; "
        f"channels={catalog.get('channels', 0)}"
    )
    result = apply_verified_metadata_fixes()
    print(
        f"[verified-metadata] changed={result.get('changed', 0)}; "
        f"normalized_titles={result.get('normalized_titles', 0)}"
    )
    ocr_overlay = apply_live_ocr_epg_overlay(consume_probe=False)
    print(
        f"[live-ocr-epg] active={ocr_overlay.get('overlay',{}).get('active',0)}; "
        f"applied={ocr_overlay.get('overlay',{}).get('applied',0)}"
    )
