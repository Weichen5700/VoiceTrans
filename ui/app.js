const $ = (selector) => document.querySelector(selector);
const checks = $("#checks");
const toast = $("#toast");

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("show"), 4200);
}

async function api(path, options = {}) {
  const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "操作失敗。");
  return payload;
}

function renderChecks(data) {
  const entries = Object.entries(data.checks || {});
  checks.innerHTML = entries.map(([name, item]) => `<div class="check"><span>${name}</span><span class="status ${item.status}">${item.status}</span><small>${item.path || item.reason || item.version || ""}</small></div>`).join("");
  $("#readyBadge").textContent = data.ready_without_models ? "本機流程可使用" : "需要處理環境問題";
}

async function refreshStatus() {
  try { renderChecks(await api("/api/status")); await refreshRuns(); }
  catch (error) { showToast(error.message); }
}

async function refreshProject() {
  const data = await api("/api/project");
  if (data.project) {
    $("#projectTitle").textContent = data.project.name;
    $("#projectHint").textContent = `${data.project.language} · ${data.project.voice_code} · 資料根目錄已建立`;
    $("#projectName").value = data.project.name;
  }
}

async function refreshRuns() {
  const data = await api("/api/runs");
  if (!data.runs.length) { $("#runs").innerHTML = '<p class="muted">尚無執行紀錄。</p>'; return; }
  $("#runs").innerHTML = data.runs.map((run) => `<div class="run"><span><strong>${run.operation}</strong><br><small>${run.run_id} · ${run.summary || "進行中"}</small></span><span class="status ${run.status === "succeeded" ? "PASS" : run.status === "failed" ? "BLOCKED" : "WARNING"}">${run.status}</span></div>`).join("");
}

$("#refreshBtn").addEventListener("click", refreshStatus);
$("#diagnosisBtn").addEventListener("click", async () => {
  const data = await api("/api/runs");
  if (!data.runs.length) return showToast("目前沒有可查看的執行 Log。");
  showToast(`最近 run-id：${data.runs[0].run_id}。診斷檔位於 data/runs/<run-id>/logs/diagnosis.md。`);
});

$("#projectForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await api("/api/project", { method: "POST", body: JSON.stringify({ name: $("#projectName").value, language: $("#language").value, voice_code: $("#voiceCode").value }) });
    await refreshProject(); showToast("專案已保存。");
  } catch (error) { showToast(error.message); }
});

$("#sourceForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const action = event.submitter?.dataset.action || "register";
  try {
    const path = $("#sourcePath").value;
    const data = action === "inspect" ? await api("/api/media/inspect", { method: "POST", body: JSON.stringify({ path }) }) : await api("/api/media/register", { method: "POST", body: JSON.stringify({ path }) });
    $("#mediaResult").textContent = JSON.stringify(data, null, 2);
    showToast(action === "inspect" ? "媒體檢查完成。" : "檔案已登記，原始檔不會被覆寫。");
    await refreshRuns();
  } catch (error) { $("#mediaResult").textContent = error.message; showToast(error.message); }
});

$("#wavForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const duration = $("#durationSeconds").value;
    const data = await api("/api/media/wav", { method: "POST", body: JSON.stringify({ path: $("#sourcePath").value, start: Number($("#startSeconds").value || 0), duration: duration ? Number(duration) : null, preset: $("#preset").value }) });
    $("#wavResult").textContent = JSON.stringify(data, null, 2);
    showToast("WAV 已產生，請從結果中的本機路徑取得。");
    await refreshRuns();
  } catch (error) { $("#wavResult").textContent = error.message; showToast(error.message); }
});

Promise.all([refreshStatus(), refreshProject()]).catch((error) => showToast(error.message));
