import src.metadata_quality_patch  # noqa: F401
from src.builder import build
from src.verified_metadata_fixes import apply_verified_metadata_fixes

if __name__ == "__main__":
    build()
    result = apply_verified_metadata_fixes()
    print(f"[verified-metadata] changed={result.get('changed', 0)}")
