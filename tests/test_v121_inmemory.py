import xml.etree.ElementTree as ET
from src.metadata_backfill import build_queue
def test_queue_from_in_memory_tree():
    tv=ET.Element("tv")
    p=ET.SubElement(tv,"programme",{"channel":"c1"})
    ET.SubElement(p,"title",{"lang":"ru"}).text="х/ф Матрица"
    q=build_queue(tv,[{"output_tvg_id":"c1","group":"Кино"}])
    assert len(q)==1 and q[0]["title"]=="Матрица"
