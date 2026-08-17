from __future__ import annotations

import re

# IPTV.online provider groups are the best available region/country signal.
# Keep this table explicit: if a provider adds a new group, it remains UNKNOWN
# until reviewed instead of silently being mapped to the wrong regional feed.
GROUP_REGIONS = {
    "Россия": "RU",
    "Украинские": "UA",
    "Беларусь": "BY",
    "Германия": "DE",
    "UK": "GB",
    "Великобритания": "GB",
    "Канада": "CA",
    "США": "US",
    "Италия": "IT",
    "Румыния": "RO",
    "Болгария": "BG",
    "Израиль": "IL",
    "BE & NL": "BE/NL",
    "BE/NL": "BE/NL",
    "Польша": "PL",
    "Венгрия": "HU",
    "Чехия": "CZ",
    "Словакия": "SK",
    "SkyLink": "CZ/SK",
    "Греция": "GR",
    "Турция": "TR",
    "Хорватия": "HR",
    "Литва": "LT",
    "Латвия": "LV",
    "Молдова": "MD",
    "Грузия": "GE",
    "Армения": "AM",
    "Азербайджан": "AZ",
}

# Global brands frequently have regional schedules. For these, automatic
# display-name matching is allowed only when the XMLTV source declares a
# compatible region. Manual aliases can still override this after verification.
REGIONAL_SENSITIVE_BRANDS = (
    "discovery", "tlc", "animal planet", "national geographic", "nat geo", "ngc",
    "eurosport", "viasat", "hbo", "nickelodeon", "nick jr", "disney", "mtv",
    "fox", "star", "bbc", "itv", "rai", "rtl", "bein", "cinemax", "paramount",
    "history", "travel channel", "food network", "cartoon network", "cnn",
    "tv1000", "canal+", "sky", "digi", "nova", "sport tv", "dazn",
)


def region_for_group(group: str) -> str:
    return GROUP_REGIONS.get((group or "").strip(), "")


def is_regional_sensitive(name: str) -> bool:
    value = re.sub(r"\s+", " ", (name or "").lower()).strip()
    return any(brand in value for brand in REGIONAL_SENSITIVE_BRANDS)


def regions_compatible(channel_region: str, source_regions: list[str] | tuple[str, ...] | set[str]) -> bool:
    if not channel_region:
        return False
    normalized = {str(r).strip().upper() for r in (source_regions or []) if str(r).strip()}
    cr = channel_region.upper()
    if cr in normalized:
        return True
    # Composite provider groups are ambiguous. A BE-only or NL-only feed must
    # not be selected automatically for a regional-sensitive brand.
    if cr == "BE/NL":
        return "BE/NL" in normalized
    if cr == "CZ/SK":
        return "CZ/SK" in normalized
    return False
