"""M02.1 HTTP envelopes implement E-02/E-07; event schema freeze belongs to M02.3."""

from typing import Generic, TypeVar

from pydantic import BaseModel
from starlette.requests import Request
from starlette.responses import JSONResponse

DataT = TypeVar("DataT")


class Success(BaseModel, Generic[DataT]):
    request_id: str
    trace_id: str
    data: DataT


class ErrorDetail(BaseModel):
    code: str
    message: str
    retryable: bool = False
    client_action: str = "FIX_REQUEST"
    command_id: str | None = None


class Failure(BaseModel):
    request_id: str
    trace_id: str
    error: ErrorDetail


def success(request: Request, data: BaseModel) -> dict:
    return {
        "request_id": request.state.request_id,
        "trace_id": request.state.trace_id,
        "data": data.model_dump(),
    }


def failure(request: Request, status: int, detail: ErrorDetail, headers=None) -> JSONResponse:
    content = Failure(
        request_id=request.state.request_id, trace_id=request.state.trace_id, error=detail
    )
    return JSONResponse(content.model_dump(), status_code=status, headers=headers)
