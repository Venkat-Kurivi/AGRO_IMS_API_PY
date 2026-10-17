import re
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.auth import SessionDep, get_current_user
from app.api.schemas import (
    RESOURCE_MODELS,
    PurchaseOrderData,
    PurchaseReceiptData,
    SaleData,
    SalesReturnData,
    StockAdjustmentData,
    StockItemCreateData,
    StockItemUpdateData,
    to_camel,
)
from app.application.inventory import (
    AdjustStockCommand,
    CreatePurchaseReceiptCommand,
    CreateSaleCommand,
    CreateSalesReturnCommand,
    DashboardQuery,
    DeleteRecordCommand,
    InventoryHandlers,
    ListRecordsQuery,
    SaveRecordCommand,
    UpdateSaleCommand,
)
from app.domain.entities import AuthenticatedUser
from app.infrastructure.relational_inventory_repository import SqlAlchemyInventoryRepository


router = APIRouter(prefix="/api/inventory", tags=["inventory"], dependencies=[Depends(get_current_user)])


def _wire(value):
    if isinstance(value, list):
        return [_wire(item) for item in value]
    if isinstance(value, dict):
        return {to_camel(key): _wire(item) for key, item in value.items()}
    return value


def _repo(session: Session) -> SqlAlchemyInventoryRepository:
    return SqlAlchemyInventoryRepository(session)


def _handlers(session: Session) -> InventoryHandlers:
    return InventoryHandlers(_repo(session))


def _payload(model, body: dict) -> dict:
    return model.model_validate(body).model_dump(mode="json", by_alias=False, exclude_none=True)


def _make_list(resource: str):
    def endpoint(session: SessionDep, user: Annotated[AuthenticatedUser, Depends(get_current_user)]):
        if resource == "users" and user.role.value != "Admin":
            raise HTTPException(status_code=403, detail="Administrator role required")
        return _wire(_handlers(session).handle(ListRecordsQuery(resource)))
    endpoint.__name__ = f"list_{resource}"
    return endpoint


def _make_create(resource: str, model):
    def endpoint(body: dict, session: SessionDep, user: Annotated[AuthenticatedUser, Depends(get_current_user)]):
        payload = _payload(model, body)
        if resource == "users":
            raw_password = payload.pop("password", None)
            if not raw_password:
                raise HTTPException(status_code=422, detail="Password is required")
            from app.application.authentication import password_hash
            payload["password_hash"] = password_hash.hash(raw_password)
            if user.role.value != "Admin":
                raise HTTPException(status_code=403, detail="Administrator role required")
        saved = _handlers(session).handle(SaveRecordCommand(resource, payload))
        return _wire(saved)
    endpoint.__name__ = f"create_{resource}"
    return endpoint


def _make_update(resource: str, model):
    def endpoint(record_id: str, body: dict, session: SessionDep, user: Annotated[AuthenticatedUser, Depends(get_current_user)]):
        if _repo(session).get(resource, record_id) is None:
            raise HTTPException(status_code=404, detail="Record not found")
        payload = _payload(model, body)
        payload["id"] = record_id
        if resource == "users":
            if user.role.value != "Admin":
                raise HTTPException(status_code=403, detail="Administrator role required")
            raw_password = body.get("password")
            payload.pop("password", None)
            if raw_password:
                from app.application.authentication import password_hash
                payload["password_hash"] = password_hash.hash(raw_password)
        return _wire(_handlers(session).handle(SaveRecordCommand(resource, payload, record_id)))
    endpoint.__name__ = f"update_{resource}"
    return endpoint


def _make_delete(resource: str):
    def endpoint(record_id: str, session: SessionDep, user: Annotated[AuthenticatedUser, Depends(get_current_user)]):
        if resource == "users" and user.role.value != "Admin":
            raise HTTPException(status_code=403, detail="Administrator role required")
        deleted = _handlers(session).handle(DeleteRecordCommand(resource, record_id))
        if not deleted:
            raise HTTPException(status_code=404, detail="Record not found")
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    endpoint.__name__ = f"delete_{resource}"
    return endpoint


for resource, model in RESOURCE_MODELS.items():
    router.add_api_route(f"/{resource}", _make_list(resource), methods=["GET"])
    router.add_api_route(f"/{resource}", _make_create(resource, model), methods=["POST"])
    router.add_api_route(f"/{resource}/{{record_id}}", _make_update(resource, model), methods=["PUT"])
    router.add_api_route(f"/{resource}/{{record_id}}", _make_delete(resource), methods=["DELETE"])


@router.get("/dashboard")
def dashboard(session: SessionDep, branch_id: str | None = Query(default=None, alias="branchId")):
    return _wire(_handlers(session).handle(DashboardQuery(branch_id)))


@router.get("/products")
def products(session: SessionDep, branch_id: str | None = Query(default=None, alias="branchId")):
    repository = _repo(session)
    products_data = repository.list("products")
    stock = repository.list("stock")
    brands = {item["id"]: item["name"] for item in repository.list("brands")}
    categories = {item["id"]: item["name"] for item in repository.list("categories")}
    subcategories = {item["id"]: item["name"] for item in repository.list("subcategories")}
    result = []
    for product in products_data:
        quantity = sum(row["quantity"] for row in stock if row["product_id"] == product["id"] and (branch_id is None or row["branch_id"] == branch_id))
        result.append({"id": product["id"], "sku": product["sku"], "name": product["name"], "brand_name": brands.get(product["brand_id"], "Unknown"), "category_name": categories.get(product["category_id"], "Unknown"), "subcategory_name": subcategories.get(product["subcategory_id"], "Unknown"), "gst": product["gst"], "cost_price": product["cost_price"], "selling_price": product["selling_price"], "quantity": quantity, "branch_id": branch_id or "all"})
    return _wire(sorted(result, key=lambda item: item["name"]))


@router.get("/stock")
def get_stock(session: SessionDep):
    return _wire(_repo(session).list("stock"))


@router.get("/stock/{branch_id}/{product_id}")
def get_stock_item(branch_id: str, product_id: str, session: SessionDep):
    result = _repo(session).stock_item(product_id, branch_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Stock item not found")
    return _wire(result)


@router.post("/stock")
def create_stock_item(body: StockItemCreateData, session: SessionDep):
    repository = _repo(session)
    if repository.stock_item(body.product_id, body.branch_id):
        raise HTTPException(status_code=409, detail="This product already has a stock record for the selected branch.")
    return _wire(repository.stock_change(body.product_id, body.branch_id, body.quantity, body.note, "INITIAL"))


@router.put("/stock/{branch_id}/{product_id}")
def update_stock_item(branch_id: str, product_id: str, body: StockItemUpdateData, session: SessionDep):
    repository = _repo(session)
    if repository.stock_item(product_id, branch_id) is None:
        raise HTTPException(status_code=404, detail="Stock item not found")
    return _wire(_handlers(session).handle(AdjustStockCommand(product_id, branch_id, body.quantity, body.note, True)))


@router.delete("/stock/{branch_id}/{product_id}", status_code=204)
def delete_stock_item(branch_id: str, product_id: str, session: SessionDep):
    repository = _repo(session)
    stock = repository.stock_item(product_id, branch_id)
    if stock is None:
        raise HTTPException(status_code=404, detail="Stock item not found")
    repository.stock_change(product_id, branch_id, -stock["quantity"], "Branch stock record deleted", "DELETE")
    repository.delete("stock", f"{branch_id}:{product_id}")


@router.get("/transactions")
def transactions(session: SessionDep):
    return _wire(_repo(session).list("transactions"))


@router.get("/purchase-orders")
def purchase_orders(session: SessionDep):
    return _wire(_repo(session).list("purchase_orders"))


@router.post("/purchase-orders")
def create_purchase_order(body: PurchaseOrderData, session: SessionDep):
    payload = _payload(PurchaseOrderData, body.model_dump())
    payload.update({"number": f"PO-{datetime.now(UTC):%Y%m%d%H%M%S%f}", "status": "Pending", "payment_status": "Unpaid"})
    payload["items"] = [{**item, "received": 0} for item in payload["items"]]
    return _wire(_repo(session).save("purchase_orders", payload))


@router.patch("/purchase-orders/{record_id}/status")
def update_purchase_order_status(record_id: str, body: dict, session: SessionDep):
    repository = _repo(session)
    order = repository.get("purchase_orders", record_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    statuses = {"pending": "Pending", "partiallyreceived": "PartiallyReceived", "completed": "Completed"}
    payments = {"unpaid": "Unpaid", "partiallypaid": "PartiallyPaid", "paid": "Paid"}
    normalized_status = re.sub(r"[^a-z]", "", str(body.get("status", "")).lower())
    normalized_payment = re.sub(r"[^a-z]", "", str(body.get("paymentStatus", body.get("payment_status", ""))).lower())
    if normalized_status not in statuses or normalized_payment not in payments:
        raise HTTPException(status_code=400, detail="Invalid purchase order or payment status.")
    order.update(status=statuses[normalized_status], payment_status=payments[normalized_payment])
    return _wire(repository.save("purchase_orders", order, record_id))


@router.delete("/purchase-orders/{record_id}", status_code=204)
def delete_purchase_order(record_id: str, session: SessionDep):
    if not _repo(session).delete("purchase_orders", record_id):
        raise HTTPException(status_code=404, detail="Purchase order not found")


@router.get("/purchase-receipts")
def purchase_receipts(session: SessionDep):
    return _wire(_repo(session).list("purchase_receipts"))


@router.post("/purchase-receipts")
def create_purchase_receipt(body: PurchaseReceiptData, session: SessionDep):
    payload = _payload(PurchaseReceiptData, body.model_dump())
    payload["number"] = f"GRN-{datetime.now(UTC):%Y%m%d%H%M%S%f}"
    return _wire(_handlers(session).handle(CreatePurchaseReceiptCommand(payload)))


@router.get("/sales")
def sales(session: SessionDep):
    return _wire(_repo(session).list("sales"))


@router.post("/sales")
def create_sale(body: SaleData, session: SessionDep):
    repository = _repo(session)
    payload = _payload(SaleData, body.model_dump())
    products_by_id = {product["id"]: product for product in repository.list("products")}
    for item in payload["items"]:
        product = products_by_id.get(item["product_id"])
        if product is None:
            raise HTTPException(status_code=404, detail=f"Product {item['product_id']} not found")
        item["unit_cost"] = product["cost_price"]
    payload["number"] = f"INV-{datetime.now(UTC):%Y%m%d%H%M%S}"
    sale = _handlers(session).handle(CreateSaleCommand(payload))
    sale["total"] = sum(item["unit_price"] * item["quantity"] for item in sale["items"])
    return _wire({"id": sale["id"], "number": sale["number"], "customer_id": sale["customer_id"], "branch_id": sale["branch_id"], "date": sale["date"], "items": [{"product_id": item["product_id"], "quantity": item["quantity"], "unit_price": item["unit_price"]} for item in sale["items"]], "total": sale["total"]})


@router.put("/sales/{record_id}")
def update_sale(record_id: str, body: SaleData, session: SessionDep):
    repository = _repo(session)
    payload = _payload(SaleData, body.model_dump())
    products_by_id = {product["id"]: product for product in repository.list("products")}
    for item in payload["items"]:
        product = products_by_id.get(item["product_id"])
        if product is None:
            raise HTTPException(status_code=404, detail=f"Product {item['product_id']} not found")
        item["unit_cost"] = product["cost_price"]
    payload["number"] = f"INV-{datetime.now(UTC):%Y%m%d%H%M%S}"
    result = _handlers(session).handle(UpdateSaleCommand(record_id, payload))
    if result is None:
        raise HTTPException(status_code=404, detail="Sale not found")
    return _wire(result)


@router.get("/sales/returns")
def sales_returns(session: SessionDep):
    return _wire(_repo(session).list("sales_returns"))


@router.post("/sales/returns")
def create_sales_return(body: SalesReturnData, session: SessionDep):
    payload = _payload(SalesReturnData, body.model_dump())
    payload["number"] = f"SR-{datetime.now(UTC):%Y%m%d%H%M%S}"
    return _wire(_handlers(session).handle(CreateSalesReturnCommand(payload)))


@router.post("/stock/adjust")
def adjust_stock(body: StockAdjustmentData, session: SessionDep):
    result = _handlers(session).handle(AdjustStockCommand(body.product_id, body.branch_id, body.quantity, body.note))
    return _wire({"product_id": body.product_id, "branch_id": body.branch_id, "quantity": body.quantity, "note": body.note, "updated_stock": result["quantity"]})


@router.post("/stock/quantity")
def set_stock_quantity(body: StockAdjustmentData, session: SessionDep):
    result = _handlers(session).handle(AdjustStockCommand(body.product_id, body.branch_id, body.quantity, body.note, True))
    return _wire({"product_id": body.product_id, "branch_id": body.branch_id, "quantity": body.quantity, "note": body.note, "updated_stock": result["quantity"]})