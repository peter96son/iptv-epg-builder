import src.metadata_quality_patch  # noqa: F401
import src.title_normalization_patch  # noqa: F401
import src.year_safe_metadata_patch  # noqa: F401
import src.v15_policy_patch  # noqa: F401
import src.horizon_guard_patch  # noqa: F401
import src.excluded_groups_patch  # noqa: F401
from src.builder import build
import src.source_reselector as _source_reselector
from src.source_evidence import install as install_source_evidence

install_source_evidence(_source_reselector)

from src.source_reselector import reselect_policy_sources
from src.source_catalog import snapshot_missing_source_catalog
from src.verified_metadata_fixes import apply_verified_metadata_fixes

if __name__ == "__main__":
    # Per-run cache is never reused between workflow executions.
    import os
    import tempfile
    with tempfile.TemporaryDirectory(prefix='epg-source-reuse-') as shared:
        os.environ['EPG_RECOVERY_SOURCE_CACHE'] = shared
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
    # Stage 1b: still-valid live OCR observations are applied by the single EPG
    # publisher. Any problem here must never fail the main build.
    try:
        from src.live_ocr_current_epg import apply_state as apply_live_ocr_state
        ocr = apply_live_ocr_state()
        print(
            f"[live-ocr] applied={ocr.get('applied', 0)}; expired={ocr.get('expired', 0)}; "
            f"skipped_real={ocr.get('skipped_real_programme', 0)}; invalid={ocr.get('invalid', 0)}"
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[live-ocr] skipped after error: {exc!r}")
