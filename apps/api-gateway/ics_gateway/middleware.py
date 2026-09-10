"""ASGI request context survives errors and streaming without buffering bodies."""

import json
import asyncio
import logging
import re
import time
from uuid import uuid4

from starlette.datastructures import MutableHeaders
from starlette.requests import Request

from .responses import ErrorDetail, failure
from ics_observability.core import CURRENT, Trace

LOGGER = logging.getLogger("ics.gateway.requests")
REQUEST_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")


class RequestContext:
    def __init__(self, app, metrics):
        self.app = app
        self.metrics = metrics
        self.diagnostic_failures = 0

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        candidates = [v for k, v in scope.get("headers", []) if k.lower() == b"x-request-id"]
        candidate = candidates[0].decode("ascii", errors="replace") if len(candidates) == 1 else ""
        request_id = candidate if REQUEST_ID.fullmatch(candidate) else uuid4().hex
        # Diagnostic identifier only: never trust client trace/tenant/actor headers for identity.
        state = scope.setdefault("state", {})
        state.update(request_id=request_id, trace_id=uuid4().hex)
        token = CURRENT.set(Trace(request_id, state["trace_id"]))
        started, status = False, 500
        complete, outcome = False, "FAILED"
        begin = time.monotonic()

        async def correlated_send(message):
            nonlocal started, status, complete
            if message["type"] == "http.response.start":
                started, status = True, message["status"]
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
                headers["X-Trace-ID"] = state["trace_id"]
                headers["Cache-Control"] = "no-store"
                headers["X-Content-Type-Options"] = "nosniff"
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                complete = True

        try:
            await self.app(scope, receive, correlated_send)
            outcome = "SUCCEEDED" if complete and status < 400 else "FAILED"
        except asyncio.CancelledError:
            outcome = "CANCELLED"
            raise
        except Exception:
            # Never log raw exception strings, input bodies, query strings or authorization.
            status = 500
            if started:
                raise  # A partially sent response cannot be rewritten as successful JSON.
            response = failure(
                Request(scope),
                500,
                ErrorDetail(
                    code="INTERNAL_ERROR",
                    message="服务暂时无法处理请求。",
                    client_action="CONTACT_SUPPORT",
                ),
            )
            await response(scope, receive, correlated_send)
        finally:
            CURRENT.reset(token)
            route = scope.get("route")
            duration = round((time.monotonic() - begin) * 1000, 2)
            # Diagnostics must not turn an already committed/streamed response into a retry.
            try:
                self.metrics.observe("http", outcome, duration)
                LOGGER.info(
                    json.dumps(
                        {
                            "event": "http_request",
                            "request_id": request_id,
                            "trace_id": state["trace_id"],
                            "method": scope["method"],
                            "route": getattr(route, "path", "unmatched"),
                            "status": status,
                            "duration_ms": duration,
                            "outcome": outcome,
                            "response_complete": complete,
                        },
                        ensure_ascii=True,
                    )
                )
            except Exception:
                # Audit writes are NOT handled here; their failures must propagate.
                self.diagnostic_failures += 1
