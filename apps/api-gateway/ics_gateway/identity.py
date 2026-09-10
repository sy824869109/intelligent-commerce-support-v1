"""Live M03 routes and reusable FastAPI authorization dependencies."""

import json
import asyncio
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPBearer
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from ics_identity.service import IdentityError
from .responses import ErrorDetail, Failure, Success, failure, success

Ref = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Login(Model):
    tenant_id: Ref
    username: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,63}$")]
    password: SecretStr = Field(min_length=15, max_length=128)


class Refresh(Model):
    refresh_token: SecretStr = Field(min_length=43, max_length=43)


class TokenPair(Model):
    access_token: str = Field(repr=False)
    refresh_token: str = Field(repr=False)
    token_type: Literal["Bearer"]
    expires_in: int


class Me(Model):
    user_id: Ref
    tenant_id: Ref
    session_id: Ref
    role: Literal["CUSTOMER", "AGENT", "ADMIN"]


class Done(Model):
    status: Literal["DONE"] = "DONE"


class PasswordChange(Model):
    old_password: SecretStr = Field(min_length=15, max_length=128)
    new_password: SecretStr = Field(min_length=15, max_length=128)


class MemberUpdate(Model):
    role: Literal["CUSTOMER", "AGENT", "ADMIN"]
    active: bool


class UserCreate(Model):
    username: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,63}$")]
    password: SecretStr = Field(min_length=15, max_length=128)
    role: Literal["CUSTOMER", "AGENT", "ADMIN"]


class GroupCreate(Model):
    name: Annotated[str, Field(min_length=1, max_length=120)]


class Created(Model):
    id: Ref


class GroupMember(Model):
    user_id: Ref
    active: bool


def current_principal(request: Request, credentials=Depends(HTTPBearer(auto_error=False))):
    cached = getattr(request.state, "principal", None)
    if cached is not None:
        return cached
    values = request.headers.getlist("authorization")
    if len(values) != 1 or not values[0].lower().startswith("bearer "):
        raise IdentityError()
    return request.app.state.identity.authenticate(values[0][7:])


def require_resource(action, loader):
    """Loader(session, request, principal) returns authoritative domain Resource or None.

    Runs authorization and loader in one transaction, before a handler can feed data
    into an LLM. Domain mutations must reauthorize inside their owner transaction.
    """

    def dependency(request: Request, principal=Depends(current_principal)):
        identity = request.app.state.identity
        with identity.db.transaction() as session:
            resource = loader(session, request, principal)
            if resource is None:
                raise IdentityError("ACCESS_DENIED", 404)
            return identity.authorize(session, principal, action, resource)

    return dependency


class IdentityBoundary:
    def __init__(self, app, origins):
        self.app, self.origins = app, frozenset(origins)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api/"):
            return await self.app(scope, receive, send)
        request = Request(scope)
        origins = request.headers.getlist("origin")
        code, status = None, 400
        if len(origins) > 1 or (origins and origins[0] not in self.origins):
            code, status = "ORIGIN_DENIED", 403
        elif any(
            key.lower() in {"access_token", "refresh_token", "token", "authorization"}
            for key in request.query_params
        ):
            code, status = "TOKEN_IN_URL", 400
        elif scope["path"].startswith("/api/v1/auth") and request.query_params:
            code, status = "INPUT_INVALID", 422
        if code:
            return await failure(
                request, status, ErrorDetail(code=code, message="请求不符合安全边界。")
            )(scope, receive, send)
        # Default-deny API authentication, even if a future route omits its dependency.
        # Resource authorization still requires the domain loader before returning facts.
        public = scope["method"] == "POST" and scope["path"] in {
            "/api/v1/auth/login",
            "/api/v1/auth/refresh",
        }
        if not public:
            authorization = request.headers.getlist("authorization")
            try:
                if len(authorization) != 1 or not authorization[0].lower().startswith("bearer "):
                    raise IdentityError()
                request.state.principal = await run_in_threadpool(
                    request.app.state.identity.authenticate, authorization[0][7:]
                )
            except IdentityError:
                return await failure(
                    request,
                    401,
                    ErrorDetail(
                        code="AUTH_REQUIRED",
                        message="需要有效身份。",
                        client_action="REAUTHENTICATE",
                    ),
                    {"WWW-Authenticate": "Bearer"},
                )(scope, receive, send)
        if scope["path"].startswith("/api/v1/auth") and scope["method"] in {"POST", "PUT", "PATCH"}:
            if (
                request.headers.get("content-type", "").split(";")[0].strip().lower()
                != "application/json"
            ):
                return await failure(
                    request, 415, ErrorDetail(code="MEDIA_UNSUPPORTED", message="需要 JSON 请求。")
                )(scope, receive, send)
            body = bytearray()
            deadline = asyncio.get_running_loop().time() + 10
            while True:
                try:
                    message = await asyncio.wait_for(
                        receive(), timeout=max(0, deadline - asyncio.get_running_loop().time())
                    )
                except TimeoutError:
                    return await failure(
                        request, 408, ErrorDetail(code="REQUEST_TIMEOUT", message="请求接收超时。")
                    )(scope, receive, send)
                if message["type"] == "http.disconnect":
                    return
                body.extend(message.get("body", b""))
                if len(body) > 4096:
                    return await failure(
                        request,
                        413,
                        ErrorDetail(code="PAYLOAD_TOO_LARGE", message="认证请求过大。"),
                    )(scope, receive, send)
                if not message.get("more_body", False):
                    break

            # Reject duplicate JSON keys rather than permitting ambiguous identity fields.
            def pairs(items):
                result = {}
                for key, value in items:
                    if key in result:
                        raise ValueError("Duplicate JSON key")
                    result[key] = value
                return result

            try:
                json.loads(body, object_pairs_hook=pairs)
            except (ValueError, UnicodeError, RecursionError):
                return await failure(
                    request, 422, ErrorDetail(code="INPUT_INVALID", message="JSON 请求无效。")
                )(scope, receive, send)
            delivered = False

            async def bounded_receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()

            return await self.app(scope, bounded_receive, send)
        return await self.app(scope, receive, send)


def router():
    api = APIRouter(
        prefix="/api/v1/auth",
        tags=["identity"],
        responses={
            status: {"model": Failure}
            for status in (400, 401, 403, 404, 408, 409, 413, 415, 422, 429, 500)
        },
    )

    @api.post("/login", response_model=Success[TokenPair])
    def login(body: Login, request: Request):
        values = request.app.state.identity.login(
            body.tenant_id,
            body.username,
            body.password.get_secret_value(),
            request.client.host if request.client else "unknown",
        )
        return success(request, TokenPair(**values))

    @api.post("/refresh", response_model=Success[TokenPair])
    def refresh(body: Refresh, request: Request):
        return success(
            request,
            TokenPair(**request.app.state.identity.refresh(body.refresh_token.get_secret_value())),
        )

    @api.get("/me", response_model=Success[Me])
    def me(request: Request, principal=Depends(current_principal)):
        return success(request, Me(**vars(principal)))

    @api.post("/logout", response_model=Success[Done])
    def logout(body: Model, request: Request, principal=Depends(current_principal)):
        request.app.state.identity.logout(principal)
        return success(request, Done())

    @api.post("/password", response_model=Success[Done])
    def password(body: PasswordChange, request: Request, principal=Depends(current_principal)):
        try:
            request.app.state.identity.change_password(
                principal,
                body.old_password.get_secret_value(),
                body.new_password.get_secret_value(),
            )
        except ValueError:
            raise IdentityError("PASSWORD_POLICY", 422) from None
        return success(request, Done())

    @api.patch("/members/{user_id}", response_model=Success[Done])
    def member(
        user_id: Ref, body: MemberUpdate, request: Request, principal=Depends(current_principal)
    ):
        request.app.state.identity.update_member(principal, user_id, body.role, body.active)
        return success(request, Done())

    @api.post("/members", response_model=Success[Created], status_code=201)
    def create_member(body: UserCreate, request: Request, principal=Depends(current_principal)):
        try:
            user_id = request.app.state.identity.create_member(
                principal, body.username, body.password.get_secret_value(), body.role
            )
        except ValueError:
            raise IdentityError("PASSWORD_POLICY", 422) from None
        return success(request, Created(id=user_id))

    @api.post("/groups", response_model=Success[Created], status_code=201)
    def create_group(body: GroupCreate, request: Request, principal=Depends(current_principal)):
        return success(
            request, Created(id=request.app.state.identity.create_group(principal, body.name))
        )

    @api.put("/groups/{group_id}/members", response_model=Success[Done])
    def group_member(
        group_id: Ref, body: GroupMember, request: Request, principal=Depends(current_principal)
    ):
        request.app.state.identity.group_member(principal, group_id, body.user_id, body.active)
        return success(request, Done())

    return api
