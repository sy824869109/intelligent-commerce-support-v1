"""商品 HTTP 协议适配；SQL、价格有效期及可见性由 Commerce 决定。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from ics_commerce import views
from .identity import current_principal
from .responses import Failure, Success, success


class Page(BaseModel):
    model_config = ConfigDict(extra="forbid")
    after: views.Ref | None = None
    limit: int = Field(default=20, ge=1, le=100)


class Search(Page):
    q: str = Field(default="", max_length=100)
    category_id: views.Ref | None = None


def router():
    """注册五个只读入口；每个端点都经过身份边界与 Commerce 重授权。"""
    api = APIRouter(
        prefix="/api/v1/products",
        tags=["catalog"],
        responses={code: {"model": Failure} for code in (400, 401, 403, 404, 422, 503)},
    )

    def unambiguous(request: Request):
        # 禁止重复参数和未声明作用域，避免客户端误以为 tenant_id 生效。
        if any(len(request.query_params.getlist(key)) != 1 for key in request.query_params):
            from ics_commerce.catalog import CatalogError

            raise CatalogError("INPUT_INVALID", 422)

    def no_query(request: Request):
        if request.query_params:
            from ics_commerce.catalog import CatalogError

            raise CatalogError("INPUT_INVALID", 422)

    @api.get("", response_model=Success[views.ProductPage], dependencies=[Depends(unambiguous)])
    def search(
        request: Request, query: Annotated[Search, Query()], principal=Depends(current_principal)
    ):
        """搜索当前租户上架商品；after 是排他 ID 下界，不是授权凭证。"""
        return success(
            request,
            views.ProductPage(**request.app.state.catalog.search(principal, **query.model_dump())),
        )

    @api.get(
        "/{product_id}",
        response_model=Success[views.ProductDetail],
        dependencies=[Depends(no_query)],
    )
    def detail(product_id: views.Ref, request: Request, principal=Depends(current_principal)):
        """返回可见商品与类目；不存在和无权访问统一 404。"""
        return success(
            request, views.ProductDetail(**request.app.state.catalog.detail(principal, product_id))
        )

    @api.get(
        "/{product_id}/specifications",
        response_model=Success[views.Specifications],
        dependencies=[Depends(unambiguous)],
    )
    def specifications(
        product_id: views.Ref,
        request: Request,
        query: Annotated[Page, Query()],
        principal=Depends(current_principal),
    ):
        """返回属性及分页上架 SKU；不隐式选择某个规格。"""
        return success(
            request,
            views.Specifications(
                **request.app.state.catalog.specifications(
                    principal, product_id, **query.model_dump()
                )
            ),
        )

    @api.get(
        "/{product_id}/skus/{sku_id}",
        response_model=Success[views.SkuFacts],
        dependencies=[Depends(no_query)],
    )
    def sku(
        product_id: views.Ref,
        sku_id: views.Ref,
        request: Request,
        principal=Depends(current_principal),
    ):
        """返回独立的价格/库存观察状态，不提供结算或库存预留。"""
        return success(
            request, views.SkuFacts(**request.app.state.catalog.sku(principal, product_id, sku_id))
        )

    @api.get(
        "/{product_id}/activity",
        response_model=Success[views.Activity],
        dependencies=[Depends(no_query)],
    )
    def activity(product_id: views.Ref, request: Request, principal=Depends(current_principal)):
        """当前尚无可核实活动来源，明确返回 UNKNOWN 而非推测优惠。"""
        return success(
            request, views.Activity(**request.app.state.catalog.activity(principal, product_id))
        )

    return api
