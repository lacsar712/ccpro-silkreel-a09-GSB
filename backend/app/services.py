"""缫丝盆门槛：改缫丝中须最近一张未作废抱合抽检条结论合格；标已缫完须最近一次汤温落在 38～42℃。"""

from app.models import Basin, CohesionInspection

MIN_TEMP = 38.0
MAX_TEMP = 42.0


class RuleError(ValueError):
    pass


def latest_temp(basin: Basin) -> float | None:
    if not basin.readings:
        return None
    latest = max(basin.readings, key=lambda r: r.taken_at)
    return latest.water_temp_c


def latest_open_inspection(basin: Basin) -> CohesionInspection | None:
    """同一盆未作废条按抽检时刻取最近一张，作为放行依据。"""
    open_slips = [s for s in (basin.inspections or []) if s.voided_at is None]
    if not open_slips:
        return None
    return max(open_slips, key=lambda s: (s.inspected_at, s.id))


def assert_can_set_status(basin: Basin, new_status: str) -> None:
    allowed = {Basin.STATUS_SOAKING, Basin.STATUS_REELING, Basin.STATUS_REELED}
    if new_status not in allowed:
        raise RuleError(f"无效状态：{new_status}")
    if new_status == Basin.STATUS_REELING:
        slip = latest_open_inspection(basin)
        if slip is None:
            raise RuleError("该盆尚无未作废的抱合抽检条，不能改缫丝中")
        if slip.conclusion != CohesionInspection.CONCLUSION_PASS:
            raise RuleError(f"最近一张抱合抽检条结论是{slip.conclusion}，不能改缫丝中")
        return
    if new_status != Basin.STATUS_REELED:
        return
    temp = latest_temp(basin)
    if temp is None:
        raise RuleError("该盆尚无汤温记录，不能标已缫完")
    if temp < MIN_TEMP or temp > MAX_TEMP:
        raise RuleError(
            f"最近汤温 {temp}℃ 不在 {MIN_TEMP:.0f}～{MAX_TEMP:.0f}℃，不能标已缫完"
        )
