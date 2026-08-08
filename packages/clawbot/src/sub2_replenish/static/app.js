(() => {
  "use strict";
  const csrf = document.querySelector('meta[name="jiyu-csrf"]').content;
  const dryRun = document.querySelector('meta[name="jiyu-dry-run"]').content === "true";
  const payload = document.querySelector("#payload");
  const parseButton = document.querySelector("#parse");
  const startButton = document.querySelector("#start");
  const stopButton = document.querySelector("#stop");
  const jobsElement = document.querySelector("#jobs");
  const errorElement = document.querySelector("#error");
  let timer = null;

  if (dryRun) {
    document.querySelector("#notice").textContent = "当前为演练模式：只验证格式与本地页面，不会打开登录窗口、读取钥匙串或创建 Sub2 账号。";
    startButton.textContent = "完成演练";
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      ...options,
      credentials: "same-origin",
      headers: {"Content-Type": "application/json", "X-JIYU-CSRF": csrf, ...(options.headers || {})},
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "操作失败");
    return data;
  }

  function button(label, className, handler) {
    const item = document.createElement("button");
    item.type = "button";
    item.textContent = label;
    if (className) item.className = className;
    item.addEventListener("click", handler);
    return item;
  }

  function render(state) {
    jobsElement.replaceChildren();
    jobsElement.className = state.jobs.length ? "" : "empty";
    if (!state.jobs.length) jobsElement.textContent = "尚未解析账号";
    for (const job of state.jobs) {
      const row = document.createElement("div");
      row.className = "job";
      const email = document.createElement("div");
      email.className = "email";
      email.textContent = job.email;
      const status = document.createElement("div");
      status.className = "status";
      status.textContent = job.plan_type ? `${job.status} · ${job.plan_type}` : job.status;
      const message = document.createElement("div");
      message.className = "message";
      message.textContent = job.message;
      const actions = document.createElement("div");
      actions.className = "job-actions";

      if (job.status === "group_required" && job.group_options.length) {
        const select = document.createElement("select");
        for (const option of job.group_options) {
          const element = document.createElement("option");
          element.value = String(option.id);
          element.textContent = option.name;
          select.append(element);
        }
        actions.append(select, button("确认分组", "", async () => {
          await act(`/api/jobs/${job.id}/group`, {group_id: Number(select.value)});
        }));
      }
      if (job.status === "rate_required") {
        const input = document.createElement("input");
        input.type = "number";
        input.min = "0";
        input.max = "100";
        input.step = "0.001";
        input.placeholder = job.rate_options.length ? job.rate_options.join(" / ") : "账号倍率";
        input.setAttribute("aria-label", "账号倍率");
        actions.append(input, button("确认倍率", "", async () => {
          await act(`/api/jobs/${job.id}/rate`, {rate_multiplier: Number(input.value)});
        }));
      }
      if (["pending", "oauth", "manual", "group_required", "rate_required", "creating"].includes(job.status)) {
        actions.append(button("跳过", "secondary", async () => act(`/api/jobs/${job.id}/skip`, {})));
      }
      if (["failed", "skipped"].includes(job.status)) {
        actions.append(button("重试", "secondary", async () => act(`/api/jobs/${job.id}/retry`, {})));
      }
      row.append(email, status, message, actions);
      jobsElement.append(row);
    }
    startButton.disabled = state.running || !state.jobs.some((job) => job.status === "pending");
    stopButton.disabled = !state.running;
    parseButton.disabled = state.running;
    if (state.running && timer === null) timer = window.setInterval(refresh, 1000);
    if (!state.running && timer !== null) {
      window.clearInterval(timer);
      timer = null;
    }
  }

  async function refresh() {
    try { render(await api("/api/state")); } catch (error) { errorElement.textContent = error.message; }
  }

  async function act(path, body) {
    errorElement.textContent = "";
    try { render(await api(path, {method: "POST", body: JSON.stringify(body)})); }
    catch (error) { errorElement.textContent = error.message; }
  }

  parseButton.addEventListener("click", async () => {
    await act("/api/parse", {raw: payload.value, target_pool: "self_hosted"});
    payload.value = "";
  });
  startButton.addEventListener("click", async () => act("/api/start", {}));
  stopButton.addEventListener("click", async () => act("/api/stop", {}));
  refresh();
})();
