from app.ml_module import analyze


def test_analyze():
    assert analyze("data") == "data"
