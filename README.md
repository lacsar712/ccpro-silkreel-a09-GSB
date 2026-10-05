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

- 盆状态改成「缫丝中」前，读取该盆**最近一张未作废抱合抽检条**，结论必须是「合格」；没有条或结论是「打滑」都会被中文挡住。
- 盆状态不可标成「已缫完」，除非该盆**最近一条**汤温记录落在 **38～42℃**(只看汤温，不掺抽检)。
- 抱合抽检条字段：盆、抽检时刻、结论（仅「合格」/「打滑」）、检验人、作废时刻（可空）。同一盆同一抽检时刻只许一张未作废条入库。
- 仅管理员可新建与作废抽检条；缫丝工打开「抱合抽检」专页只能看。规则在 `backend/app/services.py`。

## 快速启动

```bash
cd SilkReel/SilkReel-01
docker compose up --build
```
