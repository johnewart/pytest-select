from app.service import run


def test_run():
    assert run("bob") == "hello bob"
