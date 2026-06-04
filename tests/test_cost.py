import ast

from pytest_select.score.cost import score_file_cost


def test_expensive_import_raises_cost():
    tree = ast.parse("import requests\nimport boto3\n")
    assert score_file_cost(tree) > 10
