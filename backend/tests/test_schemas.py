"""Tests for Pydantic schema base classes and camelCase aliasing."""


async def test_camel_model_alias_generation():
    """Verify CamelModel converts snake_case fields to camelCase in JSON."""
    from app.schemas.base import PaginatedResponse

    resp = PaginatedResponse(items=[], total=0, page=1, page_size=20)
    json_data = resp.model_dump(by_alias=True)

    assert "pageSize" in json_data
    assert "page_size" not in json_data


async def test_camel_model_populate_by_name():
    """Verify CamelModel accepts snake_case field names for construction."""
    from app.schemas.base import PaginatedResponse

    resp = PaginatedResponse(items=["a"], total=1, page=1, page_size=10)
    assert resp.page_size == 10
    assert resp.total == 1


async def test_paginated_response_structure():
    """Verify PaginatedResponse has required fields."""
    from app.schemas.base import PaginatedResponse

    resp = PaginatedResponse(items=[1, 2, 3], total=100, page=2, page_size=3)
    dumped = resp.model_dump(by_alias=True)

    assert dumped["items"] == [1, 2, 3]
    assert dumped["total"] == 100
    assert dumped["page"] == 2
    assert dumped["pageSize"] == 3


async def test_error_response_structure():
    """Verify ErrorResponse wraps error with code and message."""
    from app.schemas.base import ErrorResponse, ErrorDetail

    err = ErrorResponse(error=ErrorDetail(code="NOT_FOUND", message="Resource not found"))
    dumped = err.model_dump()

    assert dumped["error"]["code"] == "NOT_FOUND"
    assert dumped["error"]["message"] == "Resource not found"
