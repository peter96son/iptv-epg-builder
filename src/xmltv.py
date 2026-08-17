from __future__ import annotations
import xml.etree.ElementTree as ET
from collections import defaultdict
from copy import deepcopy
from .utils import open_xml_bytes, normalize_name, xmltv_date_is_fresh

class XMLTVSource:
    def __init__(self, name: str, data: bytes):
        self.name = name
        self.data = data
        self.channels = {}
        self.names = defaultdict(set)
        self.live_ids = set()

    def index(self):
        f = open_xml_bytes(self.data)
        for _, elem in ET.iterparse(f, events=("end",)):
            tag = elem.tag.split("}")[-1]
            if tag == "channel":
                cid = elem.get("id", "")
                if cid:
                    self.channels[cid] = deepcopy(elem)
                    for dn in elem.findall("display-name"):
                        if dn.text:
                            n = normalize_name(dn.text)
                            if n:
                                self.names[n].add(cid)
                elem.clear()
            elif tag == "programme":
                if xmltv_date_is_fresh(elem.get("start", "")):
                    self.live_ids.add(elem.get("channel", ""))
                elem.clear()
        f.close()
        self.channels = {k: v for k, v in self.channels.items() if k in self.live_ids}
        self.names = {k: (v & self.live_ids) for k, v in self.names.items() if v & self.live_ids}
        return self

    def fresh_programmes(self, wanted_ids: set[str], past_days=7, future_days=21):
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
