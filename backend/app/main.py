from datetime import datetime, timezone

from quart import Quart, g, jsonify, request
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal
from app.models import Basin, CohesionSlip, utcnow
from app.repositories import BasinRepo, CohesionSlipRepo, UserRepo
from app.security import make_token, parse_token, verify_password
from app.services import (
    RuleError,
    assert_can_set_status,
    latest_active_slip,
    latest_temp,
)

app = Quart(__name__)


def _bearer() -> str | None:
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:]
    return None


@app.before_request
async def load_user():
    g.user = None
    token = _bearer()
    if not token:
        return
    username = parse_token(token)
    if not username:
        return
    async with SessionLocal() as session:
        g.user = await UserRepo(session).by_username(username)


def require_user():
    if g.user is None:
        return jsonify({"detail": "未登录"}), 401
    return None


def require_admin():
    denied = require_user()
    if denied:
        return denied
    if g.user.role != "admin":
        return jsonify({"detail": "仅管理员可操作抱合抽检条"}), 403
    return None


@app.route("/api/health")
async def health():
    return {"status": "ok", "service": "SilkReel"}


@app.route("/api/auth/login", methods=["POST"])
async def login():
    body = await request.get_json(force=True)
    username = (body or {}).get("username", "")
    password = (body or {}).get("password", "")
    async with SessionLocal() as session:
        user = await UserRepo(session).by_username(username)
        if user is None or not verify_password(password, user.password_hash):
            return jsonify({"detail": "用户名或密码错误"}), 401
        return {
            "access_token": make_token(user.username),
            "user": {"username": user.username, "role": user.role},
        }


@app.route("/api/auth/me")
async def me():
    denied = require_user()
    if denied:
        return denied
    return {"username": g.user.username, "role": g.user.role}


def _parse_dt(value) -> datetime | None:
    """datetime-local 提交的朴素时间按 UTC 落库；空值返回 None。"""
    if value in (None, ""):
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        raise RuleError("时刻格式无效")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _slip_json(slip: CohesionSlip) -> dict:
    return {
        "id": slip.id,
        "basinId": slip.basin_id,
        "basinCode": slip.basin.code if slip.basin else None,
        "inspectedAt": slip.inspected_at.isoformat() if slip.inspected_at else None,
        "result": slip.result,
        "inspector": slip.inspector,
        "voidedAt": slip.voided_at.isoformat() if slip.voided_at else None,
    }


def _basin_json(basin: Basin) -> dict:
    slip = latest_active_slip(basin)
    return {
        "id": basin.id,
        "code": basin.code,
        "status": basin.status,
        "ringIndex": basin.ring_index,
        "latestTempC": latest_temp(basin),
        "readingCount": len(basin.readings or []),
        "latestSlip": _slip_json(slip) if slip is not None else None,
    }


@app.route("/api/board")
async def board():
    denied = require_user()
    if denied:
        return denied
    async with SessionLocal() as session:
        mill = await BasinRepo(session).board()
        if mill is None:
            return jsonify({"detail": "尚无缫丝坞"}), 404
        basins = sorted(mill.basins, key=lambda b: b.ring_index)
        return {
            "filature": mill.name,
            "riverside": mill.riverside,
            "basins": [_basin_json(b) for b in basins],
        }


@app.route("/api/basins/<int:basin_id>/readings", methods=["POST"])
async def add_reading(basin_id: int):
    denied = require_user()
    if denied:
        return denied
    body = await request.get_json(force=True)
    try:
        temp = float((body or {}).get("waterTempC"))
    except (TypeError, ValueError):
        return jsonify({"detail": "汤温必须是数字"}), 400
    async with SessionLocal() as session:
        repo = BasinRepo(session)
        basin = await repo.get(basin_id)
        if basin is None:
            return jsonify({"detail": "盆不存在"}), 404
        await repo.add_reading(basin, temp, g.user.username)
        basin = await repo.get(basin_id)
        return _basin_json(basin)


@app.route("/api/basins/<int:basin_id>/status", methods=["POST"])
async def set_status(basin_id: int):
    denied = require_user()
    if denied:
        return denied
    body = await request.get_json(force=True)
    status = (body or {}).get("status", "")
    async with SessionLocal() as session:
        repo = BasinRepo(session)
        basin = await repo.get(basin_id)
        if basin is None:
            return jsonify({"detail": "盆不存在"}), 404
        try:
            assert_can_set_status(basin, status)
        except RuleError as exc:
            return jsonify({"detail": str(exc)}), 400
        await repo.save_status(basin, status)
        basin = await repo.get(basin_id)
        return _basin_json(basin)


@app.route("/api/cohesion-slips")
async def list_slips():
    denied = require_user()
    if denied:
        return denied
    basin_id = request.args.get("basin_id", type=int)
    async with SessionLocal() as session:
        slips = await CohesionSlipRepo(session).list_for(basin_id)
        return {"slips": [_slip_json(s) for s in slips]}


@app.route("/api/cohesion-slips", methods=["POST"])
async def create_slip():
    denied = require_admin()
    if denied:
        return denied
    body = await request.get_json(force=True) or {}
    result = body.get("result", "")
    if result not in (CohesionSlip.RESULT_PASS, CohesionSlip.RESULT_SLIP):
        return jsonify({"detail": "结论只允许合格或打滑"}), 400
    try:
        basin_id = int(body.get("basinId"))
    except (TypeError, ValueError):
        return jsonify({"detail": "必须指定盆"}), 400
    try:
        inspected_at = _parse_dt(body.get("inspectedAt")) or utcnow()
    except RuleError as exc:
        return jsonify({"detail": str(exc)}), 400
    inspector = (body.get("inspector") or "").strip() or g.user.username

    async with SessionLocal() as session:
        basin_repo = BasinRepo(session)
        basin = await basin_repo.get(basin_id)
        if basin is None:
            return jsonify({"detail": "盆不存在"}), 404
        slip_repo = CohesionSlipRepo(session)
        try:
            slip = await slip_repo.add(basin, inspected_at, result, inspector)
        except IntegrityError:
            await session.rollback()
            return jsonify({"detail": "该盆此抽检时刻已有一张未作废抽检条"}), 409
        slip = await slip_repo.get(slip.id)
        return _slip_json(slip)


@app.route("/api/cohesion-slips/<int:slip_id>/void", methods=["POST"])
async def void_slip(slip_id: int):
    denied = require_admin()
    if denied:
        return denied
    body = await request.get_json(silent=True) or {}
    try:
        voided_at = _parse_dt(body.get("voidedAt")) or utcnow()
    except RuleError as exc:
        return jsonify({"detail": str(exc)}), 400
    async with SessionLocal() as session:
        repo = CohesionSlipRepo(session)
        slip = await repo.get(slip_id)
        if slip is None:
            return jsonify({"detail": "抽检条不存在"}), 404
        if slip.voided_at is not None:
            return jsonify({"detail": "该抽检条已作废"}), 400
        slip = await repo.void(slip, voided_at)
        return _slip_json(slip)
