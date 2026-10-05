import { render } from "preact";
import { useEffect, useState } from "preact/hooks";
import { api, clearToken, clearUser, setToken, setUser, token, user } from "./api.js";
import "./app.css";

const STATUS_LABEL = { soaking: "浸茧", reeling: "缫丝中", reeled: "已缫完" };

function fmtWhen(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("zh-CN", { hour12: false });
}

function nowLocal() {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
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
      setUser(data.user);
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
          <input name="username" autocomplete="off" value={username} onInput={(e) => setUsername(e.target.value)} />
        </label>
        <label>
          密码
          <input name="password" type="password" autocomplete="off" value={password} onInput={(e) => setPassword(e.target.value)} />
        </label>
        <p class="hint">已预填 admin / 123456，另有 worker / 123456</p>
        <button type="submit">登录</button>
      </form>
      {err && <p class="err">{err}</p>}
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
    if (picked) {
      setPicked(data.basins.find((b) => b.id === picked.id) || data.basins[0]);
    }
  }

  useEffect(() => {
    refresh().catch((e) => setErr(e.message));
  }, []);

  if (!board) {
    return (
      <div class="yard">
        {err || "装载环盆…"}
      </div>
    );
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
      setErr(ex.message);
    }
  }

  return (
    <div>
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
          <p>
            最近抱合抽检：
            {picked.latestInspection
              ? `${picked.latestInspection.conclusion}（${picked.latestInspection.inspector} ${fmtWhen(picked.latestInspection.inspectedAt)})`
              : "无"}
          </p>
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

function Inspections({ me }) {
  const isAdmin = me.role === "admin";
  const [basins, setBasins] = useState([]);
  const [rows, setRows] = useState([]);
  const [filter, setFilter] = useState("");
  const [err, setErr] = useState("");
  const [basinId, setBasinId] = useState("");
  const [inspectedAt, setInspectedAt] = useState(nowLocal());
  const [conclusion, setConclusion] = useState("合格");

  async function refresh() {
    const board = await api("/api/board");
    setBasins(board.basins);
    const data = await api(`/api/inspections${filter ? `?basinId=${filter}` : ""}`);
    setRows(data.inspections);
  }

  useEffect(() => {
    refresh().catch((e) => setErr(e.message));
  }, [filter]);

  async function submit(e) {
    e.preventDefault();
    setErr("");
    try {
      await api("/api/inspections", {
        method: "POST",
        body: JSON.stringify({
          basinId: Number(basinId),
          inspectedAt: new Date(inspectedAt).toISOString(),
          conclusion,
        }),
      });
      setInspectedAt(nowLocal());
      await refresh();
    } catch (ex) {
      setErr(ex.message);
    }
  }

  async function voidRow(id) {
    setErr("");
    try {
      await api(`/api/inspections/${id}/void`, { method: "POST" });
      await refresh();
    } catch (ex) {
      setErr(ex.message);
    }
  }

  return (
    <div class="slips">
      <div class="slips-bar">
        <label>
          按盆筛
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="">全部盆</option>
            {basins.map((b) => (
              <option key={b.id} value={b.id}>
                {b.code}
              </option>
            ))}
          </select>
        </label>
        {!isAdmin && <span class="hint">缫丝工只能查看，登记与作废由管理员操作。</span>}
      </div>

      {isAdmin && (
        <form class="slip-form" onSubmit={submit}>
          <label>
            盆
            <select value={basinId} onChange={(e) => setBasinId(e.target.value)} required>
              <option value="">选盆</option>
              {basins.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.code}
                </option>
              ))}
            </select>
          </label>
          <label>
            抽检时刻
            <input
              type="datetime-local"
              value={inspectedAt}
              onInput={(e) => setInspectedAt(e.target.value)}
              required
            />
          </label>
          <label>
            结论
            <select value={conclusion} onChange={(e) => setConclusion(e.target.value)}>
              <option value="合格">合格</option>
              <option value="打滑">打滑</option>
            </select>
          </label>
          <button type="submit">新建抽检条</button>
        </form>
      )}

      <table class="slip-table">
        <thead>
          <tr>
            <th>盆</th>
            <th>抽检时刻</th>
            <th>结论</th>
            <th>检验人</th>
            <th>作废时刻</th>
            {isAdmin && <th>操作</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} class={r.voidedAt ? "voided" : ""}>
              <td>{r.basinCode}</td>
              <td>{fmtWhen(r.inspectedAt)}</td>
              <td class={r.conclusion === "合格" ? "verdict-pass" : "verdict-slip"}>{r.conclusion}</td>
              <td>{r.inspector}</td>
              <td>{r.voidedAt ? fmtWhen(r.voidedAt) : "—"}</td>
              {isAdmin && (
                <td>
                  {!r.voidedAt && (
                    <button onClick={() => voidRow(r.id)}>作废</button>
                  )}
                </td>
              )}
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colspan={isAdmin ? 6 : 5} class="hint">
                暂无抽检条
              </td>
            </tr>
          )}
        </tbody>
      </table>
      {err && <p class="err">{err}</p>}
    </div>
  );
}

function App() {
  const [me, setMe] = useState(user());
  const [tab, setTab] = useState("yard");
  if (!me || !token()) {
    return <Login onOk={(u) => setMe(u)} />;
  }
  return (
    <div class="yard">
      <div class="topbar">
        <div>
          <h1>江口缫丝坞</h1>
          <p>东津渡 · 改缫丝中须最近抱合抽检合格；已缫完须最近汤温 38～42℃</p>
        </div>
        <nav class="tabs">
          <button class={tab === "yard" ? "on" : ""} onClick={() => setTab("yard")}>
            环盆作业台
          </button>
          <button class={tab === "slips" ? "on" : ""} onClick={() => setTab("slips")}>
            抱合抽检
          </button>
          <button
            onClick={() => {
              clearToken();
              clearUser();
              location.reload();
            }}
          >
            退出
          </button>
        </nav>
      </div>
      {tab === "yard" ? <Yard /> : <Inspections me={me} />}
    </div>
  );
}

render(<App />, document.getElementById("app"));
