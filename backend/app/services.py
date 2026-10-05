"""盆状态门槛。

- 浸茧 → 缫丝中：须该盆最近一张未作废抱合抽检条结论为合格；无条或打滑不放行。
- → 已缫完：仍只看汤温带，最近一次汤温须落在 38～42℃，抽检不掺进去。
"""

from app.models import Basin, CohesionSlip

MIN_TEMP = 38.0
MAX_TEMP = 42.0


class RuleError(ValueError):
    pass


def latest_temp(basin: Basin) -> float | None:
    if not basin.readings:
        return None
    latest = max(basin.readings, key=lambda r: r.taken_at)
    return latest.water_temp_c


def latest_active_slip(basin: Basin) -> CohesionSlip | None:
    """同一盆未作废条按抽检时刻取最近一张。"""
    active = [s for s in (basin.slips or []) if s.voided_at is None]
    if not active:
        return None
    return max(active, key=lambda s: s.inspected_at)


def assert_can_set_status(basin: Basin, new_status: str) -> None:
    allowed = {Basin.STATUS_SOAKING, Basin.STATUS_REELING, Basin.STATUS_REELED}
    if new_status not in allowed:
        raise RuleError(f"无效状态：{new_status}")

    # 浸茧 → 缫丝中：看最近一张未作废抱合抽检条。
    if new_status == Basin.STATUS_REELING and basin.status == Basin.STATUS_SOAKING:
        slip = latest_active_slip(basin)
        if slip is None:
            raise RuleError("该盆尚无抱合抽检条，不能改缫丝中")
        if slip.result != CohesionSlip.RESULT_PASS:
            raise RuleError("最近一张抱合抽检结论为打滑，不能改缫丝中")

    # 已缫完仍只看汤温带，抽检不掺进去。
    if new_status != Basin.STATUS_REELED:
        return
    temp = latest_temp(basin)
    if temp is None:
        raise RuleError("该盆尚无汤温记录，不能标已缫完")
    if temp < MIN_TEMP or temp > MAX_TEMP:
        raise RuleError(
            f"最近汤温 {temp}℃ 不在 {MIN_TEMP:.0f}～{MAX_TEMP:.0f}℃，不能标已缫完"
        )
