"""Unit tests for conditional routing (Story 4.4 AC4)."""

import pytest

from app.agents.edges import (
    ROUTE_LOG_ONLY,
    ROUTE_PEDAGOGICAL,
    route_after_profiler,
    should_adapt,
)


@pytest.mark.parametrize(
    "phase,group,expected_adapt",
    [
        ("phase_a", "control", False),
        ("phase_a", "adaptive", False),   # Phase A never adapts (FR28)
        ("phase_b", "control", False),    # control group never adapts
        ("phase_b", "adaptive", True),    # only Phase B + adaptive
    ],
)
def test_should_adapt_matrix(phase, group, expected_adapt):
    state = {"phase": phase, "group": group}
    assert should_adapt(state) is expected_adapt


@pytest.mark.parametrize(
    "phase,group,expected_route",
    [
        ("phase_a", "control", ROUTE_LOG_ONLY),
        ("phase_a", "adaptive", ROUTE_LOG_ONLY),
        ("phase_b", "control", ROUTE_LOG_ONLY),
        ("phase_b", "adaptive", ROUTE_PEDAGOGICAL),
    ],
)
def test_route_after_profiler_matrix(phase, group, expected_route):
    assert route_after_profiler({"phase": phase, "group": group}) == expected_route


def test_should_adapt_missing_fields_is_safe():
    assert should_adapt({}) is False


@pytest.mark.parametrize(
    "phase,group,expected_route",
    [
        # AC7 tri-modal contract (Story 6.1): the SAME router, fed REAL phase/group.
        ("phase_a", "adaptive", ROUTE_LOG_ONLY),   # (a) Phase A suppresses adaptation for everyone (FR28)
        ("phase_a", "control", ROUTE_LOG_ONLY),    # (b)
        ("phase_b", "adaptive", ROUTE_PEDAGOGICAL),  # (c) only this reaches the adaptive branch
        ("phase_b", "control", ROUTE_LOG_ONLY),    # (d) control stays a clean log-only cohort
    ],
)
def test_ac7_trimodal_routing(phase, group, expected_route):
    """Story 6.1 AC7: real (phase, group) values select the correct branch unchanged."""
    assert route_after_profiler({"phase": phase, "group": group}) == expected_route
