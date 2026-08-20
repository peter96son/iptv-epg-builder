import xml.etree.ElementTree as ET
from pathlib import Path

from src import metadata_enrichment as me
from src.metadata_db import MetadataDB, SCHEMA_VERSION


def p():
    root=ET.Element("programme",{"channel":"c1"})
    ET.SubElement(root,"title",{"lang":"ru"}).text="Матрица"
    return root


def test_tmdb_image_url():
    assert me._tmdb_image_url("/poster.jpg","w500") == \
        "https://image.tmdb.org/t/p/w500/poster.jpg"
    assert me._tmdb_image_url("","w500") == ""


def test_artwork_fields_from_tmdb_payload():
    out=me._tmdb_artwork_fields({
        "poster_path":"/poster.jpg",
        "backdrop_path":"/backdrop.jpg",
    })
    assert out["poster_url"].endswith("/w500/poster.jpg")
    assert out["backdrop_url"].endswith("/w780/backdrop.jpg")


def test_programme_gets_compat_icon_and_rich_images():
    node=p()
    me._add_metadata(
        node,"8.7","tt0133093","2200000",
        overview="Описание",genres=["фантастика"],
        poster_url="https://image.tmdb.org/t/p/w500/p.jpg",
        backdrop_url="https://image.tmdb.org/t/p/w780/b.jpg",
    )
    icon=node.find("icon")
    assert icon is not None
    assert icon.get("src").endswith("/w500/p.jpg")

    poster=node.find("image[@type='poster']")
    backdrop=node.find("image[@type='backdrop']")
    assert poster is not None and poster.text.endswith("/w500/p.jpg")
    assert poster.get("orient")=="P"
    assert backdrop is not None and backdrop.text.endswith("/w780/b.jpg")
    assert backdrop.get("orient")=="L"


def test_existing_programme_icon_is_not_replaced():
    node=p()
    ET.SubElement(node,"icon",{"src":"https://provider.example/original.jpg"})
    me._add_metadata(
        node,"","","",
        poster_url="https://image.tmdb.org/t/p/w500/p.jpg",
    )
    assert node.find("icon").get("src")=="https://provider.example/original.jpg"
    assert node.find("image[@type='poster']") is not None


def test_artwork_render_is_idempotent():
    node=p()
    kwargs=dict(
        poster_url="https://image.tmdb.org/t/p/w500/p.jpg",
        backdrop_url="https://image.tmdb.org/t/p/w780/b.jpg",
    )
    me._add_metadata(node,"","","",**kwargs)
    me._add_metadata(node,"","","",**kwargs)
    assert len(node.findall("icon"))==1
    assert len(node.findall("image[@type='poster']"))==1
    assert len(node.findall("image[@type='backdrop']"))==1


def test_artwork_persists_in_knowledge_db(tmp_path: Path):
    db=MetadataDB(tmp_path/"m.sqlite3")
    try:
        db.put_title("Матрица","1999","movie","ru-RU",{
            "status":"found",
            "imdb_id":"tt0133093",
            "tmdb_id":603,
            "title":"Матрица",
            "resolved_media_type":"movie",
            "poster_url":"https://image.tmdb.org/t/p/w500/p.jpg",
            "backdrop_url":"https://image.tmdb.org/t/p/w780/b.jpg",
        })
        row=db.conn.execute(
            "SELECT t.id,m.poster_url,m.backdrop_url "
            "FROM titles t JOIN metadata m ON m.title_id=t.id "
            "WHERE t.imdb_id='tt0133093'"
        ).fetchone()
        assert row["poster_url"].endswith("/w500/p.jpg")
        assert row["backdrop_url"].endswith("/w780/b.jpg")
        assert SCHEMA_VERSION==7
        assert db.get_stat("programme_artwork")=="tmdb-poster-backdrop-v13-stage6"
    finally:
        db.close()
