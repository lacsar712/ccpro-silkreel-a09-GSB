from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Basin, BathReading, CohesionSlip, Filature, User


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
                selectinload(Filature.basins)
                .selectinload(Basin.readings),
                selectinload(Filature.basins).selectinload(Basin.slips),
            )
        )
        return result.scalars().first()

    async def get(self, basin_id: int) -> Basin | None:
        result = await self.session.execute(
            select(Basin)
            .options(selectinload(Basin.readings), selectinload(Basin.slips))
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


class CohesionSlipRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_for(self, basin_id: int | None = None) -> list[CohesionSlip]:
        stmt = (
            select(CohesionSlip)
            .options(selectinload(CohesionSlip.basin))
            .order_by(CohesionSlip.basin_id, CohesionSlip.inspected_at.desc())
        )
        if basin_id is not None:
            stmt = stmt.where(CohesionSlip.basin_id == basin_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get(self, slip_id: int) -> CohesionSlip | None:
        result = await self.session.execute(
            select(CohesionSlip)
            .options(selectinload(CohesionSlip.basin))
            .where(CohesionSlip.id == slip_id)
        )
        return result.scalar_one_or_none()

    async def add(
        self,
        basin: Basin,
        inspected_at,
        result: str,
        inspector: str,
    ) -> CohesionSlip:
        row = CohesionSlip(
            basin=basin,
            inspected_at=inspected_at,
            result=result,
            inspector=inspector,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def void(self, slip: CohesionSlip, voided_at) -> CohesionSlip:
        slip.voided_at = voided_at
        await self.session.commit()
        await self.session.refresh(slip)
        return slip
