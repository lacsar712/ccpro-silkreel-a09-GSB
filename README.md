# SilkReel-01 · 江口缫丝坞

缫丝盆环状作业台。登录后看到的是沿汤池围成一圈的盆位，点盆登记汤温并改状态——不是侧栏双列表 CRUD。

## 技术栈

| 层 | 技术 |
| --- | --- |
| Web API | Quart（异步 Flask 族）· Hypercorn |
| 结构 | `repositories.py` 仓储 + `services.py` 门槛，路由不直接拼 SQL |
| 数据 | SQLAlchemy 2 async · asyncpg · PostgreSQL 15 |
| 前端 | Preact 10 · Vite |
| 部署 | Docker Compose |

## 路径与端口

- 前端：http://localhost:4760
- API：http://localhost:8760
- PostgreSQL：localhost:6160

## 演示账号

| 用户名 | 密码 | 角色 |
| --- | --- | --- |
| `admin` | `123456` | 管理员 |
| `worker` | `123456` | 缫丝工 |

## 业务规则

- 盆状态不可标成「已缫完」，除非该盆**最近一条**汤温记录落在 **38～42℃**；此判定只看汤温带。
- 「浸茧」改「缫丝中」须读取该盆**最近一张未作废抱合抽检条**，且结论为**合格**；无条或最近结论为打滑，服务端中文挡回。已缫完判定不掺抽检。
- 抱合抽检条字段：盆、抽检时刻、结论（只允许合格/打滑）、检验人、作废时刻（可空）。同一盆未作废条按抽检时刻取最近一张放行。
- 同一盆「抽检时刻相同」的两张未作废条只许入库一张（部分唯一索引，冲突返回 409）；作废后可再建同时刻条。
- 仅管理员可建条与作废；缫丝工打开抱合抽检专页只能看。规则在 `backend/app/services.py`，接口在 `backend/app/main.py`。
- 种子数据：浸茧盆「甲-2」挂一张结论**打滑**的抽检条（挡住浸茧→缫丝中）。

## 快速启动

```bash
cd SilkReel/SilkReel-01
docker compose up --build
```
