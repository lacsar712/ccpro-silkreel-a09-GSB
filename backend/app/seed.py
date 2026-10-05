from datetime import timedelta

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Basin, BathReading, CohesionSlip, Filature, User, utcnow
from app.security import hash_password


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
        if mill is None:
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
            soaking_basin = None
            for code, status, temp, idx in specs:
                basin = Basin(filature_id=mill.id, code=code, status=status, ring_index=idx)
                session.add(basin)
                await session.flush()
                if status == Basin.STATUS_SOAKING and soaking_basin is None:
                    soaking_basin = basin
                if temp is not None:
                    session.add(
                        BathReading(
                            basin_id=basin.id,
                            water_temp_c=temp,
                            operator="worker",
                            taken_at=now - timedelta(hours=2),
                        )
                    )
            # 种子：给一张浸茧盆挂一张结论打滑的抱合抽检条，挡住浸茧→缫丝中。
            if soaking_basin is not None:
                session.add(
                    CohesionSlip(
                        basin_id=soaking_basin.id,
                        inspected_at=now - timedelta(hours=1),
                        result=CohesionSlip.RESULT_SLIP,
                        inspector="admin",
                    )
                )
            await session.commit()
            return

        # 已存在的演示库（本次新增抽检表）：若一张抽检条都没有，给浸茧盆补一张打滑条；
        # 已有人工作废/建过条则不插手。
        any_slip = (await session.execute(select(CohesionSlip.id).limit(1))).first()
        if any_slip is None:
            soaking = (
                await session.execute(
                    select(Basin)
                    .where(Basin.filature_id == mill.id, Basin.status == Basin.STATUS_SOAKING)
                    .order_by(Basin.ring_index)
                    .limit(1)
                )
            ).scalar_one_or_none()
            if soaking is not None:
                session.add(
                    CohesionSlip(
                        basin_id=soaking.id,
                        inspected_at=utcnow() - timedelta(hours=1),
                        result=CohesionSlip.RESULT_SLIP,
                        inspector="admin",
                    )
                )
        await session.commit()
