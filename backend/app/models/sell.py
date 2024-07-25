from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import RelationshipProperty
from sqlmodel import Field, Relationship, SQLModel
from app.db.base import BaseIDModel

if TYPE_CHECKING:
    from app.models.enterprise import Enterprise
    from app.models.user import User


class Client(BaseIDModel, table=True):
    __tablename__ = "client"
    name: str = Field(description="Name of the client.", max_length=120, index=True)
    description: Optional[str] = Field(description="Description of the client.", max_length=120, index=False, default=None)
    enterprise_code: Optional[str] = Field(description="Code of the enterprise.", min_length=6, max_length=40, index=True, default=None)
    enterprise_id: int = Field(
        foreign_key="enterprise.id",
        index=True,
    )
    enterprise: "Enterprise" = Relationship(back_populates="clients")
    person_code: Optional[str] = Field(description="Code of the person.", min_length=6, max_length=40, index=True, default=None)
    sells: Optional[list["Sell"]] = Relationship(back_populates="client")


class ProductBase(BaseIDModel):
    name: str = Field(description="Name of the product.", max_length=120, index=True)
    cost: float = Field(description="Cost of the product.", ge=0.0)
    description: Optional[str] = Field(default=None, max_length=450)
    stock: int = Field(description="Stock of the product.", ge=0, default=0)
    enterprise_id: Optional[int] = Field(
        foreign_key="enterprise.id",
        index=True,
    )


class BaseProduct(ProductBase, table=True):
    """Represents a product stored in the database."""

    price: Optional[float] = Field(description="Price of the product.", ge=0.0, default=None)
    created_at: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = Field(default=None)
    deleted_at: Optional[datetime] = Field(default=None)
    created_by: Optional[int] = Field(foreign_key="user.id", description="User ID that created the product.")
    last_updated_by: Optional[int] = Field(foreign_key="user.id", description="User ID that last updated the product.")
    user_updated: Optional["User"] = Relationship(sa_relationship=RelationshipProperty(
        "User",
        back_populates="updates",
        foreign_keys="[BaseProduct.last_updated_by]",
    ))
    user_created: Optional["User"] = Relationship(sa_relationship=RelationshipProperty(
        "User",
        back_populates="products",
        foreign_keys="[BaseProduct.created_by]"
    ))
    enterprise: "Enterprise" = Relationship(back_populates='products')

    __tablename__ = "product"
    __table_args__ = (UniqueConstraint("name", "enterprise_id"),)


class BaseSell(BaseIDModel):
    product_id: int = Field(foreign_key="product.id")
    client_id: int | None = Field(foreign_key="client.id")
    quantity: int = Field(description="Quantity of the product sold.", ge=0)
    user_id: int = Field(foreign_key="user.id")
    created_at: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc))



class Sell(BaseSell, table=True):
    """Represents a sell stored in the database."""

    __tablename__ = "sell"
    user: Optional["User"] = Relationship(back_populates="sells")
    client: Optional["Client"] = Relationship(back_populates="sells")


class SellCreate(SQLModel):
    product_id: int
    client_id: int
    quantity: int
    user_id: int


class SellCreateMe(SQLModel):
    client_id: int
    product_id: int
    quantity: int


class UserSells(BaseIDModel):
    username: str
    sells: list["BaseSell"] = [];


class SellDetailResponse(SQLModel):
    data: BaseSell


class SellsResponse(SQLModel):
    data: list[BaseSell] = []


class UserSellsListResponse(SQLModel):
    data: list[UserSells] = []
     

class ClientCreate(SQLModel):
    name: str
    description: Optional[str] = None
    enterprise_code: Optional[str] = None
    person_code: Optional[str] = None


class ClientRead(SQLModel):
    id: int
    name: str
    description: str
    enterprise_code: Optional[str] = None
    person_code: Optional[str] = None


class ClientResponse(SQLModel):
    data: ClientRead
