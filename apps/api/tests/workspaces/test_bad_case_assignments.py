"""Published SQLAlchemy tables for workspace badcase assignment."""

from app.db.models.domain import DOMAIN_METADATA, bad_cases


def test_domain_metadata_declares_workspace_assignment_tables() -> None:
    """Fixture bootstrap includes both rule and assignment relations."""
    labels = DOMAIN_METADATA.tables["workspace_bad_case_labels"]
    assignments = DOMAIN_METADATA.tables["workspace_bad_cases"]

    assert "catalog_label" in bad_cases.c
    assert tuple(labels.primary_key.columns.keys()) == ("workspace_id", "label")
    assert tuple(assignments.primary_key.columns.keys()) == (
        "workspace_id",
        "bad_case_id",
        "assignment_source",
    )
    assert assignments.c.bad_case_id.references(bad_cases.c.bad_case_id)
