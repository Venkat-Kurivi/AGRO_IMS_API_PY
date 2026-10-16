from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


def to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, use_enum_values=True)
    id: str | None = None


NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class BranchData(ApiModel):
    name: NonEmpty
    code: NonEmpty
    city: str = ""
    phone: str = ""


class BrandData(ApiModel):
    name: NonEmpty
    origin: str = ""


class CategoryData(ApiModel):
    name: NonEmpty
    description: str = ""


class SubcategoryData(ApiModel):
    name: NonEmpty
    category_id: NonEmpty


class CustomerData(ApiModel):
    name: NonEmpty
    phone: str = ""
    email: str = ""
    city: str = ""
    address: str = ""


class VendorData(ApiModel):
    name: NonEmpty
    phone: str = ""
    email: str = ""
    city: str = ""


class ProductData(ApiModel):
    sku: NonEmpty
    name: NonEmpty
    brand_id: NonEmpty
    category_id: NonEmpty
    subcategory_id: NonEmpty
    gst: float = Field(ge=0)
    cost_price: float = Field(ge=0)
    selling_price: float = Field(ge=0)


class UserData(ApiModel):
    name: NonEmpty
    username: NonEmpty
    password: str | None = None
    role: Literal["Admin", "Manager"] = "Manager"
    branch_id: str | None = None
    active: bool = True


class SaleLineData(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    product_id: NonEmpty
    quantity: int = Field(gt=0)
    unit_price: float = Field(ge=0)


class SaleData(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    customer_id: NonEmpty
    branch_id: NonEmpty
    date: datetime
    items: list[SaleLineData] = Field(min_length=1)


class PurchaseOrderLineData(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    product_id: NonEmpty
    quantity: int = Field(gt=0)
    unit_cost: float = Field(ge=0)


class PurchaseOrderData(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    vendor_id: NonEmpty
    branch_id: NonEmpty
    date: datetime
    expected_date: datetime
    items: list[PurchaseOrderLineData] = Field(min_length=1)


class PurchaseReceiptLineData(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    product_id: NonEmpty
    quantity: int = Field(gt=0)


class PurchaseReceiptData(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    purchase_order_id: NonEmpty
    date: datetime
    note: str = ""
    items: list[PurchaseReceiptLineData] = Field(min_length=1)


class SalesReturnData(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    sale_id: NonEmpty
    date: datetime
    reason: str = ""
    items: list[PurchaseReceiptLineData] = Field(min_length=1)


class StockAdjustmentData(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    product_id: NonEmpty
    branch_id: NonEmpty
    quantity: int
    note: str = ""


class StockItemCreateData(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    product_id: NonEmpty
    branch_id: NonEmpty
    quantity: int = Field(ge=0)
    note: str = ""


class StockItemUpdateData(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    quantity: int = Field(ge=0)
    note: str = ""


RESOURCE_MODELS = {
    "branches": BranchData,
    "brands": BrandData,
    "categories": CategoryData,
    "subcategories": SubcategoryData,
    "customers": CustomerData,
    "vendors": VendorData,
    "products": ProductData,
    "users": UserData,
}