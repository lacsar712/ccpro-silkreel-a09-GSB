from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Basin, BathReading, CohesionInspection, Filature, User


class DuplicateInspectionError(Exception):
    """同一盆同一抽检时刻已有未作废条，只许入库一张。"""


class UserRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def by_username(self, username: str) -> User | None:
        result = await self.session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()


class BasinRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def board(self) -> Filature | None:
        result = await self.session.execute(
            select(Filature).options(
                selectinload(Filature.basins).selectinload(Basin.readings),
                selectinload(Filature.basins).selectinload(Basin.inspections),
            )
        )
        return result.scalars().first()

    async def get(self, basin_id: int) -> Basin | None:
        result = await self.session.execute(
            select(Basin)
            .options(selectinload(Basin.readings), selectinload(Basin.inspections))
            .where(Basin.id == basin_id)
        )
        return result.scalar_one_or_none()

    async def add_reading(self, basin: Basin, temp_c: float, operator: str) -> BathReading:
        row = BathReading(basin=basin, water_temp_c=temp_c, operator=operator)
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def save_status(self, basin: Basin, status: str) -> None:
        basin.status = status
        await self.session.commit()


class InspectionRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list(self, basin_id: int | None = None) -> list[CohesionInspection]:
        stmt = (
            select(CohesionInspection)
            .options(selectinload(CohesionInspection.basin))
            .order_by(CohesionInspection.inspected_at.desc(), CohesionInspection.id.desc())
        )
        if basin_id is not None:
            stmt = stmt.where(CohesionInspection.basin_id == basin_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get(self, inspection_id: int) -> CohesionInspection | None:
        result = await self.session.execute(
            select(CohesionInspection)
            .options(selectinload(CohesionInspection.basin))
            .where(CohesionInspection.id == inspection_id)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        basin: Basin,
        inspected_at: datetime,
        conclusion: str,
        inspector: str,
    ) -> CohesionInspection:
        row = CohesionInspection(
            basin=basin,
            inspected_at=inspected_at,
            conclusion=conclusion,
            inspector=inspector,
        )
        self.session.add(row)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise DuplicateInspectionError() from exc
        await self.session.refresh(row)
        return row

    async def void(self, row: CohesionInspection, when: datetime) -> None:
        row.voided_at = when
        await self.session.commit()
