from dataclasses import dataclass

from app.domain.repositories import InventoryRepository


@dataclass(frozen=True)
class ListRecordsQuery:
    resource: str


@dataclass(frozen=True)
class SaveRecordCommand:
    resource: str
    payload: dict
    record_id: str | None = None


@dataclass(frozen=True)
class DeleteRecordCommand:
    resource: str
    record_id: str


@dataclass(frozen=True)
class AdjustStockCommand:
    product_id: str
    branch_id: str
    quantity: int
    note: str
    set_quantity: bool = False


@dataclass(frozen=True)
class DashboardQuery:
    branch_id: str | None = None


@dataclass(frozen=True)
class CreateSaleCommand:
    payload: dict


@dataclass(frozen=True)
class UpdateSaleCommand:
    record_id: str
    payload: dict


@dataclass(frozen=True)
class CreatePurchaseReceiptCommand:
    payload: dict


@dataclass(frozen=True)
class CreateSalesReturnCommand:
    payload: dict


class InventoryHandlers:
    def __init__(self, repository: InventoryRepository):
        self.repository = repository

    def handle(self, request):
        if isinstance(request, ListRecordsQuery):
            return self.repository.list(request.resource)
        if isinstance(request, SaveRecordCommand):
            return self.repository.save(request.resource, request.payload, request.record_id)
        if isinstance(request, DeleteRecordCommand):
            return self.repository.delete(request.resource, request.record_id)
        if isinstance(request, AdjustStockCommand):
            if request.set_quantity:
                current = self.repository.stock_item(request.product_id, request.branch_id)
                delta = request.quantity - (current["quantity"] if current else 0)
            else:
                delta = request.quantity
            return self.repository.stock_change(request.product_id, request.branch_id, delta, request.note)
        if isinstance(request, DashboardQuery):
            return self.repository.dashboard(request.branch_id)
        if isinstance(request, CreateSaleCommand):
            return self.repository.create_sale(request.payload)
        if isinstance(request, UpdateSaleCommand):
            return self.repository.update_sale(request.record_id, request.payload)
        if isinstance(request, CreatePurchaseReceiptCommand):
            return self.repository.create_receipt(request.payload)
        if isinstance(request, CreateSalesReturnCommand):
            return self.repository.create_return(request.payload)
        raise TypeError(f"Unsupported request: {type(request).__name__}")