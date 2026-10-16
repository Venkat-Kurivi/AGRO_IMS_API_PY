from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


class BranchRecord(Base):
    __tablename__ = "branches"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(20))
    city: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str] = mapped_column(String(50))


class BrandRecord(Base):
    __tablename__ = "brands"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    origin: Mapped[str] = mapped_column(String(150))


class CategoryRecord(Base):
    __tablename__ = "categories"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(String(250))


class SubcategoryRecord(Base):
    __tablename__ = "subcategories"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    category_id: Mapped[str] = mapped_column(ForeignKey("categories.id"))


class CustomerRecord(Base):
    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(50))
    email: Mapped[str] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(100))
    address: Mapped[str] = mapped_column(String(250), default="")


class VendorRecord(Base):
    __tablename__ = "vendors"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(50))
    email: Mapped[str] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(100))


class ProductRecord(Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sku: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    brand_id: Mapped[str] = mapped_column(ForeignKey("brands.id"))
    category_id: Mapped[str] = mapped_column(ForeignKey("categories.id"))
    subcategory_id: Mapped[str] = mapped_column(ForeignKey("subcategories.id"))
    gst: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    cost_price: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    selling_price: Mapped[Decimal] = mapped_column(Numeric(18, 2))


class UserRecord(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))
    branch_id: Mapped[str | None] = mapped_column(ForeignKey("branches.id"), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class StockItemRecord(Base):
    __tablename__ = "stock_items"
    __table_args__ = (UniqueConstraint("product_id", "branch_id", name="uq_stock_product_branch"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id"))
    quantity: Mapped[int] = mapped_column(Integer)


class StockTransactionRecord(Base):
    __tablename__ = "stock_transactions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(24))
    reference: Mapped[str] = mapped_column(String(100))
    note: Mapped[str] = mapped_column(String(250))


class PurchaseOrderRecord(Base):
    __tablename__ = "purchase_orders"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    number: Mapped[str] = mapped_column(String(100), unique=True)
    vendor_id: Mapped[str] = mapped_column(ForeignKey("vendors.id"))
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id"))
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expected_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32))
    payment_status: Mapped[str] = mapped_column(String(24))
    items: Mapped[list["PurchaseOrderItemRecord"]] = relationship(back_populates="purchase_order", cascade="all, delete-orphan")
    receipts: Mapped[list["PurchaseReceiptRecord"]] = relationship(back_populates="purchase_order")


class PurchaseOrderItemRecord(Base):
    __tablename__ = "purchase_order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    purchase_order_id: Mapped[str] = mapped_column(ForeignKey("purchase_orders.id", ondelete="CASCADE"))
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    received: Mapped[int] = mapped_column(Integer)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    purchase_order: Mapped[PurchaseOrderRecord] = relationship(back_populates="items")


class PurchaseReceiptRecord(Base):
    __tablename__ = "purchase_receipts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    number: Mapped[str] = mapped_column(String(100), unique=True)
    purchase_order_id: Mapped[str] = mapped_column(ForeignKey("purchase_orders.id"))
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    note: Mapped[str] = mapped_column(String(250))
    items: Mapped[list["PurchaseReceiptItemRecord"]] = relationship(back_populates="receipt", cascade="all, delete-orphan")
    purchase_order: Mapped[PurchaseOrderRecord] = relationship(back_populates="receipts")


class PurchaseReceiptItemRecord(Base):
    __tablename__ = "purchase_receipt_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    purchase_receipt_id: Mapped[str] = mapped_column(ForeignKey("purchase_receipts.id", ondelete="CASCADE"))
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    receipt: Mapped[PurchaseReceiptRecord] = relationship(back_populates="items")


class SaleRecord(Base):
    __tablename__ = "sales"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    number: Mapped[str] = mapped_column(String(100), unique=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"))
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id"))
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    items: Mapped[list["SaleItemRecord"]] = relationship(back_populates="sale", cascade="all, delete-orphan")
    returns: Mapped[list["SalesReturnRecord"]] = relationship(back_populates="sale")


class SaleItemRecord(Base):
    __tablename__ = "sale_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sale_id: Mapped[str] = mapped_column(ForeignKey("sales.id", ondelete="CASCADE"))
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    sale: Mapped[SaleRecord] = relationship(back_populates="items")


class SalesReturnRecord(Base):
    __tablename__ = "sales_returns"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    number: Mapped[str] = mapped_column(String(100), unique=True)
    sale_id: Mapped[str] = mapped_column(ForeignKey("sales.id"))
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(String(250))
    items: Mapped[list["SalesReturnItemRecord"]] = relationship(back_populates="sales_return", cascade="all, delete-orphan")
    sale: Mapped[SaleRecord] = relationship(back_populates="returns")


class SalesReturnItemRecord(Base):
    __tablename__ = "sales_return_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sales_return_id: Mapped[str] = mapped_column(ForeignKey("sales_returns.id", ondelete="CASCADE"))
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    sales_return: Mapped[SalesReturnRecord] = relationship(back_populates="items")


engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def initialize_database() -> None:
    Base.metadata.create_all(engine)