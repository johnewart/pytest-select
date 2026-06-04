from app.util import greet


def test_greet():
    assert greet("world") == "hello world"
