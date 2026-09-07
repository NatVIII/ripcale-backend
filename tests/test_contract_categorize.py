"""Categorize contract compliance tests.

The categorize contract lives in `docs/CATEGORIZE_CONTRACT.md` (the source of
truth). These tests assert the code's declared version matches the doc and that
the rule shape + matchable fields match the documentation.
"""
#region: imports
from app.categorize.categorize import CONTRACT_VERSION, TEXT_FIELDS
from app.schema import CategoryRule

from contract_helpers import read_contract_version
#endregion


#region: version + shapes
def test_categorize_version_matches_doc():
    assert CONTRACT_VERSION == read_contract_version("CATEGORIZE_CONTRACT.md")


def test_category_rule_fields_match_doc():
    assert set(CategoryRule.model_fields) == {
        "mode", "fields", "regex", "categories",
    }


def test_text_fields_match_doc():
    assert set(TEXT_FIELDS) == {"uid", "title", "description", "location", "url"}
#endregion
