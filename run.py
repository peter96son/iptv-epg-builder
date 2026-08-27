import src.metadata_quality_patch  # noqa: F401
import src.title_normalization_patch  # noqa: F401
import src.year_safe_metadata_patch  # noqa: F401
import src.horizon_guard_patch  # noqa: F401
from src.builder import build
from src.verified_metadata_fixes import apply_verified_metadata_fixes

if __name__ == "__main__":
    build()
    result = apply_verified_metadata_fixes()
    print(
        f"[verified-metadata] changed={result.get('changed', 0)}; "
        f"normalized_titles={result.get('normalized_titles', 0)}"
    )
