"""FastAPI application factory and lifecycle-scoped, read-only health checks."""

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from starlette.exceptions import HTTPException

from .middleware import RequestContext
from .responses import ErrorDetail, Failure, Success, failure, success
from .settings import Settings
from ics_persistence.database import Database

Check = Callable[[], Awaitable[bool]]


class Health(BaseModel):
    status: str
    service: str = "api-gateway"
    scope: str = "application"
    checks: dict[str, str]


def create_app(
    settings: Settings | None = None,
    *,
    checks: Mapping[str, Check] | None = None,
    database: Database | None = None,
) -> FastAPI:
    """Each instance owns its lifecycle; database is an explicit optional dependency."""
    settings = settings or Settings()
    readiness_checks = dict(checks or {})
    if database is not None:
        if "mysql" in readiness_checks:
            raise ValueError("Reserved MySQL health check")

        async def mysql_check():
            return await asyncio.to_thread(database.ready)

        readiness_checks["mysql"] = mysql_check

    @asynccontextmanager
    async def lifespan(app):
        app.state.ready = True
        try:
            yield
        finally:
            app.state.ready = False
            if database is not None:
                await asyncio.to_thread(database.close)

    app = FastAPI(
        title="智能电商客服 API Gateway",
        version="0.1.0",
        description="应用骨架；显式启用数据库时检查连接和迁移版本。不表示 RAG 或业务已可用。",
        lifespan=lifespan,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
        debug=False,
        redirect_slashes=False,
    )
    app.state.ready = False
    app.state.settings = settings
    app.add_middleware(RequestContext)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return failure(
            request, 422, ErrorDetail(code="VALIDATION_ERROR", message="请求参数不符合接口要求。")
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        code, message = {
            404: ("NOT_FOUND", "接口不存在。"),
            405: ("METHOD_NOT_ALLOWED", "请求方法不支持。"),
            401: ("UNAUTHORIZED", "需要有效身份。"),
            403: ("FORBIDDEN", "无权访问。"),
        }.get(exc.status_code, ("HTTP_ERROR", "请求无法处理。"))
        # Preserve protocol headers, never arbitrary exception-provided values.
        headers = {
            k: v
            for k, v in (exc.headers or {}).items()
            if k.lower() in {"allow", "www-authenticate", "retry-after"}
        }
        return failure(request, exc.status_code, ErrorDetail(code=code, message=message), headers)

    @app.get("/health/live", response_model=Success[Health], tags=["health"])
    async def live(request: Request):
        return success(request, Health(status="alive", checks={"process": "ok"}))

    @app.get(
        "/health/ready",
        response_model=Success[Health],
        responses={503: {"model": Failure}},
        tags=["health"],
    )
    async def ready(request: Request):
        async def run(check):
            try:
                return (
                    await asyncio.wait_for(check(), timeout=settings.readiness_timeout_seconds)
                    is True
                )
            except Exception:
                return False

        results = await asyncio.gather(*(run(c) for c in readiness_checks.values()))
        if not app.state.ready or not all(results):
            return failure(
                request,
                503,
                ErrorDetail(
                    code="SERVICE_NOT_READY",
                    message="服务尚未准备就绪。",
                    retryable=True,
                    client_action="RETRY_WITH_BACKOFF",
                ),
            )
        return success(
            request,
            Health(
                status="ready",
                scope="application+database" if database is not None else "application",
                checks={"lifecycle": "ok", **{k: "ok" for k in readiness_checks}},
            ),
        )

    return app
