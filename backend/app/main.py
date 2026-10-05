from datetime import datetime, timezone

from quart import Quart, g, jsonify, request
from quart.helpers import make_response

from app.db import SessionLocal
from app.models import Basin, CohesionInspection, utcnow
from app.repositories import BasinRepo, DuplicateInspectionError, InspectionRepo, UserRepo
from app.security import make_token, parse_token, verify_password
from app.services import RuleError, assert_can_set_status, latest_open_inspection, latest_temp

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
        return jsonify({"detail": "仅管理员能登记或作废抱合抽检条"}), 403
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


def _basin_json(basin: Basin) -> dict:
    slip = latest_open_inspection(basin)
    return {
        "id": basin.id,
        "code": basin.code,
        "status": basin.status,
        "ringIndex": basin.ring_index,
        "latestTempC": latest_temp(basin),
        "readingCount": len(basin.readings or []),
        "latestInspection": (
            {
                "conclusion": slip.conclusion,
                "inspectedAt": slip.inspected_at.isoformat(),
                "inspector": slip.inspector,
            }
            if slip
            else None
        ),
    }


def _inspection_json(row: CohesionInspection) -> dict:
    return {
        "id": row.id,
        "basinId": row.basin_id,
        "basinCode": row.basin.code if row.basin else "",
        "inspectedAt": row.inspected_at.isoformat(),
        "conclusion": row.conclusion,
        "inspector": row.inspector,
        "voidedAt": row.voided_at.isoformat() if row.voided_at else None,
    }


def _parse_when(raw) -> datetime | None:
    if not raw or not isinstance(raw, str):
        return None
    try:
        moment = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


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


@app.route("/api/inspections")
async def list_inspections():
    denied = require_user()
    if denied:
        return denied
    raw = request.args.get("basinId", "")
    basin_id = None
    if raw:
        try:
            basin_id = int(raw)
        except ValueError:
            return jsonify({"detail": "盆编号必须是数字"}), 400
    async with SessionLocal() as session:
        rows = await InspectionRepo(session).list(basin_id)
        return {"inspections": [_inspection_json(r) for r in rows]}


@app.route("/api/inspections", methods=["POST"])
async def create_inspection():
    denied = require_admin()
    if denied:
        return denied
    body = (await request.get_json(force=True)) or {}
    try:
        basin_id = int(body.get("basinId"))
    except (TypeError, ValueError):
        return jsonify({"detail": "盆编号必须是数字"}), 400
    conclusion = body.get("conclusion", "")
    if conclusion not in CohesionInspection.CONCLUSIONS:
        return jsonify({"detail": "结论只能是合格或打滑"}), 400
    inspected_at = _parse_when(body.get("inspectedAt"))
    if inspected_at is None:
        return jsonify({"detail": "抽检时刻格式不对"}), 400
    async with SessionLocal() as session:
        basin = await BasinRepo(session).get(basin_id)
        if basin is None:
            return jsonify({"detail": "盆不存在"}), 404
        try:
            row = await InspectionRepo(session).create(
                basin, inspected_at, conclusion, g.user.username
            )
        except DuplicateInspectionError:
            return jsonify({"detail": "同一盆同一抽检时刻已有未作废的抽检条，只许入库一张"}), 409
        row = await InspectionRepo(session).get(row.id)
        return _inspection_json(row), 201


@app.route("/api/inspections/<int:inspection_id>/void", methods=["POST"])
async def void_inspection(inspection_id: int):
    denied = require_admin()
    if denied:
        return denied
    async with SessionLocal() as session:
        repo = InspectionRepo(session)
        row = await repo.get(inspection_id)
        if row is None:
            return jsonify({"detail": "抽检条不存在"}), 404
        if row.voided_at is None:
            await repo.void(row, utcnow())
        return _inspection_json(row)
