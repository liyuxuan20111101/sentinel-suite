/* AI Tool Suite 前端逻辑：导航 / 表单收集 / API 调用 / 报告着色渲染 */
"use strict";

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];

/* ---------- 导航 ---------- */
$("#nav").addEventListener("click", (e) => {
  const btn = e.target.closest(".nav-item");
  if (!btn) return;
  $$(".nav-item").forEach((x) => x.classList.toggle("active", x === btn));
  $$(".panel").forEach((p) => p.classList.toggle("active", p.id === "panel-" + btn.dataset.tool));
  $("#result-title").textContent = btn.querySelector("b").textContent + " 输出";
});

/* ---------- DiffVerifier 模式切换 ---------- */
$$('input[name="dv-mode"]').forEach((r) => r.addEventListener("change", () => {
  const explicit = document.querySelector('input[name="dv-mode"]:checked').value === "explicit";
  $$(".dv-bak-only").forEach((x) => x.classList.toggle("hidden", explicit));
  $$(".dv-explicit-only").forEach((x) => x.classList.toggle("hidden", !explicit));
}));

/* ---------- 状态映射 ---------- */
function statusFor(code) {
  if (code === 0) return ["ok", "通过 / 一致"];
  if (code === 1) return ["bad", "发现问题"];
  if (code === 2) return ["warn", "无法判定"];
  return ["warn", "注意"];
}

/* ---------- 报告着色 ---------- */
const GOOD = ["✅", "✓", "PASS", "一致 →", "全部", "行为未变"];
const BAD = ["❌", "⛔", "✗", "FAIL", "行为不同", "一票否决"];
const WARN = ["⚠", "❓", "疑似", "无法确认", "未能核实"];
function lineClass(ln) {
  if (BAD.some((k) => ln.includes(k))) return "l-bad";
  if (GOOD.some((k) => ln.includes(k))) return "l-ok";
  if (WARN.some((k) => ln.includes(k))) return "l-warn";
  return "";
}
function renderReport(text) {
  $("#result").classList.remove("empty");
  $("#result").innerHTML = text.split("\n").map((ln) => {
    const esc = ln.replace(/&/g, "&amp;").replace(/</g, "&lt;");
    const cls = lineClass(ln);
    return cls ? `<span class="${cls}">${esc}</span>` : (esc || " ");
  }).join("\n");
}

/* ---------- 运行 ---------- */
async function runTool(tool) {
  const btn = document.querySelector(`[data-run="${tool}"]`);
  const status = $("#result-status");
  btn.disabled = true;
  status.className = "status busy";
  status.textContent = "运行中…";
  $("#result").classList.remove("empty");
  $("#result").textContent = "运行中…";

  const payload = collect(tool);
  const t0 = performance.now();
  try {
    const resp = await fetch(`/api/${tool}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    renderReport(data.report || "(空输出)");
    const [cls, label] = statusFor(data.code);
    status.className = "status " + cls;
    status.textContent = label + `（${Math.round(performance.now() - t0)}ms）`;
  } catch (err) {
    renderReport("请求失败：" + err.message + "（服务还在跑吗？）");
    status.className = "status bad";
    status.textContent = "请求失败";
  } finally {
    btn.disabled = false;
  }
}

function collect(tool) {
  if (tool === "diffverifier") {
    const explicit = document.querySelector('input[name="dv-mode"]:checked').value === "explicit";
    const base = explicit
      ? { mode: "explicit", old: $("#dv-old").value.trim(), new: $("#dv-new").value.trim(), calls: $("#dv-calls").value }
      : { mode: "bak", path: $("#dv-path").value.trim(), calls: $("#dv-calls").value };
    base.auto = $("#dv-auto").checked && !base.calls.trim();
    return base;
  }
  if (tool === "slopfirewall") {
    return { text: $("#sf-text").value, use_seeds: $("#sf-seeds").checked, no_cache: $("#sf-nocache").checked };
  }
  if (tool === "replaykit") {
    return { trace_path: $("#rk-trace").value.trim(), tools_path: $("#rk-tools").value.trim(),
             all: $("#rk-all").checked, repeat: parseInt($("#rk-repeat").value) || 1 };
  }
  if (tool === "posttrain") {
    return { text: $("#ptd-text").value, threshold: parseFloat($("#ptd-threshold").value) || 0.8, quiet: $("#ptd-quiet").checked };
  }
  if (tool === "opsbench") {
    return { case: $("#ob-case").value, answer: $("#ob-answer").value };
  }
  return {};
}

$$(".run").forEach((b) => b.addEventListener("click", () => runTool(b.dataset.run)));
document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
    const active = document.querySelector(".panel.active");
    if (active) runTool(active.id.replace("panel-", ""));
  }
});

/* ---------- OpsBench 案例列表 ---------- */
(async () => {
  try {
    const r = await fetch("/api/opsbench/cases");
    const data = await r.json();
    const sel = $("#ob-case");
    sel.innerHTML = "";
    for (const c of data.cases || []) {
      const o = document.createElement("option");
      o.value = c;
      o.textContent = c;
      sel.appendChild(o);
    }
    if (!data.cases || !data.cases.length) sel.innerHTML = '<option value="">（opsbench/cases 下没有案例）</option>';
  } catch { $("#ob-case").innerHTML = '<option value="">（服务未连接）</option>'; }
})();

$("#ob-load-example").addEventListener("click", async () => {
  const caseId = $("#ob-case").value;
  if (!caseId) return;
  try {
    const r = await fetch("/api/opsbench/example/" + encodeURIComponent(caseId));
    const data = await r.json();
    if (data.answer) $("#ob-answer").value = data.answer;
  } catch { /* 忽略：按钮无效时用户可手动粘贴 */ }
});
