import xml.etree.ElementTree as ET
import src.v14_policy_patch  # noqa: F401
from src import metadata_enrichment as me
from src.channel_family import family_candidates

def p(title):
    e=ET.Element("programme")
    t=ET.SubElement(e,"title"); t.text=title
    return e

def test_series_episode_suffixes():
    assert me._media_type(p("Мамочки. 13 с"),"Кино")=="series"
    assert me._clean_search_title("Мамочки. 13 с")=="Мамочки"
    assert me._media_type(p("Секретные материалы Сезон 08"),"Кино")=="series"

def test_known_parenthetical_animation():
    assert me._media_type(p("Три кота (Картинная галерея)"),"Детские")=="series"
    assert me._clean_search_title("Три кота (Картинная галерея)")=="Три кота"
    assert me._clean_search_title("Простоквашино (Неудобные соседи)")=="Простоквашино"

def test_movie_year_not_series():
    assert me._media_type(p("Веном (2018)"),"Кино")=="movie"

def test_hd_not_stripped_from_channel_family():
    assert family_candidates("Наш Кинопоказ HD","RU")[0]
    assert "наш кинопоказ" not in family_candidates("Наш Кинопоказ HD","RU")[1:]
