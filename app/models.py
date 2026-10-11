from sqlalchemy import CheckConstraint, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Tariff(Base):
    __tablename__ = "tariffs"
    __table_args__ = (CheckConstraint("price > 0", name="ck_tariffs_price_positive"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(50), unique=True)
    price: Mapped[int] = mapped_column(Integer)  # в копейках
