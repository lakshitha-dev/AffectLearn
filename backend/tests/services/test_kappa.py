"""Cohen's kappa, as used for inter-rater agreement in the expert review.

A pure function, so these live apart from the API tests rather than under their module-level
asyncio mark.

Kappa is reported instead of raw agreement because raw agreement is inflated by the base rate:
if ninety per cent of decisions are reasonable, two raters who both simply always said "yes"
agree ninety per cent of the time while sharing no judgement at all.
"""

from app.services.decision_review_service import cohens_kappa


def test_perfect_agreement_is_one():
    assert cohens_kappa([True, False, True, False], [True, False, True, False]) == 1.0


def test_chance_level_agreement_is_zero():
    # Both raters say yes half the time and agree half the time -- exactly what chance predicts,
    # which raw agreement would report as a respectable 50%.
    assert cohens_kappa([True, True, False, False], [True, False, True, False]) == 0.0


def test_systematic_disagreement_is_negative():
    assert cohens_kappa([True, True, False, False], [False, False, True, True]) < 0


def test_a_constant_rater_is_undefined_not_zero():
    """Expected agreement is 1.0, so the denominator is zero. A rater who always says yes is a
    real and interesting finding; reporting kappa 0.0 would say "no better than chance", which
    is a different claim."""
    assert cohens_kappa([True, True, True], [True, True, True]) is None


def test_too_few_items_is_undefined():
    assert cohens_kappa([True], [True]) is None


def test_mismatched_lengths_are_undefined():
    assert cohens_kappa([True, False], [True]) is None
