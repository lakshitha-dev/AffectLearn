"""Every model table must have a migration that creates it.

This exists because `learner_profiles` did not, and nothing caught it. The `LearnerProfile` model
shipped, the profiler used it, and production ran for weeks with the table absent — `alembic_version`
stuck at 019 while the model expected a table nobody had ever created.

It was invisible because the Learner Profiler degrades instead of failing: both cold-store calls sit
in bare `except` blocks, so every load and every persist raised `UndefinedTableError`, logged a
warning, and the cycle continued. Profile load `source` was 100% `redis` across 400 consecutive
production cycles — meaning a Redis eviction would have silently destroyed a participant's entire
affect history, with no error anywhere.

A unit test cannot catch a missing table (the test suite builds its schema from `Base.metadata`, which
is exactly why the gap survived). Comparing the model registry against the migration files can.
"""

from __future__ import annotations

import glob
import os
import re

import importlib
import pkgutil

from app.models.base import Base


def _register_all_models() -> None:
    """Import EVERY module in `app.models` so `Base.metadata` is complete.

    Deliberately walks the package rather than relying on `app.models.__init__`. That __init__ is
    exactly how the original bug survived: it never imported `learner_profile`, so the table was
    absent from `Base.metadata`, so alembic autogenerate could not have generated a migration for
    it even if someone had run it. A check that trusts the same incomplete registry would pass
    while testing nothing — the first version of this file did precisely that.
    """
    import app.models as models_pkg

    for info in pkgutil.iter_modules(models_pkg.__path__):
        importlib.import_module(f"{models_pkg.__name__}.{info.name}")


_register_all_models()


def _tables_created_by_migrations() -> set[str]:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sql = "\n".join(
        open(path, encoding="utf-8").read()
        for path in glob.glob(os.path.join(here, "alembic", "versions", "*.py"))
    )
    # Matches both op.create_table("x", ...) and op.rename_table(..., "x").
    return set(re.findall(r'create_table\(\s*["\']([a-z_]+)["\']', sql)) | set(
        re.findall(r'rename_table\([^)]*?["\']([a-z_]+)["\']\s*\)', sql)
    )


def test_every_model_table_has_a_creating_migration():
    created = _tables_created_by_migrations()
    missing = sorted(t for t in Base.metadata.tables if t not in created)
    assert not missing, (
        f"model tables with no migration: {missing}. "
        "Production would raise UndefinedTableError on first use — and if the caller swallows "
        "exceptions (as the learner profiler does), silently lose data instead."
    )


def test_learner_profiles_specifically_is_covered():
    """Named explicitly: this is the table whose absence caused the incident."""
    assert "learner_profiles" in _tables_created_by_migrations()


def test_migration_revisions_form_an_unbroken_chain():
    """A duplicate or dangling `down_revision` silently strands later migrations."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    revs: dict[str, str | None] = {}
    for path in glob.glob(os.path.join(here, "alembic", "versions", "*.py")):
        src = open(path, encoding="utf-8").read()
        rev = re.search(r'^revision:?\s*(?::\s*str\s*)?=\s*["\']([^"\']+)["\']', src, re.M)
        down = re.search(
            r'^down_revision:?[^=]*=\s*(?:["\']([^"\']+)["\']|None)', src, re.M
        )
        if rev:
            revs[rev.group(1)] = down.group(1) if (down and down.group(1)) else None

    assert len(revs) == len(set(revs)), "duplicate revision ids"
    heads = [r for r in revs if r not in set(revs.values())]
    assert len(heads) == 1, f"expected exactly one head, found {sorted(heads)}"
    for rev, down in revs.items():
        assert down is None or down in revs, f"{rev} points at missing revision {down}"
