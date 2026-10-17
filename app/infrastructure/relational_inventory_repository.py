from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.exceptions import ConflictError, NotFoundError, RuleViolation
from app.infrastructure.database import (
    BrandRecord,
    BranchRecord,
    CategoryRecord,
    CustomerRecord,
    ProductRecord,
    PurchaseOrderItemRecord,
    PurchaseOrderRecord,
    PurchaseReceiptItemRecord,
    PurchaseReceiptRecord,
    SaleItemRecord,
    SaleRecord,
    SalesReturnItemRecord,
    SalesReturnRecord,
    StockItemRecord,
    StockTransactionRecord,
    SubcategoryRecord,
    UserRecord,
    VendorRecord,
)


RESOURCE_MODELS = {
    "branches": BranchRecord,
    "brands": BrandRecord,
    "categories": CategoryRecord,
    "subcategories": SubcategoryRecord,
    "customers": CustomerRecord,
    "vendors": VendorRecord,
    "products": ProductRecord,
    "users": UserRecord,
    "stock": StockItemRecord,
    "transactions": StockTransactionRecord,
    "purchase_orders": PurchaseOrderRecord,
    "purchase_receipts": PurchaseReceiptRecord,
    "sales": SaleRecord,
    "sales_returns": SalesReturnRecord,
}


class SqlAlchemyInventoryRepository:
    def __init__(self, session: Session):
        self.session = session

    def list(self, resource: str) -> list[dict]:
        model = RESOURCE_MODELS[resource]
        rows = self.session.scalars(select(model)).all()
        values = [self._serialize(resource, row) for row in rows]
        sort_key = "date" if resource in {"sales", "purchase_orders", "purchase_receipts", "sales_returns", "transactions"} else "name"
        return sorted(values, key=lambda row: row.get(sort_key, ""), reverse=sort_key == "date")

    def get(self, resource: str, record_id: str) -> dict | None:
        model = RESOURCE_MODELS[resource]
        if resource == "stock":
            branch_id, separator, product_id = record_id.partition(":")
            row = self.session.scalar(select(StockItemRecord).where(
                StockItemRecord.branch_id == branch_id,
                StockItemRecord.product_id == product_id if separator else StockItemRecord.id == record_id,
            ))
        else:
            row = self.session.get(model, record_id)
        return self._serialize(resource, row) if row else None

    def save(self, resource: str, payload: dict, record_id: str | None = None) -> dict:
        model = RESOURCE_MODELS[resource]
        data = dict(payload)
        identifier = record_id or data.get("id") or uuid4().hex
        data["id"] = identifier
        if resource == "users":
            self._validate_user(data, identifier)
        if resource == "stock":
            row = self.session.scalar(select(StockItemRecord).where(
                StockItemRecord.product_id == data["product_id"],
                StockItemRecord.branch_id == data["branch_id"],
            ))
        else:
            row = self.session.get(model, identifier)
        if row is None:
            row = model(id=identifier)
            self.session.add(row)
        nested = data.pop("items", None)
        if resource == "users":
            data.pop("password", None)
            if data.get("password_hash"):
                row.password_hash = data.pop("password_hash")
            elif not row.password_hash:
                raise RuleViolation("A password is required for a new user.")
        else:
            data.pop("password_hash", None)
        for name, value in data.items():
            if name == "id" or not hasattr(row, name):
                continue
            setattr(row, name, self._from_wire_value(name, value))
        if nested is not None:
            row.items = [self._make_child(resource, item) for item in nested]
        self.session.flush()
        return self._serialize(resource, row)

    def _validate_user(self, data: dict, identifier: str) -> None:
        if not data.get("branch_id"):
            data["branch_id"] = None
        elif self.session.get(BranchRecord, data["branch_id"]) is None:
            raise RuleViolation("The selected branch does not exist.")
        username = data.get("username")
        if username and self.session.scalar(select(UserRecord.id).where(
            UserRecord.username == username, UserRecord.id != identifier,
        )):
            raise ConflictError("A user with this username already exists.")

    def delete(self, resource: str, record_id: str) -> bool:
        if resource == "stock":
            row = self.session.scalar(select(StockItemRecord).where(
                StockItemRecord.branch_id == record_id.split(":", 1)[0],
                StockItemRecord.product_id == record_id.split(":", 1)[-1],
            ))
        else:
            row = self.session.get(RESOURCE_MODELS[resource], record_id)
        if row is None:
            return False
        if resource == "purchase_orders" and row.receipts:
            raise ConflictError("A purchase order with receipts cannot be deleted.")
        if resource == "sales" and row.returns:
            raise ConflictError("A sale with returns cannot be deleted.")
        self.session.delete(row)
        self.session.flush()
        return True

    def stock_item(self, product_id: str, branch_id: str) -> dict | None:
        row = self.session.scalar(select(StockItemRecord).where(
            StockItemRecord.product_id == product_id,
            StockItemRecord.branch_id == branch_id,
        ))
        return self._serialize("stock", row) if row else None

    def stock_change(self, product_id: str, branch_id: str, delta: int, note: str, reference: str = "MANUAL", transaction_type: str = "Adjustment") -> dict:
        row = self.session.scalar(select(StockItemRecord).where(
            StockItemRecord.product_id == product_id,
            StockItemRecord.branch_id == branch_id,
        ))
        if row is None:
            if self.session.get(ProductRecord, product_id) is None or self.session.get(BranchRecord, branch_id) is None:
                raise NotFoundError("Product or branch not found.")
            row = StockItemRecord(
                id=f"st_{branch_id}_{product_id}",
                product_id=product_id,
                branch_id=branch_id,
                quantity=0,
            )
            self.session.add(row)
        row.quantity = max(0, row.quantity + delta)
        if delta or reference == "INITIAL":
            self._transaction(product_id, branch_id, delta, note, reference, transaction_type=transaction_type)
        self.session.flush()
        return self._serialize("stock", row)

    def create_sale(self, payload: dict) -> dict:
        with self.session.begin_nested():
            for item in payload["items"]:
                row = self.session.scalar(select(StockItemRecord).where(
                    StockItemRecord.product_id == item["product_id"],
                    StockItemRecord.branch_id == payload["branch_id"],
                ))
                if row is None or row.quantity < item["quantity"]:
                    raise RuleViolation(f"Insufficient stock for product {item['product_id']}.")
                row.quantity -= item["quantity"]
                self._transaction(item["product_id"], payload["branch_id"], -item["quantity"], f"Sold to customer {payload['customer_id']}", payload["number"], payload["date"], "Sale")
            return self.save("sales", payload)

    def create_receipt(self, payload: dict) -> dict:
        order_row = self.session.get(PurchaseOrderRecord, payload["purchase_order_id"])
        if order_row is None:
            raise NotFoundError("Purchase order not found.")
        order = self._serialize("purchase_orders", order_row)
        if not payload["items"]:
            raise RuleViolation("Enter at least one received quantity.")
        received_totals: dict[str, int] = {}
        for item in payload["items"]:
            received_totals[item["product_id"]] = received_totals.get(item["product_id"], 0) + item["quantity"]
        for product_id, quantity in received_totals.items():
            line = next((entry for entry in order["items"] if entry["product_id"] == product_id), None)
            if line is None or line["received"] + quantity > line["quantity"]:
                raise RuleViolation(f"Received quantity for product {product_id} exceeds the ordered quantity.")
        with self.session.begin_nested():
            for item in payload["items"]:
                line = next(entry for entry in order["items"] if entry["product_id"] == item["product_id"])
                line["received"] += item["quantity"]
                self.stock_change(item["product_id"], order["branch_id"], item["quantity"], payload["note"], payload["number"], "Purchase")
            order["status"] = "Completed" if all(line["received"] >= line["quantity"] for line in order["items"]) else "PartiallyReceived"
            self.save("purchase_orders", order, order["id"])
            return self.save("purchase_receipts", payload)

    def update_sale(self, record_id: str, payload: dict) -> dict | None:
        existing = self.get("sales", record_id)
        if existing is None:
            return None
        with self.session.begin_nested():
            for item in existing["items"]:
                self.stock_change(item["product_id"], existing["branch_id"], item["quantity"], "Reversed sale update", existing["number"], "Return")
            for item in payload["items"]:
                row = self.session.scalar(select(StockItemRecord).where(
                    StockItemRecord.product_id == item["product_id"],
                    StockItemRecord.branch_id == payload["branch_id"],
                ))
                if row is None or row.quantity < item["quantity"]:
                    raise RuleViolation(f"Insufficient stock for product {item['product_id']}.")
                row.quantity -= item["quantity"]
                self._transaction(item["product_id"], payload["branch_id"], -item["quantity"], "Updated sale", existing["number"], payload["date"], "Sale")
            payload.update(id=record_id, number=existing["number"])
            return self.save("sales", payload, record_id)

    def create_return(self, payload: dict) -> dict:
        sale = self.get("sales", payload["sale_id"])
        if sale is None:
            raise NotFoundError("Sale not found.")
        sold: dict[str, int] = {}
        for line in sale["items"]:
            sold[line["product_id"]] = sold.get(line["product_id"], 0) + line["quantity"]
        for returned in self.list("sales_returns"):
            if returned["sale_id"] == payload["sale_id"]:
                for line in returned["items"]:
                    sold[line["product_id"]] = sold.get(line["product_id"], 0) - line["quantity"]
        return_totals: dict[str, int] = {}
        for item in payload["items"]:
            return_totals[item["product_id"]] = return_totals.get(item["product_id"], 0) + item["quantity"]
        for product_id, quantity in return_totals.items():
            if quantity < 1 or quantity > sold.get(product_id, 0):
                raise RuleViolation(f"Return quantity for product {product_id} exceeds sold quantity.")
        with self.session.begin_nested():
            for item in payload["items"]:
                self.stock_change(item["product_id"], sale["branch_id"], item["quantity"], payload["reason"], payload["number"], "Return")
            return self.save("sales_returns", payload)

    def dashboard(self, branch_id: str | None) -> dict:
        sales = [row for row in self.list("sales") if branch_id is None or row["branch_id"] == branch_id]
        orders = self.list("purchase_orders")
        branches = self.list("branches")
        products = self.list("products")
        stock = [row for row in self.list("stock") if branch_id is None or row["branch_id"] == branch_id]
        today = datetime.now(UTC).date()
        month_start = today.fromordinal(today.toordinal() - 29)
        total = lambda sale: sum(line["unit_price"] * line["quantity"] for line in sale["items"])
        date_of = lambda row: datetime.fromisoformat(row["date"].replace("Z", "+00:00")).date()
        trend = []
        for offset in range(13, -1, -1):
            target = today.fromordinal(today.toordinal() - offset)
            trend.append({"day": target.strftime("%m-%d"), "value": round(sum(total(sale) for sale in sales if date_of(sale) == target), 2)})
        recent = [sale for sale in sales if month_start <= date_of(sale) <= today]
        quantities: dict[str, int] = {}
        for sale in sales:
            for item in sale["items"]:
                quantities[item["product_id"]] = quantities.get(item["product_id"], 0) + item["quantity"]
        names = {product["id"]: product["name"] for product in products}
        all_sales = self.list("sales")
        return {
            "sales_today": round(sum(total(sale) for sale in sales if date_of(sale) == today), 2),
            "sales_this_week": round(sum(total(sale) for sale in sales if 0 <= (today - date_of(sale)).days < 7), 2),
            "purchases_this_month": round(sum(item["quantity"] * item["unit_cost"] for order in orders if month_start <= date_of(order) <= today for item in order["items"]), 2),
            "low_stock_items": sum(row["quantity"] < 5 for row in stock),
            "profit_last_30_days": round(sum((line["unit_price"] - line["unit_cost"]) * line["quantity"] for sale in recent for line in sale["items"]), 2),
            "sales_invoices_this_week": sum(0 <= (today - date_of(sale)).days < 7 for sale in sales),
            "daily_trend_count": len(trend),
            "trend": trend,
            "branch_performance": [{"name": branch["name"], "sales": round(sum(total(sale) for sale in all_sales if sale["branch_id"] == branch["id"] and month_start <= date_of(sale) <= today), 2), "purchases": round(sum(item["quantity"] * item["unit_cost"] for order in orders if order["branch_id"] == branch["id"] and month_start <= date_of(order) <= today for item in order["items"]), 2)} for branch in branches],
            "top_products": [{"product_name": names.get(product_id, "Unknown"), "quantity": quantity} for product_id, quantity in sorted(quantities.items(), key=lambda item: item[1], reverse=True)[:5]],
        }

    def _transaction(self, product_id: str, branch_id: str, quantity: int, note: str, reference: str, date: str | datetime | None = None, transaction_type: str = "Adjustment") -> None:
        self.session.add(StockTransactionRecord(
            id=uuid4().hex,
            date=self._from_wire_value("date", date or datetime.now(UTC).isoformat()),
            product_id=product_id,
            branch_id=branch_id,
            quantity=quantity,
            type=transaction_type,
            reference=reference,
            note=note,
        ))

    @staticmethod
    def _make_child(resource: str, data: dict):
        models = {
            "purchase_orders": PurchaseOrderItemRecord,
            "purchase_receipts": PurchaseReceiptItemRecord,
            "sales": SaleItemRecord,
            "sales_returns": SalesReturnItemRecord,
        }
        return models[resource](**{
            name: SqlAlchemyInventoryRepository._from_wire_value(name, value)
            for name, value in data.items()
            if name != "id" and hasattr(models[resource], name)
        })

    @staticmethod
    def _from_wire_value(name: str, value):
        if name in {"date", "expected_date"} and isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        if name in {"gst", "cost_price", "selling_price", "unit_cost", "unit_price"} and value is not None:
            return Decimal(str(value))
        return value

    def _serialize(self, resource: str, row) -> dict:
        values = {column.key: getattr(row, column.key) for column in row.__table__.columns}
        for key, value in values.items():
            if isinstance(value, Decimal):
                values[key] = float(value)
            elif isinstance(value, datetime):
                values[key] = value.isoformat()
        if resource == "users":
            values.pop("password_hash", None)
            return values
        if resource in {"purchase_orders", "purchase_receipts", "sales", "sales_returns"}:
            values["items"] = [self._serialize_child(item) for item in row.items]
        return values

    @staticmethod
    def _serialize_child(row) -> dict:
        values = {column.key: getattr(row, column.key) for column in row.__table__.columns}
        values.pop("id", None)
        for key, value in values.items():
            if isinstance(value, Decimal):
                values[key] = float(value)
            elif isinstance(value, datetime):
                values[key] = value.isoformat()
        for foreign_key in ("purchase_order_id", "purchase_receipt_id", "sale_id", "sales_return_id"):
            values.pop(foreign_key, None)
        return values