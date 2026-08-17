from __future__ import annotations
import xml.etree.ElementTree as ET
from collections import defaultdict
from copy import deepcopy
from .utils import open_xml_bytes, normalize_name, xmltv_date_is_fresh, xmltv_programme_is_usable


class XMLTVSource:
    """Indexed XMLTV source.

    v1.9 deliberately distinguishes "date-fresh" data from a schedule that is
    actually usable by a player now.  A source channel is exposed to Matcher
    only when it has at least one programme that is current or starts soon.
    This prevents channels from being counted as covered merely because the
    feed still contains yesterday's entries.
    """

    def __init__(self, name: str, data: bytes):
        self.name = name
        self.data = data
        self.channels = {}
        self.names = defaultdict(set)
        self.live_ids = set()
        self.usable_ids = set()

    def index(self):
        all_channels = {}
        all_names = defaultdict(set)

        f = open_xml_bytes(self.data)
        for _, elem in ET.iterparse(f, events=("end",)):
            tag = elem.tag.split("}")[-1]
            if tag == "channel":
                cid = elem.get("id", "")
                if cid:
                    all_channels[cid] = deepcopy(elem)
                    for dn in elem.findall("display-name"):
                        if dn.text:
                            n = normalize_name(dn.text)
                            if n:
                                all_names[n].add(cid)
                elem.clear()
            elif tag == "programme":
                cid = elem.get("channel", "")
                if cid and xmltv_date_is_fresh(elem.get("start", "")):
                    self.live_ids.add(cid)
                if cid and xmltv_programme_is_usable(elem.get("start", ""), elem.get("stop", "")):
                    self.usable_ids.add(cid)
                elem.clear()
        f.close()

        # Matching is based on actual current/upcoming usability, not only a
        # broad calendar-date freshness check.
        self.channels = {k: v for k, v in all_channels.items() if k in self.usable_ids}
        self.names = {
            k: (v & self.usable_ids)
            for k, v in all_names.items()
            if v & self.usable_ids
        }
        return self

    def fresh_programmes(self, wanted_ids: set[str], past_days=2, future_days=21):
        f = open_xml_bytes(self.data)
        try:
            for _, elem in ET.iterparse(f, events=("end",)):
                if elem.tag.split("}")[-1] == "programme":
                    cid = elem.get("channel", "")
                    if cid in wanted_ids and xmltv_date_is_fresh(elem.get("start", ""), past_days, future_days):
                        yield deepcopy(elem)
                    elem.clear()
        finally:
            f.close()
