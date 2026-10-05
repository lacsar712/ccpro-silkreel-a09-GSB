import { render } from "preact";
import { useEffect, useState } from "preact/hooks";
import { api, clearToken, setToken, token } from "./api.js";
import "./app.css";

const STATUS_LABEL = { soaking: "浸茧", reeling: "缫丝中", reeled: "已缫完" };
const RESULT_LABEL = { pass: "合格", slip: "打滑" };

function fmtTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("zh-CN", { hour12: false });
}

function nowLocalInput() {
  const d = new Date();
  const pad = (x) => String(x).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(
    d.getHours()
  )}:${pad(d.getMinutes())}`;
}

function Login({ onOk }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("123456");
  const [err, setErr] = useState("");
  async function submit(e) {
    e.preventDefault();
    setErr("");
    try {
      const data = await api("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      setToken(data.access_token);
      onOk(data.user);
    } catch (ex) {
      setErr(ex.message);
    }
  }
  return (
    <div class="login">
      <h1>江口缫丝坞</h1>
      <p>汤温环盆作业台，不是列表台账。</p>
      <form onSubmit={submit} autocomplete="off">
        <label>
          用户名
          <input
            name="username"
            autocomplete="off"
            value={username}
            onInput={(e) => setUsername(e.target.value)}
          />
        </label>
        <label>
          密码
          <input
            name="password"
            type="password"
            autocomplete="off"
            value={password}
            onInput={(e) => setPassword(e.target.value)}
          />
        </label>
        <p class="hint">已预填 admin / 123456，另有 worker / 123456</p>
        <button type="submit">登录</button>
      </form>
      {err && <p class="err">{err}</p>}
    </div>
  );
}

function Topbar({ user, page, onNav }) {
  return (
    <div class="topbar">
      <div>
        <h1>江口缫丝坞</h1>
        <nav class="nav">
          <button
            class={page === "yard" ? "navbtn active" : "navbtn"}
            onClick={() => onNav("yard")}
          >
            环盆作业台
          </button>
          <button
            class={page === "inspect" ? "navbtn active" : "navbtn"}
            onClick={() => onNav("inspect")}
          >
            抱合抽检
          </button>
        </nav>
      </div>
      <div class="who">
        <span>
          {user.username}（{user.role === "admin" ? "管理员" : "缫丝工"}）
        </span>
        <button
          onClick={() => {
            clearToken();
            location.reload();
          }}
        >
          退出
        </button>
      </div>
    </div>
  );
}

function Yard() {
  const [board, setBoard] = useState(null);
  const [picked, setPicked] = useState(null);
  const [temp, setTemp] = useState("40");
  const [err, setErr] = useState("");

  async function refresh() {
    const data = await api("/api/board");
    setBoard(data);
    setPicked((prev) =>
      prev ? data.basins.find((b) => b.id === prev.id) || data.basins[0] : prev
    );
  }

  useEffect(() => {
    refresh().catch((e) => setErr(e.message));
  }, []);

  if (!board) {
    return <div class="yard">{err || "装载环盆…"}</div>;
  }

  const n = board.basins.length;

  async function writeTemp() {
    setErr("");
    try {
      const row = await api(`/api/basins/${picked.id}/readings`, {
        method: "POST",
        body: JSON.stringify({ waterTempC: Number(temp) }),
      });
      await refresh();
      setPicked(row);
    } catch (ex) {
      setErr(ex.message);
    }
  }
  async function setStatus(status) {
    setErr("");
    try {
      const row = await api(`/api/basins/${picked.id}/status`, {
        method: "POST",
        body: JSON.stringify({ status }),
      });
      await refresh();
      setPicked(row);
    } catch (ex) {
      // 打滑/无条由服务端中文挡回，抽屉不另开绿灯。
      setErr(ex.message);
    }
  }

  const slip = picked?.latestSlip;

  return (
    <div class="yard">
      <p class="sub">点盆登记汤温；浸茧改缫丝中须最近一张未作废抱合抽检合格，已缫完仍只看最近汤温 38～42℃</p>
      <div class="ring">
        {board.basins.map((b, i) => {
          const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
          const left = 50 + Math.cos(angle) * 38;
          const top = 50 + Math.sin(angle) * 38;
          return (
            <button
              key={b.id}
              class={`basin ${b.status}`}
              style={{ left: `${left}%`, top: `${top}%` }}
              onClick={() => setPicked(b)}
            >
              <strong>{b.code}</strong>
              <span>{STATUS_LABEL[b.status]}</span>
            </button>
          );
        })}
      </div>
      {picked && (
        <div class="drawer">
          <h3>
            {picked.code} · {STATUS_LABEL[picked.status]}
          </h3>
          <p>最近汤温：{picked.latestTempC ?? "无"} ℃ · 记录 {picked.readingCount} 次</p>
          <p class="slip-line">
            最近未作废抽检：
            {slip ? (
              <span class={`badge ${slip.result}`}>
                {RESULT_LABEL[slip.result]} · {fmtTime(slip.inspectedAt)}
              </span>
            ) : (
              <span class="badge none">无</span>
            )}
          </p>
          {picked.status === "soaking" && (
            <p class="hint">
              {slip?.result === "pass"
                ? "抽检合格，可改缫丝中。"
                : "无合格抽检条时改缫丝中会被挡住：无条或最近结论打滑均不放行。"}
            </p>
          )}
          <input value={temp} onInput={(e) => setTemp(e.target.value)} />
          <button onClick={writeTemp}>登记汤温</button>
          <div>
            <button onClick={() => setStatus("soaking")}>浸茧</button>
            <button onClick={() => setStatus("reeling")}>缫丝中</button>
            <button onClick={() => setStatus("reeled")}>已缫完</button>
          </div>
          {err && <p class="err">{err}</p>}
        </div>
      )}
    </div>
  );
}

function Inspection({ user }) {
  const admin = user.role === "admin";
  const [board, setBoard] = useState(null);
  const [basinFilter, setBasinFilter] = useState("");
  const [slips, setSlips] = useState([]);
  const [err, setErr] = useState("");
  const [form, setForm] = useState({
    basinId: "",
    inspectedAt: nowLocalInput(),
    result: "pass",
    inspector: user.username,
  });

  async function loadBoard() {
    const data = await api("/api/board");
    setBoard(data);
    return data;
  }

  async function loadSlips(b) {
    const data = b || (await loadBoard());
    const basinId = basinFilter || "";
    const list = await api(
      basinId ? `/api/cohesion-slips?basin_id=${encodeURIComponent(basinId)}` : "/api/cohesion-slips"
    );
    const codeOf = new Map(data.basins.map((x) => [x.id, x.code]));
    setSlips(
      list.slips.map((s) => ({ ...s, basinCode: s.basinCode || codeOf.get(s.basinId) || s.basinId }))
    );
  }

  useEffect(() => {
    loadBoard()
      .then((b) => loadSlips(b))
      .catch((e) => setErr(e.message));
  }, []);

  async function reload() {
    setErr("");
    try {
      await loadSlips();
    } catch (ex) {
      setErr(ex.message);
    }
  }

  async function changeFilter(value) {
    setBasinFilter(value);
    setErr("");
    try {
      const data = board || (await loadBoard());
      const list = await api(
        value ? `/api/cohesion-slips?basin_id=${encodeURIComponent(value)}` : "/api/cohesion-slips"
      );
      const codeOf = new Map(data.basins.map((x) => [x.id, x.code]));
      setSlips(
        list.slips.map((s) => ({
          ...s,
          basinCode: s.basinCode || codeOf.get(s.basinId) || s.basinId,
        }))
      );
    } catch (ex) {
      setErr(ex.message);
    }
  }

  async function createSlip(e) {
    e.preventDefault();
    setErr("");
    if (!form.basinId) {
      setErr("必须选择盆");
      return;
    }
    try {
      await api("/api/cohesion-slips", {
        method: "POST",
        body: JSON.stringify({
          basinId: Number(form.basinId),
          inspectedAt: form.inspectedAt ? new Date(form.inspectedAt).toISOString() : null,
          result: form.result,
          inspector: form.inspector,
        }),
      });
      await reload();
    } catch (ex) {
      setErr(ex.message);
    }
  }

  async function voidSlip(id) {
    setErr("");
    try {
      await api(`/api/cohesion-slips/${id}/void`, { method: "POST", body: "{}" });
      await reload();
    } catch (ex) {
      setErr(ex.message);
    }
  }

  if (!board) return <div class="page">{err || "装载抽检页…"}</div>;

  return (
    <div class="page">
      <p class="sub">
        同一盆未作废条按抽检时刻取最近一张作为浸茧→缫丝中的放行依据，结论须为合格；已作废不参与。
      </p>

      <div class="filterbar">
        <label>
          按盆筛：
          <select value={basinFilter} onChange={(e) => changeFilter(e.target.value)}>
            <option value="">全部盆</option>
            {board.basins.map((b) => (
              <option value={b.id} key={b.id}>
                {b.code}（{STATUS_LABEL[b.status]}）
              </option>
            ))}
          </select>
        </label>
      </div>

      <table class="slip-table">
        <thead>
          <tr>
            <th>盆</th>
            <th>抽检时刻</th>
            <th>结论</th>
            <th>检验人</th>
            <th>作废时刻</th>
            {admin && <th>操作</th>}
          </tr>
        </thead>
        <tbody>
          {slips.length === 0 && (
            <tr>
              <td colspan={admin ? 6 : 5} class="hint">
                暂无抽检条
              </td>
            </tr>
          )}
          {slips.map((s) => (
            <tr key={s.id} class={s.voidedAt ? "voided" : ""}>
              <td>{s.basinCode}</td>
              <td>{fmtTime(s.inspectedAt)}</td>
              <td>
                <span class={`badge ${s.result}`}>{RESULT_LABEL[s.result]}</span>
              </td>
              <td>{s.inspector}</td>
              <td>{s.voidedAt ? fmtTime(s.voidedAt) : "—"}</td>
              {admin && (
                <td>
                  {s.voidedAt ? (
                    <span class="hint">已作废</span>
                  ) : (
                    <button class="voidbtn" onClick={() => voidSlip(s.id)}>
                      作废
                    </button>
                  )}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>

      {admin ? (
        <form class="slip-form" onSubmit={createSlip}>
          <h3>新建抽检条</h3>
          <label>
            盆
            <select
              value={form.basinId}
              onChange={(e) => setForm({ ...form, basinId: e.target.value })}
            >
              <option value="">请选择盆</option>
              {board.basins.map((b) => (
                <option value={b.id} key={b.id}>
                  {b.code}
                </option>
              ))}
            </select>
          </label>
          <label>
            抽检时刻
            <input
              type="datetime-local"
              value={form.inspectedAt}
              onInput={(e) => setForm({ ...form, inspectedAt: e.target.value })}
            />
          </label>
          <label>
            结论
            <select
              value={form.result}
              onChange={(e) => setForm({ ...form, result: e.target.value })}
            >
              <option value="pass">合格</option>
              <option value="slip">打滑</option>
            </select>
          </label>
          <label>
            检验人
            <input
              value={form.inspector}
              onInput={(e) => setForm({ ...form, inspector: e.target.value })}
            />
          </label>
          <button type="submit">建条</button>
        </form>
      ) : (
        <p class="hint">缫丝工只读：建条与作废仅管理员可操作。</p>
      )}

      {err && <p class="err">{err}</p>}
    </div>
  );
}

function Shell() {
  const [user, setUser] = useState(null);
  const [page, setPage] = useState("yard");
  const [bootErr, setBootErr] = useState("");

  useEffect(() => {
    if (!token()) return;
    api("/api/auth/me")
      .then((u) => setUser(u))
      .catch((e) => setBootErr(e.message));
  }, []);

  if (!user) {
    if (bootErr) clearToken();
    return <Login onOk={(u) => setUser(u)} />;
  }

  return (
    <div class="shell">
      <Topbar user={user} page={page} onNav={setPage} />
      {page === "yard" ? <Yard /> : <Inspection user={user} />}
    </div>
  );
}

render(<Shell />, document.getElementById("app"));
