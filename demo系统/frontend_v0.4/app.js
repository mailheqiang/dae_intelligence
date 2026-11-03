/* 大鄂智能 · 报价演示系统 前端（原生 JS，无框架）。只通过 /api/* 与后端通信。 */
const $ = s => document.querySelector(s);
const h = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fmt = n => Number(n || 0).toLocaleString("zh-CN", {minimumFractionDigits: 2, maximumFractionDigits: 2});
async function api(path, method = "GET", body) {
  const r = await fetch(path, {method, headers: {"Content-Type": "application/json"}, body: body ? JSON.stringify(body) : undefined});
  const d = await r.json().catch(() => ({}));
  if (r.status === 401) { state.user = null; render(); throw new Error("未登录"); }
  if (!r.ok) throw new Error(d.error || r.statusText);
  return d;
}

const TILE_COLORS = [["#8a9a6b","#c9d2b0"],["#c9a9a6","#e9d9d6"],["#9b6b7d","#d1b3bf"],["#6f9a86","#b9d3c6"],["#7d8fa8","#c1ccdb"],["#c2a27a","#e4d3bd"],["#b8684f","#e2b8aa"],["#8c8fa0","#cfd0da"],["#a99a6a","#ddd4b2"],["#6d8a9a","#b7cbd4"],["#9c7f9a","#d3c3d1"],["#7f9a6d","#c6d6b9"],["#a5876a","#d9c7b3"],["#6b7d9a","#b8c4d6"],["#9a8a6b","#d6cbb4"]];
const state = {user: null, role: null, page: "wizard", cfg: null, ans: null, step: 0, preview: null, result: null, kb: {files: [], cur: null, content: "", mtime: null, rows: null}, history: []};

// ---------- 路由 ----------
function render() {
  const app = $("#app");
  if (!state.user) return renderLogin(app);
  const on = p => state.page === p ? "on" : "";
  const titles = {wizard: ["报价向导", "卡片式步进 · 按知识库展开部件并取价"], history: ["历史报价", "输出目录中的报价单，可载入向导继续修改"], kb: ["知识库维护", "直接读写 知识库/ 目录 · 保存前自动备份到 .bak/"], users: ["用户管理", "账号与权限"]};
  app.innerHTML = `
  <div class="top"><div class="brand"><span class="mark">鄂</span>大鄂智能</div>
    <nav><a href="#" data-p="wizard" class="${on("wizard")}">报价向导</a><a href="#" data-p="history" class="${on("history")}">历史报价</a><a href="#" data-p="kb" class="${on("kb")}">知识库</a>${state.role === "admin" ? `<a href="#" data-p="users" class="${on("users")}">用户</a>` : ""}</nav>
    <div class="spacer"></div><div class="user"><span><b>${h(state.user)}</b> · ${state.role === "admin" ? "管理员" : "用户"}</span><button id="logout">退出</button></div></div>
  <div class="main"><div class="topline"><h2>${titles[state.page][0]}</h2><span class="kicker">${titles[state.page][1]}</span></div><div id="main"></div></div>`;
  $("#logout").onclick = async () => { await api("/api/logout", "POST"); state.user = null; render(); };
  document.querySelectorAll(".top nav a").forEach(a => a.onclick = e => { e.preventDefault(); state.page = a.dataset.p; render(); });
  ({wizard: renderWizard, history: renderHistory, kb: renderKB, users: renderUsers})[state.page]($("#main"));
}

function renderLogin(app) {
  app.innerHTML = `<div class="login-wrap"><div class="login"><div class="logo"><span class="mark">鄂</span><span class="kicker">定制家具报价系统</span></div><h1>大鄂智能</h1><div class="sub">登录后进入报价向导与知识库</div>
    <label>用户名</label><input id="u" autocomplete="username"><label>密码</label><input id="p" type="password" autocomplete="current-password">
    <div class="err" id="err"></div><button class="pri" id="go">登 录</button></div></div>`;
  const go = async () => {
    try { const d = await api("/api/login", "POST", {username: $("#u").value.trim(), password: $("#p").value}); state.user = d.user; state.role = d.role; await loadConfig(); render(); }
    catch (e) { $("#err").textContent = e.message; }
  };
  $("#go").onclick = go; $("#p").onkeydown = e => { if (e.key === "Enter") go(); }; $("#u").focus();
}

async function loadConfig() { state.cfg = await api("/api/wizard/config"); }

// ---------- 向导 ----------
function newAnswers() {
  const d = state.cfg.问答配置.默认, today = new Date().toISOString().slice(0, 10);
  return {meta: {客户名: "", 客户抬头: "", 项目名: "", 项目地址: "", 报价日期: today, 订单编号: "", 生产周期: d.生产周期, 付款条件: d.付款条件, 税: d.税, 担当: d.担当},
    组织方式: "按区域", 档位: "中配", 折扣: {方式: "无", 整单折扣: 0.8, 按类别: {木作: 0.8, 门: 0.85, 收纳: 0.85, 代采: 1.15, 石材: 1.0}, 成交价: ""},
    价格口径: "牌价", 房间: [], 不含项: [], 说明: []};
}
const FLOOR_ORDER = ["地下三层", "地下二层", "地下一层", "一层", "二层", "三层", "四层", "五层", "阁楼", "楼梯间"];
function floorSort(fs) { return [...fs].sort((x, y) => ((FLOOR_ORDER.indexOf(x) + 99) % 99) - ((FLOOR_ORDER.indexOf(y) + 99) % 99) || x.localeCompare(y)); }
function sortRooms(a) { const order = state.cfg.问答配置.房间.map(x => x.名称), fo = floorSort(a._楼层 || floorsOf(a)); a.房间.sort((x, y) => fo.indexOf(x.楼层 || "一层") - fo.indexOf(y.楼层 || "一层") || order.indexOf(x.名称) - order.indexOf(y.名称)); }
function floorsOf(a) { const fs = [...new Set((a.房间 || []).map(r => r.楼层 || "一层"))]; return fs.length ? fs : ["一层"]; }
function roomLabel(a, r) { return (floorsOf(a).length > 1 || (a._楼层 || []).length > 1 ? (r.楼层 || "一层") + "·" : "") + r.名称; }
function stepList() {
  const rooms = (state.ans?.房间 || []).map(r => "房间：" + roomLabel(state.ans, r));
  return ["基本信息", "报价方式", "空间盘点", ...rooms, "部件预览", "不含项与说明", "生成报价单"];
}
function renderWizard(el) {
  if (!state.ans) state.ans = newAnswers();
  const steps = stepList(), i = state.step, a = state.ans;
  const roomIdx = i - 3, nRooms = a.房间.length;
  let body = "";
  if (i === 0) body = stepMeta(a);
  else if (i === 1) body = stepMode(a);
  else if (i === 2) body = stepRooms(a);
  else if (roomIdx >= 0 && roomIdx < nRooms) body = stepRoom(a, roomIdx);
  else if (i === 3 + nRooms) body = stepPreview(a);
  else if (i === 4 + nRooms) body = stepExclude(a);
  else body = stepBuild(a);
  state.maxStep = Math.max(state.maxStep || 0, i);
  el.innerHTML = `<div class="wiz"><div class="steps"><div class="ttl">步骤 <span class="muted" style="font-weight:400">· 点击可跳转</span></div>${steps.map((s, k) => `<span class="${k === i ? "on" : k <= state.maxStep ? "done" : "todo"}" ${k !== i && k <= state.maxStep ? `data-step="${k}"` : ""} title="${k === i ? "当前步骤" : k <= state.maxStep ? "已填写，点击跳转" : "尚未到达"}"><i>${k !== i && k <= state.maxStep ? "✓" : k + 1}</i>${h(s)}</span>`).join("")}</div>
    <div class="left">${body}</div><div class="side" id="side"></div></div>`;
  state._save = null;
  bindStep(i, roomIdx, nRooms);
  document.querySelectorAll("[data-step]").forEach(x => x.onclick = async () => { try { if (state._save) await state._save(); } catch (e) {} state.step = Number(x.dataset.step); renderWizard($("#main")); });
  renderSide();
}
function nav(prevOk = true, nextLabel = "下一步") {
  return `<div class="actions"><button id="prev" ${state.step === 0 || !prevOk ? "disabled" : ""}>← 上一步</button><div class="right"><button class="ghost" id="reset">重新开始</button><button class="pri" id="next">${nextLabel} →</button></div></div>`;
}
function bindNav(onNext) {
  state._save = onNext;
  $("#prev") && ($("#prev").onclick = () => { state.step--; renderWizard($("#main")); });
  $("#reset").onclick = () => { if (confirm("清空当前报价重新开始？")) { state.ans = newAnswers(); state.step = 0; state.preview = null; state.result = null; renderWizard($("#main")); } };
  $("#next").onclick = async () => { if (await onNext() !== false) { state.step++; renderWizard($("#main")); } };
}
function field(label, key, val, type = "text", extra = "") { return `<label><span>${h(label)}</span><input data-k="${h(key)}" type="${type}" value="${h(val)}" ${extra}></label>`; }

function stepMeta(a) {
  const m = a.meta;
  return `<div class="card"><h3>1. 基本信息</h3><p class="hint">只有客户名必填，其余有默认值，随时可改。</p>
    <div class="sec">客户与项目</div>
    <div class="grid">${field("客户名 *", "客户名", m.客户名)}${field("客户抬头（首页 xx 御中）", "客户抬头", m.客户抬头, "text", 'placeholder="默认同客户名"')}${field("项目名", "项目名", m.项目名, "text", 'placeholder="默认：客户名+全屋定制家具"')}${field("项目地址", "项目地址", m.项目地址)}</div>
    <div class="sec">单据信息</div>
    <div class="grid">${field("报价日期", "报价日期", m.报价日期, "date")}${field("订单编号", "订单编号", m.订单编号, "text", 'placeholder="默认 HTBJ+日期+001"')}${field("生产周期", "生产周期", m.生产周期)}${field("付款条件", "付款条件", m.付款条件)}${field("税", "税", m.税)}${field("担当", "担当", m.担当)}</div>
    ${nav()}</div>`;
}
function optList(name, items, cur, withDesc = true) {
  return `<div class="opts">` + items.map(o => `<label class="opt ${cur === o.值 ? "on" : ""}"><input type="radio" name="${name}" value="${h(o.值)}" ${cur === o.值 ? "checked" : ""}> <b>${h(o.值)}</b>${withDesc ? `<small>${h(o.说明)}</small>` : ""}</label>`).join("") + `</div>`;
}
function stepMode(a) {
  const w = state.cfg.问答配置;
  return `<div class="card"><h3>2. 报价方式</h3><p class="hint">三个决定性问题，决定明细表怎么分组、按哪个档位取价、首页金额怎么算。</p>
    <div class="split3"><div><b>报价组织方式</b>${optList("mode", w.组织方式, a.组织方式)}</div>
    <div><b>配置档位</b>${optList("tier", w.档位, a.档位)}</div>
    <div><b>折扣策略</b>${optList("disc", w.折扣, a.折扣.方式)}</div></div>
    <div class="sec">折扣参数与口径</div>
    <div class="row" id="discx">${field("整单折扣", "整单折扣", a.折扣.整单折扣, "number", 'step="0.01"')}${field("成交价（谈判整数）", "成交价", a.折扣.成交价, "number")}${Object.entries(a.折扣.按类别).map(([k, v]) => field(k + "折扣", "cat." + k, v, "number", 'step="0.01"')).join("")}
      <label><span>价格口径</span><select id="kj"><option ${a.价格口径 === "牌价" ? "selected" : ""}>牌价</option><option ${a.价格口径 === "销售单价" ? "selected" : ""}>销售单价</option></select></label></div>
    ${nav()}</div>`;
}
function notesCard(a) {
  const r = state.notes;
  const roomNames = state.cfg.问答配置.房间.map(x => x.名称), tpls = Object.keys(state.cfg.家具模板);
  return `<div class="card notes"><h3>粘贴现场记录（可选）</h3><p class="hint">一行一件，例如「餐边柜2*2.2，有灯带，抽屉3个」「橱柜地柜4延米」。识别后自动勾选房间、填好尺寸，识别不了的在下面指认一次，系统会记住。</p>
    <div class="split notes-split"><textarea id="notes" style="min-height:220px;font-family:inherit" placeholder="玄关柜1.18*2.2
餐边柜2*2.2，有灯带，抽屉3个
橱柜地柜4延米
国产岩板台面">${h(state.notesText || "")}</textarea>
    <div>${r ? `<table class="notes-tbl"><tr><th>原文</th><th>楼层</th><th>房间</th><th>识别为</th><th>尺寸 / 配置</th><th>状态</th></tr>
      ${r.识别.map((it, k) => `<tr class="${it.状态 === "未识别" ? "warn" : ""}"><td>${h(it.原文)}</td><td class="muted">${h(it.楼层 || "")}</td>
        <td>${it.状态 === "未识别" || it.状态 === "待补尺寸" ? `<select data-nroom="${k}">${roomNames.map(n => `<option ${n === it.房间 ? "selected" : ""}>${h(n)}</option>`).join("")}</select>` : h(it.房间 || "")}</td>
        <td>${it.状态 === "未识别" ? `<select data-ntpl="${k}"><option value="">— 选择模板 —</option>${tpls.map(t => `<option>${h(t)}</option>`).join("")}</select>` : `${h(it.模板 || "")}${it.标签 ? " · " + h(it.标签) : ""}`}</td>
        <td class="muted">${Object.entries(it.参数 || {}).filter(([k2]) => !["柜门比例", "D"].includes(k2)).map(([k2, v]) => `${h(k2)}=${h(Array.isArray(v) ? v.join(";") : v)}`).join(" ")}${(it.配件 || []).map(c => ` +${h(c.名称)}×${h(c.数量)}`).join("")}${it.说明?.length ? ` <i>${h(it.说明.join("；"))}</i>` : ""}</td>
        <td><span class="tag ${it.状态 === "ok" ? "lime" : (it.状态 === "并入" || it.状态 === "楼层") ? "" : "amber"}">${h(it.状态 === "ok" ? "✓" : it.状态)}</span></td></tr>`).join("")}</table>
      <div class="row center" style="margin-top:10px"><button class="pri" id="notes-apply">应用到向导</button><span class="muted">识别 ${r.统计.识别} · 待补尺寸 ${r.统计.待补尺寸} · 并入 ${r.统计.并入} · 未识别 ${r.统计.未识别}</span></div>` : `<div class="muted" style="padding:20px">粘贴后点"识别"</div>`}</div></div>
    <div class="row" style="margin-top:10px"><button id="notes-parse">识别</button><span class="muted">识别规则来自 知识库/简写名与商品名映射.md，可在"知识库"里维护</span></div></div>`;
}
function stepRooms(a) {
  const w = state.cfg.问答配置;
  a._楼层 = a._楼层 && a._楼层.length ? a._楼层 : floorsOf(a);
  const floors = floorSort(a._楼层);
  const multi = floors.length > 1;
  const tiles = fl => `<div class="tiles">${w.房间.map((r, k) => { const cur = a.房间.find(x => x.名称 === r.名称 && (x.楼层 || "一层") === fl); const [c1, c2] = TILE_COLORS[k % TILE_COLORS.length]; return `<label class="tile ${cur ? "on" : ""}" style="--c1:${c1};--c2:${c2}"><input type="checkbox" data-room="${h(fl)}||${h(r.名称)}" ${cur ? "checked" : ""}><div class="art"></div><span class="chk">✓</span>
      <div class="body"><b>${h(r.名称)}</b>${cur && cur.家具?.length ? `<span class="tag lime" style="margin-left:6px">${cur.家具.length} 件已录入</span>` : ""}<small>${r.家具.map(f => h(f.标签)).join(" · ")}</small></div></label>`; }).join("")}</div>`;
  return notesCard(a) + `<div class="card"><h3>3. 空间盘点</h3><p class="hint">勾选要报价的区域；每个区域下一步单独一张卡片。别墅 / 复式请先添加楼层，每层都可以有自己的客厅、卫生间等。</p>
    <div class="floors"><span class="muted">楼层：</span>${floors.map(f => `<span class="chip">${h(f)}${floors.length > 1 ? `<button class="ghost" data-rmfloor="${h(f)}" title="移除该楼层及其房间">✕</button>` : ""}</span>`).join("")}
      <select id="addfloor"><option value="">+ 添加楼层…</option>${w.楼层候选.concat(["四层", "阁楼"]).filter(f => !floors.includes(f)).map(f => `<option>${h(f)}</option>`).join("")}<option value="__custom">自定义…</option></select><input id="customfloor" placeholder="如 夹层" style="display:none;width:120px"><button id="addfloorbtn" style="display:none">添加</button></div>
    ${floors.map(fl => `${multi ? `<div class="sec">${h(fl)}</div>` : ""}${tiles(fl)}`).join("")}
    ${nav()}</div>`;
}
function paramInput(p, val) {
  const k = h(p.键);
  if (p.类型 === "bool") return `<label><span>${h(p.标签)}</span><input type="checkbox" data-pk="${k}" ${val ? "checked" : ""}></label>`;
  if (p.类型 === "select") return `<label><span>${h(p.标签)}</span><select data-pk="${k}">${p.选项.map(o => `<option ${o === val ? "selected" : ""}>${h(o)}</option>`).join("")}</select></label>`;
  if (p.类型 === "multi") return `<label style="grid-column:1/-1"><span>${h(p.标签)}</span><span class="multi">${p.选项.map(o => `<label style="flex-direction:row;align-items:center;gap:4px;color:var(--ink)"><input type="checkbox" data-pm="${k}" value="${h(o)}" ${(val || []).includes(o) ? "checked" : ""}>${h(o)}</label>`).join("")}</span></label>`;
  return `<label><span>${h(p.标签)}</span><input type="number" data-pk="${k}" value="${h(val)}"></label>`;
}
function mergeAcc(tpl, acc) {
  const base = (tpl.默认配件 || []).map(x => ({名称: x.名称, 数量: x.数量 || 0}));
  (acc || []).forEach(x => { const b = base.find(y => y.名称 === x.名称); if (b) b.数量 = x.数量; else base.push({名称: x.名称, 数量: x.数量, 单位: x.单位, 单价: x.单价}); });
  return base;
}
function accTable(f, tag) {
  const cat = state.cfg.配件目录 || [];
  const groups = {}; cat.forEach(c => (groups[c.类别] = groups[c.类别] || []).push(c));
  f.配件 = f.配件 || [];
  return `<div class="acc"><div class="acc-head"><b>配件 / 五金</b><span class="muted">数量 0 的不出行；选"自定义"时单价可留空（待定价）</span></div>
    <table class="acc-tbl"><tr><th>名称</th><th style="width:90px">数量</th><th style="width:70px">单位</th><th style="width:110px">单价</th><th style="width:70px">类别</th><th></th></tr>
    ${f.配件.map((x, k) => { const c = cat.find(y => y.名称 === x.名称 || y.键 === x.名称); return `<tr><td>${h(x.名称)}${c ? "" : ' <span class="tag amber">自定义</span>'}</td>
      <td><input type="number" min="0" data-acc="${tag}:${k}:数量" value="${h(x.数量 ?? 0)}"></td><td>${c ? h(c.单位) : `<input data-acc="${tag}:${k}:单位" value="${h(x.单位 || "套")}" style="width:60px">`}</td>
      <td>${c ? `<span class="muted">目录价${c.待定价 ? "（待定）" : ""}</span>` : `<input type="number" data-acc="${tag}:${k}:单价" value="${h(x.单价 ?? "")}" placeholder="留空=待定价" style="width:100px">`}</td>
      <td class="muted">${h(c ? c.类别 : (x.类别 || "木作"))}</td><td><button class="ghost" data-accrm="${tag}:${k}">✕</button></td></tr>`; }).join("")}</table>
    <div class="row center" style="margin-top:6px"><select data-accsel="${tag}"><option value="">+ 从目录添加…</option>${Object.entries(groups).map(([g, list]) => `<optgroup label="${h(g)}">${list.map(c => `<option value="${h(c.名称)}">${h(c.名称)}（${h(c.单位)}）</option>`).join("")}</optgroup>`).join("")}<option value="__custom">✎ 自定义配件…</option></select>
    <input data-acccustom="${tag}" placeholder="自定义名称" style="display:none;width:160px"><button data-accadd="${tag}" style="display:none">加入</button></div></div>`;
}
function stepRoom(a, idx) {
  const room = a.房间[idx], w = state.cfg.问答配置, tpls = state.cfg.家具模板;
  const cands = (w.房间.find(r => r.名称 === room.名称) || {家具: []}).家具;
  room.家具 = room.家具 || [];
  const blocks = cands.map((c, ci) => {
    const inst = room.家具.find(f => f._cand === ci);
    const tpl = tpls[c.模板]; if (!tpl) return "";
    const vals = Object.fromEntries(tpl.参数.map(p => [p.键, inst ? inst.参数[p.键] : (c.参数?.[p.键] ?? p.默认)]));
    return `<div class="furn ${inst ? "on" : ""} ${inst?._待补尺寸 ? "need" : ""}" data-ci="${ci}"><label><input type="checkbox" data-fc="${ci}" ${inst ? "checked" : ""}> <b>${h(c.标签)}</b> <span class="tag">${h(c.模板)}</span>${inst?._来源 ? ` <span class="muted" style="font-size:12px">← ${h(inst._来源)}</span>` : ""}${inst?._待补尺寸 ? ' <span class="tag amber">待补尺寸</span>' : ""} <span class="desc">${h(tpl.说明)}</span></label>
      ${inst ? `<div class="params">${tpl.参数.map(p => paramInput(p, vals[p.键])).join("")}</div>${tpl.支持配件 ? accTable(inst, "c" + ci) : ""}` : ""}</div>`;
  }).join("");
  const extra = room.家具.filter(f => f._cand === undefined).map((f, k) => {
    const tpl = tpls[f.模板];
    return `<div class="furn on ${f._待补尺寸 ? "need" : ""}" data-ex="${k}"><label><b>${h(f.标签)}</b> <span class="tag">${h(f.模板)}</span>${f._来源 ? ` <span class="muted" style="font-size:12px">← ${h(f._来源)}</span>` : ""}${f._待补尺寸 ? ' <span class="tag amber">待补尺寸</span>' : ""} <span class="desc"><button class="ghost" data-rm="${k}">移除</button></span></label>
      <div class="params">${tpl.参数.map(p => paramInput(p, f.参数[p.键] ?? p.默认)).join("")}</div>${tpl.支持配件 ? accTable(f, "x" + k) : ""}</div>`;
  }).join("");
  return `<div class="card"><h3>${idx + 4}. ${h(room.楼层)} · ${h(room.名称)}</h3><p class="hint">勾选需要的家具，展开后填尺寸和配置；说"标配"就保持默认值。</p>
    ${blocks}${extra}
    <div class="row" style="margin-top:14px"><label><span>添加其他家具</span><select id="addtpl"><option value="">— 选择模板 —</option>${Object.keys(tpls).map(t => `<option>${h(t)}</option>`).join("")}</select></label><button id="addbtn">添加</button></div>
    ${nav()}</div>`;
}
function stepPreview(a) {
  const p = state.preview;
  if (!p) return `<div class="card"><h3>部件预览</h3><p class="hint">正在按知识库展开部件并取价…</p></div>`;
  const s = p._摘要;
  return `<div class="card"><h3>${stepList().indexOf("部件预览") + 1}. 部件预览与取价</h3><p class="hint">按 02 拆解、04 算量、05 取价。⚠估价行可直接改单价；改数量请回到房间卡片。</p>
    ${s.警告.length ? `<div class="warn" style="padding:8px">${s.警告.map(h).join("<br>")}</div>` : ""}
    ${p.分组.map((g, gi) => `<div class="grp"><h4>${h(g.名称)} <span class="muted" style="margin-left:auto;font-weight:500" data-sub="${gi}">${fmt(g.部件.reduce((t, r) => t + qtyOf(r, g) * Number(r.单价 || 0), 0))} 元</span></h4><table><tr><th>部件</th><th>材质</th><th>尺寸</th><th>数量</th><th>单位</th><th>单价</th><th>来源</th><th>类别</th><th>备注</th></tr>
      ${g.部件.map((r, ri) => `<tr class="${/估价|未定价/.test(r.备注) ? "warn" : ""}"><td>${h(r.名称)}</td><td>${h(r.材质)}</td><td>${h(r.尺寸)}</td><td>${h(r.数量)}</td><td>${h(r.单位)}</td>
        <td><input type="number" data-price="${gi}:${ri}" value="${r.单价 == null ? "" : h(r.单价)}" placeholder="待定价" style="width:90px"></td><td class="muted">${h(r._来源)}</td><td>${h(r.类别)}</td><td>${r.备注 ? `<span class="tag amber">${h(r.备注)}</span>` : ""}</td></tr>`).join("")}</table></div>`).join("")}
    <div class="total"><span>牌价合计</span><b data-total>${fmt(s.牌价合计)} 元</b><span data-final>折后 ${fmt(s.折后金额)} 元</span><span>${s.部件行数} 行 · 估价 ${s.估价行数} 行</span></div>
    ${nav(true, "确认，下一步")}</div>`;
}
function stepExclude(a) {
  const w = state.cfg.问答配置;
  return `<div class="card"><h3>${stepList().indexOf("不含项与说明") + 1}. 不含项与说明</h3><p class="hint">写进报价单末尾，避免纠纷。</p>
    <div class="sec">不含项</div><div class="opts">${w.不含项候选.map(t => `<label class="opt ${a.不含项.includes(t) ? "on" : ""}"><input type="checkbox" data-ex="${h(t)}" ${a.不含项.includes(t) ? "checked" : ""}> ${h(t)}</label>`).join("")}</div>
    <label class="muted" style="display:block;margin:12px 0"><span>补充不含项（每行一条）</span><textarea id="exmore" style="min-height:60px">${h(a.不含项.filter(t => !w.不含项候选.includes(t)).join("\n"))}</textarea></label>
    <div class="sec">说明</div><div class="opts">${w.说明候选.map(t => `<label class="opt ${a.说明.includes(t) ? "on" : ""}"><input type="checkbox" data-note="${h(t)}" ${a.说明.includes(t) ? "checked" : ""}> ${h(t)}</label>`).join("")}</div>
    <label class="muted" style="display:block;margin:12px 0"><span>补充说明</span><textarea id="notemore" style="min-height:60px">${h(a.说明.filter(t => !w.说明候选.includes(t)).join("\n"))}</textarea></label>
    ${nav()}</div>`;
}
function stepBuild(a) {
  const s = state.preview?._摘要, r = state.result;
  return `<div class="card"><h3>${stepList().length}. 生成报价单</h3>
    ${s ? `<p>客户 <b>${h(a.meta.客户名)}</b> · ${h(a.组织方式)} · ${h(a.档位)} · 折扣：${h(a.折扣.方式)}<br>${s.分组数} 个分组 · ${s.部件行数} 行 · 牌价合计 <b>${fmt(s.牌价合计)}</b> 元 · 折后 <b>${fmt(s.折后金额)}</b> 元 · 估价 ${s.估价行数} 行</p>` : ""}
    ${r ? `<div class="sec">已生成</div><div class="files">${r.files.map(f => `<div class="file"><span class="tier">${h(f.tier)}</span><span class="name">${h(f.xlsx)}</span>
        <a href="/api/quote/download/${encodeURIComponent(f.xlsx)}"><button>下载</button></a><button class="pri" data-open="${h(f.xlsx)}">用 Excel 打开</button><button data-reveal="${h(f.xlsx)}">在 Finder 中显示</button></div>`).join("")}</div>
      <div class="row center"><input id="savedir" placeholder="另存到目录，如 ~/Desktop/报价" style="width:340px"><button id="saveas">另存</button><span id="savemsg" class="muted"></span></div>
      ${(r.学习?.新增取价键?.length || r.学习?.新增别名?.length) ? `<div class="learn"><b>已自动补充到知识库：</b>${r.学习.新增取价键.length ? `自定义配件 ${r.学习.新增取价键.length} 项（${r.学习.新增取价键.map(k => h(k.replace("自定义.", ""))).join("、")}，待填单价）` : ""}${r.学习.新增别名.length ? ` 新简写 ${r.学习.新增别名.length} 条（${r.学习.新增别名.map(h).join("、")}）` : ""} <a href="#" id="go-pending">去填单价 →</a></div>` : ""}`
      : `<div style="margin-top:12px"><button class="accent" id="build" style="padding:11px 28px">生成 Excel 报价单</button> <span class="muted" style="margin-left:10px">${a.档位 === "三档都出" ? "将生成基础 / 中配 / 高配三个文件" : "明细保留公式，Excel 打开自动计算"}</span></div>`}
    <div class="actions"><button id="prev">← 上一步</button><div class="right"><button class="ghost" id="reset">重新开始</button></div></div></div>`;
}
function readAcc(container, prev) {
  const out = (prev || []).map(x => ({...x}));
  container.querySelectorAll("[data-acc]").forEach(x => { const [, k, field] = x.dataset.acc.split(":"); if (!out[k]) return; out[k][field] = field === "数量" ? Number(x.value || 0) : field === "单价" ? (x.value === "" ? "" : Number(x.value)) : x.value; });
  return out;
}
function readParams(container, tpl) {
  const out = {};
  tpl.参数.forEach(p => {
    if (p.类型 === "bool") out[p.键] = container.querySelector(`[data-pk="${p.键}"]`).checked;
    else if (p.类型 === "multi") out[p.键] = [...container.querySelectorAll(`[data-pm="${p.键}"]:checked`)].map(x => x.value);
    else if (p.类型 === "select") out[p.键] = container.querySelector(`[data-pk="${p.键}"]`).value;
    else out[p.键] = Number(container.querySelector(`[data-pk="${p.键}"]`).value || 0);
  });
  return out;
}
function bindStep(i, roomIdx, nRooms) {
  const a = state.ans, tpls = state.cfg.家具模板;
  if (i === 0) bindNav(() => { document.querySelectorAll("[data-k]").forEach(x => a.meta[x.dataset.k] = x.value.trim()); if (!a.meta.客户名) { alert("客户名必填"); return false; } });
  else if (i === 1) {
    document.querySelectorAll(".opt input[type=radio]").forEach(x => x.onchange = () => x.closest(".split3").querySelectorAll(`input[name=${x.name}]`).forEach(y => y.closest(".opt").classList.toggle("on", y.checked)));
    bindNav(() => { a.组织方式 = $("input[name=mode]:checked").value; a.档位 = $("input[name=tier]:checked").value; a.折扣.方式 = $("input[name=disc]:checked").value;
      document.querySelectorAll("#discx [data-k]").forEach(x => a.折扣[x.dataset.k] = x.value === "" ? "" : Number(x.value));
      document.querySelectorAll('[data-k^="cat."]').forEach(x => a.折扣.按类别[x.dataset.k.slice(4)] = Number(x.value)); a.价格口径 = $("#kj").value; });
  } else if (i === 2) {
    $("#notes-parse").onclick = async () => { state.notesText = $("#notes").value; if (!state.notesText.trim()) return; state.notes = await api("/api/notes/parse", "POST", {text: state.notesText}); renderWizard($("#main")); };
    $("#notes").oninput = () => state.notesText = $("#notes").value;
    if ($("#notes-apply")) $("#notes-apply").onclick = () => {
      const r = state.notes, tplsAll = state.cfg.家具模板; a._新别名 = a._新别名 || [];
      // 用户指认的未识别行 → 补成家具，并记为新别名
      r.识别.forEach((it, k) => {
        const rs = document.querySelector(`[data-nroom="${k}"]`), ts = document.querySelector(`[data-ntpl="${k}"]`);
        if (rs && it.状态 !== "未识别") { it.房间 = rs.value; }
        if (ts && ts.value) { const label = it.原文.replace(/[\d\.\*×xX延米]+/g, "").replace(/[,，].*$/, "").trim() || ts.value;
          it.房间 = rs.value; it.模板 = ts.value; it.标签 = label; it.状态 = "待补尺寸"; it.参数 = {};
          a._新别名.push({简写: label, 房间: it.房间, 模板: it.模板, 标签: label, 参数: ""}); }
      });
      // 重新按识别结果汇总房间（保留用户已手动勾选的房间）
      const byRoom = {};
      r.识别.filter(it => it.状态 === "ok" || it.状态 === "待补尺寸").forEach(it => { const key = (it.楼层 || "一层") + "||" + it.房间; (byRoom[key] = byRoom[key] || []).push(it); });
      Object.entries(byRoom).forEach(([key, list]) => {
        const [fl, name] = key.split("||");
        let room = a.房间.find(x => x.名称 === name && (x.楼层 || "一层") === fl); if (!room) { room = {名称: name, 楼层: fl, 家具: []}; a.房间.push(room); }
        a._楼层 = [...new Set([...(a._楼层 || floorsOf(a)), fl])];
        const cands = (state.cfg.问答配置.房间.find(x => x.名称 === name) || {家具: []}).家具;
        list.forEach(it => { if (room.家具.some(f => f._来源 === it.原文)) return;
          const tpl = tplsAll[it.模板]; if (!tpl) return;
          const params = Object.fromEntries(tpl.参数.map(p => [p.键, it.参数?.[p.键] ?? p.默认]));
          // 候选里已有同名（或同模板且唯一）的条目 → 直接填值，不新建
          let ci = cands.findIndex((c, k) => c.标签 === (it.标签 || it.模板) && !room.家具.some(f => f._cand === k));
          if (ci < 0) { const same = cands.map((c, k) => [c, k]).filter(([c, k]) => c.模板 === it.模板 && !room.家具.some(f => f._cand === k)); if (same.length === 1) ci = same[0][1]; }
          const inst = {模板: it.模板, 标签: it.标签 || it.模板, 参数: params, 配件: mergeAcc(tpl, it.配件), _来源: it.原文, _待补尺寸: it.状态 === "待补尺寸"};
          if (ci >= 0) { inst._cand = ci; inst.标签 = cands[ci].标签; Object.entries(cands[ci].参数 || {}).forEach(([k, v]) => { if (!(k in (it.参数 || {}))) inst.参数[k] = v; }); }
          room.家具.push(inst); });
      });
      sortRooms(a);
      state.preview = null; renderWizard($("#main"));
    };
    const collectRooms = () => { const keep = [];
      document.querySelectorAll("[data-room]").forEach(x => { if (x.checked) { const [fl, name] = x.dataset.room.split("||"); const old = a.房间.find(r => r.名称 === name && (r.楼层 || "一层") === fl) || {名称: name, 楼层: fl, 家具: []}; old.楼层 = fl; keep.push(old); } });
      a.房间 = keep; };
    document.querySelectorAll("[data-room]").forEach(x => x.onchange = () => x.closest(".tile").classList.toggle("on", x.checked));
    $("#addfloor").onchange = () => { const v = $("#addfloor").value; if (v === "__custom") { $("#customfloor").style.display = ""; $("#addfloorbtn").style.display = ""; $("#customfloor").focus(); return; }
      if (!v) return; collectRooms(); a._楼层 = [...new Set([...(a._楼层 || []), v])]; renderWizard($("#main")); };
    $("#addfloorbtn").onclick = () => { const v = $("#customfloor").value.trim(); if (!v) return; collectRooms(); a._楼层 = [...new Set([...(a._楼层 || []), v])]; renderWizard($("#main")); };
    document.querySelectorAll("[data-rmfloor]").forEach(b => b.onclick = e => { e.preventDefault(); collectRooms(); const fl = b.dataset.rmfloor; a._楼层 = a._楼层.filter(f => f !== fl); a.房间 = a.房间.filter(r => (r.楼层 || "一层") !== fl); renderWizard($("#main")); });
    bindNav(() => { collectRooms(); if (!a.房间.length) { alert("至少选一个区域"); return false; }
      sortRooms(a); state.preview = null; });
  } else if (roomIdx >= 0 && roomIdx < nRooms) {
    const room = a.房间[roomIdx], cands = (state.cfg.问答配置.房间.find(r => r.名称 === room.名称) || {家具: []}).家具;
    const collect = () => {
      document.querySelectorAll("[data-ci]").forEach(box => { const ci = Number(box.dataset.ci), chk = box.querySelector("[data-fc]").checked, c = cands[ci];
        const idx = room.家具.findIndex(f => f._cand === ci);
        if (chk && box.querySelector(".params")) { const old = idx >= 0 ? room.家具[idx] : null; const inst = {_cand: ci, 模板: c.模板, 标签: c.标签, 参数: readParams(box, tpls[c.模板]), 配件: readAcc(box, old ? old.配件 : []), _来源: old?._来源, _待补尺寸: old?._待补尺寸}; const need = ["W", "L", "L1", "地柜"].find(k => k in inst.参数); if (inst._待补尺寸 && need && inst.参数[need]) inst._待补尺寸 = false; idx >= 0 ? room.家具[idx] = inst : room.家具.push(inst); }
        else if (chk && idx < 0) room.家具.push({_cand: ci, 模板: c.模板, 标签: c.标签, 参数: Object.fromEntries(tpls[c.模板].参数.map(p => [p.键, c.参数?.[p.键] ?? p.默认])), 配件: mergeAcc(tpls[c.模板], [])});
        else if (!chk && idx >= 0) room.家具.splice(idx, 1); });
      document.querySelectorAll("[data-ex]").forEach(box => { const f = room.家具.filter(x => x._cand === undefined)[Number(box.dataset.ex)]; if (f) { f.参数 = readParams(box, tpls[f.模板]); f.配件 = readAcc(box, f.配件); const need = ["W", "L", "L1", "地柜"].find(k => k in f.参数); if (f._待补尺寸 && need && f.参数[need]) f._待补尺寸 = false; } });
    };
    const findF = tag => tag[0] === "c" ? room.家具.find(f => f._cand === Number(tag.slice(1))) : room.家具.filter(x => x._cand === undefined)[Number(tag.slice(1))];
    document.querySelectorAll("[data-accrm]").forEach(b => b.onclick = () => { collect(); const [tag, k] = b.dataset.accrm.split(":"); const f = findF(tag); f.配件.splice(Number(k), 1); renderWizard($("#main")); });
    document.querySelectorAll("[data-accsel]").forEach(sel => sel.onchange = () => { const tag = sel.dataset.accsel; const ci = document.querySelector(`[data-acccustom="${tag}"]`), ab = document.querySelector(`[data-accadd="${tag}"]`);
      if (sel.value === "__custom") { ci.style.display = ""; ab.style.display = ""; ci.focus(); return; }
      if (!sel.value) return; collect(); const f = findF(tag); const c = (state.cfg.配件目录 || []).find(y => y.名称 === sel.value); const ex = f.配件.find(x => x.名称 === sel.value);
      if (ex) ex.数量 = (Number(ex.数量) || 0) + 1; else f.配件.push({名称: sel.value, 数量: 1, 单位: c?.单位, 类别: c?.类别}); renderWizard($("#main")); });
    document.querySelectorAll("[data-accadd]").forEach(b => b.onclick = () => { const tag = b.dataset.accadd; const name = document.querySelector(`[data-acccustom="${tag}"]`).value.trim(); if (!name) return; collect(); findF(tag).配件.push({名称: name, 数量: 1, 单位: "套", 单价: ""}); renderWizard($("#main")); });
    document.querySelectorAll("[data-fc]").forEach(x => x.onchange = () => { collect(); renderWizard($("#main")); });
    document.querySelectorAll("[data-rm]").forEach(b => b.onclick = () => { collect(); const ex = room.家具.filter(x => x._cand === undefined)[Number(b.dataset.rm)]; room.家具.splice(room.家具.indexOf(ex), 1); renderWizard($("#main")); });
    $("#addbtn").onclick = () => { const t = $("#addtpl").value; if (!t) return; collect(); room.家具.push({模板: t, 标签: t, 参数: Object.fromEntries(tpls[t].参数.map(p => [p.键, p.默认])), 配件: mergeAcc(tpls[t], [])}); renderWizard($("#main")); };
    bindNav(() => { collect(); state.preview = null; });
  } else if (i === 3 + nRooms) {
    if (!state.preview) { api("/api/quote/expand", "POST", a).then(p => { p.分组.forEach(g => g.部件.forEach(r => r._原价 = r.单价)); state.preview = p; renderWizard($("#main")); }).catch(e => alert(e.message)); return; }
    document.querySelectorAll("[data-price]").forEach(x => x.oninput = () => { const [gi, ri] = x.dataset.price.split(":").map(Number); state.preview.分组[gi].部件[ri].单价 = Number(x.value) || 0; recalcPreview(); });
    bindNav(() => { // 把改过的单价写回答案的"覆盖"
      const p = state.preview; document.querySelectorAll("[data-price]").forEach(x => { const [gi, ri] = x.dataset.price.split(":").map(Number), row = p.分组[gi].部件[ri], v = Number(x.value);
        if (v !== Number(row._原价 ?? row.单价) || f_hasOverride(a, p.分组[gi], row.名称)) { const g = p.分组[gi], room = a.房间.find(r => r.名称 === g.房间 && (r.楼层 || "一层") === (g.楼层 || "一层")), f = room.家具.find(f => (f.标签 || f.模板) === g.家具); f.覆盖 = (f.覆盖 || []).filter(o => o.名称 !== row.名称); f.覆盖.push({名称: row.名称, 单价: v}); row.单价 = v; } });
    });
  } else if (i === 4 + nRooms) {
    document.querySelectorAll("[data-ex],[data-note]").forEach(x => x.onchange = () => x.closest(".opt").classList.toggle("on", x.checked));
    bindNav(async () => { a.不含项 = [...document.querySelectorAll("[data-ex]:checked")].map(x => x.dataset.ex).concat($("#exmore").value.split("\n").map(s => s.trim()).filter(Boolean));
      a.说明 = [...document.querySelectorAll("[data-note]:checked")].map(x => x.dataset.note).concat($("#notemore").value.split("\n").map(s => s.trim()).filter(Boolean));
      state.preview = await api("/api/quote/expand", "POST", a); state.result = null; });
  } else {
    $("#prev").onclick = () => { state.step--; renderWizard($("#main")); };
    $("#reset").onclick = () => { if (confirm("清空当前报价重新开始？")) { state.ans = newAnswers(); state.step = 0; state.preview = null; state.result = null; renderWizard($("#main")); } };
    if ($("#build")) $("#build").onclick = async () => { $("#build").disabled = true; $("#build").textContent = "生成中…"; try { state.result = await api("/api/quote/build", "POST", {答案: a}); } catch (e) { alert(e.message); } renderWizard($("#main")); };
    document.querySelectorAll("[data-open]").forEach(b => b.onclick = () => api("/api/quote/open", "POST", {name: b.dataset.open}).catch(e => alert(e.message)));
    document.querySelectorAll("[data-reveal]").forEach(b => b.onclick = () => api("/api/quote/open", "POST", {name: b.dataset.reveal, reveal: true}).catch(e => alert(e.message)));
    if ($("#go-pending")) $("#go-pending").onclick = e => { e.preventDefault(); state.page = "kb"; state.kb.pending = true; render(); };
    if ($("#saveas")) $("#saveas").onclick = async () => { try { for (const f of state.result.files) { const r = await api("/api/quote/saveas", "POST", {name: f.xlsx, dir: $("#savedir").value}); if (!r.ok) throw new Error(r.error); } $("#savemsg").textContent = "已保存到 " + $("#savedir").value; } catch (e) { $("#savemsg").textContent = e.message; } };
  }
}

// ---------- 前端实时重算（改单价时右侧总价同步变化） ----------
function qtyOf(row, group) {
  const q = String(row.数量 ?? "").trim();
  if (q.startsWith("=@")) { const key = q.slice(2); return group.部件.filter(o => o !== row && (o._锚 === key || (!o._锚 && o.名称.includes(key)))).reduce((s, o) => s + (qtyOf(o, group) || 0), 0); }
  const body = q.startsWith("=") ? q.slice(1) : q;
  if (!/^[\d\.\+\-\*/\(\) ]+$/.test(body) || !body.trim()) return 0;
  try { return Number(Function('"use strict";return (' + body + ")")()) || 0; } catch (e) { return 0; }
}
function f_hasOverride(a, g, name) { const room = a.房间.find(r => r.名称 === g.房间 && (r.楼层 || "一层") === (g.楼层 || "一层")), f = room && room.家具.find(f => (f.标签 || f.模板) === g.家具); return !!(f && (f.覆盖 || []).some(o => o.名称 === name)); }
function recalcPreview() {
  const p = state.preview, a = state.ans; if (!p) return;
  let total = 0, final = 0; const d = a.折扣 || {方式: "无"}, rates = d.按类别 || {};
  p.分组.forEach((g, gi) => { let sub = 0;
    g.部件.forEach(r => { const amt = qtyOf(r, g) * Number(r.单价 || 0); sub += amt; total += amt;
      if (d.方式 === "按类别") final += amt * Number(rates[r.类别] ?? 1); });
    g._小计 = sub; const el = document.querySelector(`[data-sub="${gi}"]`); if (el) el.textContent = fmt(sub) + " 元"; });
  if (d.方式 === "整单") final = total * Number(d.整单折扣 || 1);
  else if (d.方式 === "谈判整数") final = Number(d.成交价) || total;
  else if (d.方式 !== "按类别") final = total;
  p._摘要.牌价合计 = Math.round(total * 100) / 100; p._摘要.折后金额 = Math.round(final * 100) / 100;
  const t = document.querySelector("[data-total]"); if (t) t.textContent = fmt(total) + " 元";
  const f = document.querySelector("[data-final]"); if (f) f.textContent = "折后 " + fmt(final) + " 元";
  renderSide();
}
function renderSide() {
  const a = state.ans, s = state.preview?._摘要, n = a.房间.reduce((k, r) => k + (r.家具 || []).length, 0);
  $("#side").innerHTML = `<h4>当前配置</h4><div class="cust">${h(a.meta.客户名 || "（未填客户名）")}</div><div class="muted">${h(a.组织方式)} · ${h(a.档位)} · 折扣：${h(a.折扣.方式)}</div>
    <div class="stats"><div><b>${a.房间.length}</b><span>个区域</span></div><div><b>${n}</b><span>件家具</span></div>${s ? `<div><b>${s.部件行数}</b><span>行部件</span></div><div><b>${s.估价行数}</b><span>行估价</span></div>` : ""}</div>
    ${s ? `<h4>预估金额</h4><div class="big">${fmt(s.折后金额)} 元</div><div class="muted" style="margin-bottom:10px">牌价 ${fmt(s.牌价合计)}</div>` : ""}
    <h4>区域与家具</h4><div class="rooms">${a.房间.map(r => `<div><b>${h(roomLabel(a, r))}</b> <span class="muted">${(r.家具 || []).map(f => h(f.标签 || f.模板)).join("、") || "—"}</span></div>`).join("") || '<div class="muted">尚未选择区域</div>'}</div>`;
}

// ---------- 历史 ----------
async function renderHistory(el) {
  el.innerHTML = `<div class="card muted">加载中…</div>`;
  const hs = await api("/api/quote/history");
  el.innerHTML = `<div class="card"><table><tr><th>客户</th><th>日期</th><th>方式</th><th>档位</th><th>分组</th><th>文件</th><th></th></tr>
    ${hs.map(x => `<tr><td>${h(x.客户名)}</td><td>${h(x.日期)}</td><td>${h(x.组织方式)}</td><td>${h(x.档位)}</td><td>${x.分组数}</td><td class="muted">${h(x.xlsx || x.json)}</td>
      <td style="white-space:nowrap">${x.有答案 ? `<button class="pri" data-load="${h(x.json)}">载入向导</button>` : ""} ${x.xlsx ? `<a href="/api/quote/download/${encodeURIComponent(x.xlsx)}"><button>下载</button></a><button data-open="${h(x.xlsx)}">Excel 打开</button>` : ""}</td></tr>`).join("")}</table></div>`;
  document.querySelectorAll("[data-load]").forEach(b => b.onclick = async () => { const c = await api("/api/quote/load/" + encodeURIComponent(b.dataset.load)); state.ans = c._答案; state.step = 0; state.preview = null; state.result = null; state.page = "wizard"; render(); });
  document.querySelectorAll("[data-open]").forEach(b => b.onclick = () => api("/api/quote/open", "POST", {name: b.dataset.open}));
}

// ---------- 知识库 ----------
async function renderKB(el) {
  const k = state.kb;
  if (!k.files.length) k.files = await api("/api/kb");
  const pend = await api("/api/kb/pending");
  el.innerHTML = `<div class="kb"><div class="list card"><a href="#" id="kb-pending" class="${k.pending ? "on" : ""}"><span>待定价清单</span><span class="tag ${pend.length ? "amber" : ""}">${pend.length}</span></a>${k.files.map(f => `<a href="#" data-f="${h(f.path)}" class="${k.cur === f.path ? "on" : ""}"><span>${h(f.path)}</span><span class="tag">${f.type}</span></a>`).join("")}</div>
    <div class="edit card" id="kbedit">${k.pending ? pendingView(pend) : k.cur ? "" : '<span class="muted">← 选择一个文件</span>'}</div></div>`;
  $("#kb-pending").onclick = e => { e.preventDefault(); k.pending = true; k.cur = null; renderKB(el); };
  if (k.pending) { document.querySelectorAll("[data-setprice]").forEach(b => b.onclick = async () => { const key = b.dataset.setprice; const g = t => document.querySelector(`[data-pp="${key}:${t}"]`).value;
    const r = await api("/api/kb/pending", "PUT", {键: key, 价格: {基础: g("基础"), 中配: g("中配"), 高配: g("高配")}}); if (!r.ok) alert(r.error); state.cfg = await api("/api/wizard/config"); renderKB(el); }); }
  document.querySelectorAll("[data-f]").forEach(a => a.onclick = async e => { e.preventDefault(); k.pending = false; const d = await api("/api/kb/" + encodeURIComponent(a.dataset.f).replace(/%2F/g, "/")); k.cur = d.path; k.content = d.content; k.mtime = d.mtime; k.rows = null; renderKB(el); });
  if (k.cur && !k.pending) renderEditor($("#kbedit"));
}
function pendingView(pend) {
  if (!pend.length) return `<h3>待定价清单</h3><p class="muted">没有待定价的配件。报价时用户自定义的配件会自动出现在这里。</p>`;
  return `<h3>待定价清单</h3><p class="hint">这些是报价时临时自定义、还没有单价的配件。填一个档位会自动套用到三档；填完即生效。</p>
    <table><tr><th>取价键</th><th>单位</th><th>类别</th><th>基础</th><th>中配</th><th>高配</th><th>来源</th><th></th></tr>
    ${pend.map(p => `<tr><td><b>${h(p.键.replace("自定义.", ""))}</b></td><td>${h(p.单位)}</td><td>${h(p.类别)}</td>
      ${["基础", "中配", "高配"].map(t => `<td><input type="number" data-pp="${h(p.键)}:${t}" value="${p[t] ?? ""}" style="width:90px"></td>`).join("")}
      <td class="muted">${h(p.来源)}</td><td><button class="pri" data-setprice="${h(p.键)}">保存</button></td></tr>`).join("")}</table>`;
}
function renderEditor(el) {
  const k = state.kb, type = k.cur.split(".").pop();
  const head = `<div class="kbhead"><h3>${h(k.cur)}</h3><span class="row center" style="margin:0"><span id="msg" class="muted"></span><button id="reload">重新加载</button><button class="pri" id="save">保存</button></span></div>`;
  if (type === "md") {
    el.innerHTML = head + `<div class="split"><textarea id="ta">${h(k.content)}</textarea><div class="preview" id="pv"></div></div>`;
    const pv = () => $("#pv").innerHTML = marked.parse($("#ta").value); pv(); $("#ta").oninput = pv;
    $("#save").onclick = () => saveKB($("#ta").value);
  } else if (type === "json") {
    el.innerHTML = head + `<textarea id="ta">${h(k.content)}</textarea>`;
    $("#save").onclick = () => { try { JSON.parse($("#ta").value); } catch (e) { $("#msg").textContent = "JSON 语法错误：" + e.message; return; } saveKB($("#ta").value); };
  } else {
    if (!k.rows) k.rows = parseCSV(k.content);
    const rows = k.rows;
    el.innerHTML = head + `<div style="overflow:auto;max-height:70vh"><table><tr>${rows[0].map(c => `<th>${h(c)}</th>`).join("")}<th></th></tr>
      ${rows.slice(1).map((r, ri) => `<tr>${rows[0].map((_, ci) => `<td><input data-cell="${ri}:${ci}" value="${h(r[ci] ?? "")}"></td>`).join("")}<td><button data-del="${ri}">删</button></td></tr>`).join("")}</table></div><button id="addrow" style="margin-top:8px">增加一行</button>`;
    const collect = () => document.querySelectorAll("[data-cell]").forEach(x => { const [ri, ci] = x.dataset.cell.split(":").map(Number); rows[ri + 1][ci] = x.value; });
    $("#addrow").onclick = () => { collect(); rows.push(rows[0].map(() => "")); renderEditor(el); };
    document.querySelectorAll("[data-del]").forEach(b => b.onclick = () => { collect(); rows.splice(Number(b.dataset.del) + 1, 1); renderEditor(el); });
    $("#save").onclick = () => { collect(); saveKB(toCSV(rows)); };
  }
  $("#reload").onclick = async () => { const d = await api("/api/kb/" + encodeURIComponent(k.cur).replace(/%2F/g, "/")); k.content = d.content; k.mtime = d.mtime; k.rows = null; renderEditor(el); };
}
async function saveKB(content) {
  const k = state.kb;
  try { const r = await api("/api/kb/" + encodeURIComponent(k.cur).replace(/%2F/g, "/"), "PUT", {content, mtime: k.mtime});
    if (!r.ok) { $("#msg").textContent = r.error; return; } k.mtime = r.mtime; k.content = content; $("#msg").textContent = "已保存 " + new Date().toLocaleTimeString(); state.cfg = await api("/api/wizard/config"); }
  catch (e) { $("#msg").textContent = e.message; }
}
function parseCSV(t) { const rows = []; let row = [], cell = "", q = false; t = t.replace(/^﻿/, "");
  for (let i = 0; i < t.length; i++) { const c = t[i];
    if (q) { if (c === '"') { if (t[i + 1] === '"') { cell += '"'; i++; } else q = false; } else cell += c; }
    else if (c === '"') q = true; else if (c === ",") { row.push(cell); cell = ""; } else if (c === "\n") { row.push(cell); rows.push(row); row = []; cell = ""; } else if (c !== "\r") cell += c; }
  if (cell !== "" || row.length) { row.push(cell); rows.push(row); } return rows.filter(r => r.length > 1 || r[0] !== ""); }
function toCSV(rows) { return rows.map(r => r.map(c => /[",\n]/.test(c) ? '"' + c.replace(/"/g, '""') + '"' : c).join(",")).join("\n") + "\n"; }

// ---------- 用户管理 ----------
async function renderUsers(el) {
  const us = await api("/api/users");
  el.innerHTML = `<div class="card"><table><tr><th>用户名</th><th>角色</th><th></th></tr>${us.map(u => `<tr><td>${h(u.username)}</td><td>${h(u.role)}</td><td><button data-del="${h(u.username)}">删除</button></td></tr>`).join("")}</table>
    <div class="sec">新增 / 修改密码</div><div class="row center"><input id="nu" placeholder="用户名"><input id="np" placeholder="密码" type="password"><select id="nr"><option value="user">user</option><option value="admin">admin</option></select><button class="pri" id="add">保存</button></div>
    <p class="muted">用户保存在 demo系统/data/users.json（密码为 SHA-256 哈希）。</p></div>`;
  $("#add").onclick = async () => { if (!$("#nu").value) return; await api("/api/users", "POST", {username: $("#nu").value.trim(), password: $("#np").value, role: $("#nr").value}); renderUsers(el); };
  document.querySelectorAll("[data-del]").forEach(b => b.onclick = async () => { if (confirm("删除 " + b.dataset.del + "？")) { await api("/api/users?username=" + encodeURIComponent(b.dataset.del), "DELETE"); renderUsers(el); } });
}

// ---------- 启动 ----------
(async () => { const me = await api("/api/me"); if (me.user) { state.user = me.user; state.role = me.role; await loadConfig(); } render(); })();
