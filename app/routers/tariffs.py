from fastapi import APIRouter
from sqlalchemy import select

from app.db import SessionDep
from app.models import Tariff
from app.schemas import TariffOut

router = APIRouter(tags=["tariffs"])


@router.get("/tariffs")
def list_tariffs(session: SessionDep) -> list[TariffOut]:
    tariffs = session.scalars(select(Tariff).order_by(Tariff.id))
    return [TariffOut.model_validate(tariff) for tariff in tariffs]
