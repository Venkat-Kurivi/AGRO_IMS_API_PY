from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "Admin"
    MANAGER = "Manager"


class PurchaseOrderStatus(StrEnum):
    PENDING = "Pending"
    PARTIALLY_RECEIVED = "PartiallyReceived"
    COMPLETED = "Completed"


class PaymentStatus(StrEnum):
    UNPAID = "Unpaid"
    PARTIALLY_PAID = "PartiallyPaid"
    PAID = "Paid"


class StockTransactionType(StrEnum):
    PURCHASE = "Purchase"
    SALE = "Sale"
    RETURN = "Return"
    ADJUSTMENT = "Adjustment"


@dataclass
class AggregateRoot:
    id: str


@dataclass
class User(AggregateRoot):
    name: str
    username: str
    password_hash: str
    role: UserRole
    branch_id: str | None = None
    active: bool = True


@dataclass(frozen=True)
class AuthenticatedUser:
    id: str
    username: str
    role: UserRole
    branch_id: str | None


@dataclass
class Branch(AggregateRoot):
    name: str
    code: str
    city: str = ""
    phone: str = ""


@dataclass
class Brand(AggregateRoot):
    name: str
    origin: str = ""


@dataclass
class Category(AggregateRoot):
    name: str
    description: str = ""


@dataclass
class Subcategory(AggregateRoot):
    name: str
    category_id: str


@dataclass
class Customer(AggregateRoot):
    name: str
    phone: str = ""
    email: str = ""
    city: str = ""
    address: str = ""


@dataclass
class Vendor(AggregateRoot):
    name: str
    phone: str = ""
    email: str = ""
    city: str = ""


@dataclass
class Product(AggregateRoot):
    sku: str
    name: str
    brand_id: str
    category_id: str
    subcategory_id: str
    gst: Decimal
    cost_price: Decimal
    selling_price: Decimal


@dataclass
class StockItem(AggregateRoot):
    product_id: str
    branch_id: str
    quantity: int


@dataclass
class StockTransaction(AggregateRoot):
    date: datetime
    product_id: str
    branch_id: str
    quantity: int
    type: StockTransactionType
    reference: str
    note: str


@dataclass
class PurchaseOrderItem:
    product_id: str
    quantity: int
    received: int
    unit_cost: Decimal


@dataclass
class PurchaseOrder(AggregateRoot):
    number: str
    vendor_id: str
    branch_id: str
    date: datetime
    expected_date: datetime
    status: PurchaseOrderStatus
    payment_status: PaymentStatus
    items: list[PurchaseOrderItem] = field(default_factory=list)


@dataclass
class PurchaseReceipt(AggregateRoot):
    number: str
    purchase_order_id: str
    date: datetime
    note: str
    items: list[dict] = field(default_factory=list)


@dataclass
class Sale(AggregateRoot):
    number: str
    customer_id: str
    branch_id: str
    date: datetime
    items: list[dict] = field(default_factory=list)


@dataclass
class SalesReturn(AggregateRoot):
    number: str
    sale_id: str
    date: datetime
    reason: str
    items: list[dict] = field(default_factory=list)