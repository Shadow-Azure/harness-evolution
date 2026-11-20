"""Persist target bindings, restartable analysis intent, and report provenance."""

import sqlalchemy as sa

from alembic import op

revision = "0029"
down_revision = "0028"


def upgrade() -> None:
    db = op.get_bind()
    metadata = sa.MetaData()
    for table, fields in {
        "evolution_targets": {
            "attribution_package_id": sa.String(64),
            "attribution_skill_name": sa.String(128),
            "attribution_generation": sa.String(36),
            "attribution_owner": sa.String(36),
            "attribution_snapshot": sa.JSON(),
            "attribution_due": sa.DateTime(timezone=True),
            "attribution_cutoff": sa.DateTime(timezone=True),
        },
        "probe_reports": {
            "attribution_skill_name": sa.String(128),
            "binding_generation": sa.String(36),
            "analyzed_at": sa.DateTime(timezone=True),
        },
    }.items():
        if not sa.inspect(db).has_table(table):
            continue
        existing = {c["name"] for c in sa.inspect(db).get_columns(table)}
        for name, typ in fields.items():
            if name not in existing:
                op.add_column(table, sa.Column(name, typ, nullable=True))
    t, b, r, p, w, skills = [
        sa.Table(name, metadata, autoload_with=db)
        for name in (
            "evolution_targets",
            "attribution_skill_bindings",
            "attribution_skill_revisions",
            "attribution_skill_packages",
            "attribution_skill_package_bindings",
            "attribution_skills",
        )
    ]
    for row in db.execute(sa.select(t.c.id, t.c.workspace_id)).all():
        binding = db.execute(
            sa.select(r.c.content, skills.c.skill_key)
            .select_from(
                b.join(r, b.c.skill_revision_id == r.c.id).join(skills, r.c.skill_id == skills.c.id)
            )
            .where(b.c.target_id == row.id, b.c.workspace_id == row.workspace_id)
        ).one_or_none()
        content = binding.content if binding else None
        if (
            binding
            and content
            and isinstance(content.get("instructions"), str)
            and "packageId" not in content
        ):
            db.execute(
                t.update().where(t.c.id == row.id).values(attribution_skill_name=binding.skill_key)
            )
            continue
        pid = (
            content.get("packageId")
            if content
            else db.execute(
                sa.select(w.c.package_id).where(w.c.workspace_id == row.workspace_id)
            ).scalar_one_or_none()
        )
        name = db.execute(
            sa.select(p.c.skill_name).where(p.c.workspace_id == row.workspace_id, p.c.id == pid)
        ).scalar_one_or_none()
        db.execute(
            t.update()
            .where(t.c.id == row.id)
            .values(
                attribution_package_id=pid if name else "default-attribute-badcases",
                attribution_skill_name=name or "attribute-badcases",
            )
        )
    if not sa.inspect(db).has_table("probe_reports"):
        return
    reports = sa.Table("probe_reports", metadata, autoload_with=db)
    db.execute(
        reports.update().values(
            analyzed_at=reports.c.created_at,
            attribution_skill_name=reports.c.execution_manifest["skill"]["key"].as_string(),
        )
    )


def downgrade() -> None:
    for table, fields in (
        ("probe_reports", ["attribution_skill_name", "binding_generation", "analyzed_at"]),
        (
            "evolution_targets",
            [
                "attribution_package_id",
                "attribution_skill_name",
                "attribution_generation",
                "attribution_due",
                "attribution_owner",
                "attribution_snapshot",
                "attribution_cutoff",
            ],
        ),
    ):
        if not sa.inspect(op.get_bind()).has_table(table):
            continue
        for name in fields:
            op.drop_column(table, name)
