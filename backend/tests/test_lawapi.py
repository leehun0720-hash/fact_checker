from app.lawapi import _six, _flatten_article


def test_article_number_formats():
    assert _six("14") == "001400"
    assert _six("제14조") == "001400"
    assert _six("10의2") == "001002"
    assert _six("제10조의2") == "001002"
    assert _six("제2항") == "000200"


def test_flatten_nested_article():
    unit = {"조문내용": "제2조(정의)", "항": {"호": [{"호내용": " 1. 정보란 ", "목": [{"목내용": "가. 전자적"}]}, {"호내용": "2. 정보화란"}]}}
    text = _flatten_article(unit)
    assert text.splitlines() == ["제2조(정의)", "1. 정보란", "가. 전자적", "2. 정보화란"]
