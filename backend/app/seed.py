from datetime import timedelta

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Basin, BathReading, CohesionInspection, Filature, User, utcnow
from app.security import hash_password


async def _ensure_slip_seed(session) -> None:
    """保证至少一张结论打滑的未作废抽检条挂在浸茧盆上(新库老库都幂等)。"""
    has_any = (await session.execute(select(CohesionInspection.id))).first()
    if has_any:
        return
    basin = (
        await session.execute(
            select(Basin)
            .where(Basin.status == Basin.STATUS_SOAKING)
            .order_by(Basin.ring_index)
        )
    ).scalars().first()
    if basin is None:
        return
    session.add(
        CohesionInspection(
            basin_id=basin.id,
            inspected_at=utcnow() - timedelta(hours=1),
            conclusion=CohesionInspection.CONCLUSION_SLIP,
            inspector="admin",
        )
    )


async def seed_demo() -> None:
    async with SessionLocal() as session:
        existing = await session.execute(select(User).where(User.username == "admin"))
        admin = existing.scalar_one_or_none()
        if admin is None:
            admin = User(username="admin", password_hash=hash_password("123456"), role="admin")
            session.add(admin)
        else:
            admin.password_hash = hash_password("123456")
            admin.role = "admin"

        existing_w = await session.execute(select(User).where(User.username == "worker"))
        worker = existing_w.scalar_one_or_none()
        if worker is None:
            session.add(User(username="worker", password_hash=hash_password("123456"), role="worker"))
        else:
            worker.password_hash = hash_password("123456")
            worker.role = "worker"

        mill = (await session.execute(select(Filature))).scalars().first()
        if mill:
            await _ensure_slip_seed(session)
            await session.commit()
            return

        mill = Filature(name="江口缫丝坞", riverside="东津渡")
        session.add(mill)
        await session.flush()
        now = utcnow()
        specs = [
            ("甲-1", Basin.STATUS_REELING, 40.5, 0),
            ("甲-2", Basin.STATUS_SOAKING, None, 1),
            ("乙-1", Basin.STATUS_REELED, 39.2, 2),
            ("乙-2", Basin.STATUS_REELING, 36.0, 3),
            ("丙-1", Basin.STATUS_SOAKING, None, 4),
            ("丙-2", Basin.STATUS_REELED, 41.0, 5),
        ]
        for code, status, temp, idx in specs:
            basin = Basin(filature_id=mill.id, code=code, status=status, ring_index=idx)
            session.add(basin)
            await session.flush()
            if temp is not None:
                session.add(
                    BathReading(
                        basin_id=basin.id,
                        water_temp_c=temp,
                        operator="worker",
                        taken_at=now - timedelta(hours=2),
                    )
                )
        await _ensure_slip_seed(session)
        await session.commit()
