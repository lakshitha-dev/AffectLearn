"""The pre/post assessments are the study's dependent variable — these guard their validity.

A broken item here does not crash anything; it silently produces a wrong gain score, which is far
worse. Every check below corresponds to a way the measure could be invalid without anyone noticing:

  * an item reused verbatim between pre and post measures recall of the item, not learning
  * an unpaired item makes pre and post scores non-comparable
  * a zero- or multi-correct item is mis-scored by a system that assumes exactly one
  * an item pointing at a non-existent section cannot have its gain attributed to content
"""

from __future__ import annotations

from app.db.assessment_content import building as ac
from app.db.assessment_content_helpers import parse_question_meta, question


def _meta(q):
    return parse_question_meta(q.explanation)


def test_pre_and_post_exist_with_correct_types():
    pre, post = ac.build_pre(), ac.build_post()
    assert pre.assessment_type == "pre"
    assert post.assessment_type == "post"
    assert pre.title != post.title


def test_every_item_is_matched_across_pre_and_post():
    """An unpaired item makes the two tests measure different things."""
    pre_keys = {_meta(q)["pair"] for q in ac.build_pre().questions}
    post_keys = {_meta(q)["pair"] for q in ac.build_post().questions}
    assert pre_keys == post_keys, (
        f"unmatched pairs — only in pre: {pre_keys - post_keys}; "
        f"only in post: {post_keys - pre_keys}"
    )


def test_pair_keys_are_unique_within_each_assessment():
    for build in (ac.build_pre, ac.build_post):
        keys = [_meta(q)["pair"] for q in build().questions]
        assert len(keys) == len(set(keys)), f"duplicate pair keys in {build.__name__}"


def test_paired_items_are_not_verbatim_copies():
    """The core validity requirement: same construct, different surface.

    If the post item is textually identical, a gain measures memory of that question rather than
    learning of the concept, and the study's central comparison is meaningless.
    """
    pre = {_meta(q)["pair"]: q for q in ac.build_pre().questions}
    post = {_meta(q)["pair"]: q for q in ac.build_post().questions}
    for key, q_pre in pre.items():
        q_post = post[key]
        assert q_pre.text.strip() != q_post.text.strip(), f"pair {key!r} reuses the question text"
        pre_opts = {o.text.strip() for o in q_pre.options}
        post_opts = {o.text.strip() for o in q_post.options}
        assert pre_opts != post_opts, f"pair {key!r} reuses the full option set"


def test_paired_items_target_the_same_section():
    """Same construct implies same source section — otherwise the pairing is mislabelled."""
    pre = {_meta(q)["pair"]: _meta(q)["section"] for q in ac.build_pre().questions}
    post = {_meta(q)["pair"]: _meta(q)["section"] for q in ac.build_post().questions}
    for key, section in pre.items():
        assert post[key] == section, f"pair {key!r} maps to different sections"


def test_exactly_one_correct_option_per_item():
    for build in (ac.build_pre, ac.build_post):
        for q in build().questions:
            n = sum(1 for o in q.options if o.is_correct)
            assert n == 1, f"{q.text[:50]!r} has {n} correct options"


def test_items_have_at_least_three_options():
    """Two-option items are coin flips and add noise rather than measurement."""
    for build in (ac.build_pre, ac.build_post):
        for q in build().questions:
            assert len(q.options) >= 3, f"{q.text[:50]!r} has only {len(q.options)} options"


def test_options_are_shuffled_before_a_learner_sees_them():
    """Authoring order must not reach the learner, or position becomes a free signal.

    The correct option IS first in every authored item here, which would be a validity defect if it
    survived to the learner. It does not: `assessment_service` shuffles per request. This test
    asserts that protection still exists, because if it were ever removed the items in this package
    would silently become answerable without reading them.
    """
    import inspect

    from app.services import assessment_service

    src = inspect.getsource(assessment_service)
    assert "shuffle" in src, (
        "assessment_service no longer shuffles options. The authored items place the correct "
        "answer first, so every question would be answerable by picking option 1."
    )


def test_every_item_maps_to_a_real_section_of_the_study_course():
    """A section title that does not exist cannot have gains attributed to it."""
    from app.db.course_content.building import build as build_course

    course = build_course()
    real = {
        s.title
        for m in course.modules
        for lsn in m.lessons
        for s in lsn.sections
    }
    for build in (ac.build_pre, ac.build_post):
        for q in build().questions:
            section = _meta(q).get("section", "")
            assert section in real, f"unknown section {section!r} in {q.text[:40]!r}"


def test_module_title_matches_the_seeded_course():
    from app.db.course_content.building import build as build_course

    titles = {m.title for m in build_course().modules}
    assert ac.MODULE_TITLE in titles, (
        f"{ac.MODULE_TITLE!r} is not a module of the study course — the seeder would silently "
        f"attach nothing. Available: {sorted(titles)}"
    )


def test_helper_rejects_items_without_exactly_one_answer():
    """The guard must actually fire, or it protects nothing."""
    import pytest

    with pytest.raises(ValueError):
        question("q", [("a", True), ("b", True)], pair_key="k", section_title="s")
    with pytest.raises(ValueError):
        question("q", [("a", False), ("b", False)], pair_key="k", section_title="s")
