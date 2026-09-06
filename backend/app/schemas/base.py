from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


def camelise_keys(value):
    """Recursively rewrite dict KEYS to camelCase, leaving values alone.

    `CamelModel` handles model FIELDS, which covers almost every response. It does not reach the
    keys inside a `dict[str, ...]` value, and it cannot shape a response whose structure is
    dynamic — the subject-access export is a dump of whatever tables hold rows for one learner,
    so it has no fixed schema to declare.

    Applied at the route boundary rather than in the service, so services keep returning
    Python-natural snake_case and the wire convention stays a property of the wire.
    """
    if isinstance(value, dict):
        return {to_camel(str(k)): camelise_keys(v) for k, v in value.items()}
    if isinstance(value, list):
        return [camelise_keys(v) for v in value]
    return value


class PaginatedResponse(CamelModel):
    items: list
    total: int
    page: int
    page_size: int


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
