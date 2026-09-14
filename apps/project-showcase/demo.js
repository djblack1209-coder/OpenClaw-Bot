"use strict";

// 这是交互式讲解模型。真实账本与调度器分别以 Python 实现和回归测试为准。
const byId = (id) => document.getElementById(id);
const pages = document.querySelectorAll("[data-page]");
pages.forEach((button) =>
  button.addEventListener("click", () => {
    pages.forEach((item) => {
      const selected = item === button;
      item.classList.toggle("active", selected);
      item.setAttribute("aria-pressed", String(selected));
      byId(item.dataset.page).hidden = !selected;
    });
  }),
);

const clocks = {
  summer: "2026-07-06T20:30:00-04:00",
  winter: "2026-01-06T19:30:00-05:00",
  late: "2026-07-07T10:01:00+08:00",
};
const businessFormat = new Intl.DateTimeFormat("sv-SE", {
  timeZone: "Asia/Singapore",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});
const claims = new Set();
let cycleCount = 0;
function businessTime() {
  return businessFormat.format(new Date(clocks[byId("clock").value]));
}
byId("clock").addEventListener("change", () => {
  byId("business-time").textContent = businessTime();
});
byId("run-cycle").addEventListener("click", () => {
  const [day, time] = businessTime().split(" ");
  const trace = byId("cycle-trace");
  if (time < "08:30" || time > "10:00") {
    trace.textContent = `SKIPPED · ${day} ${time} Asia/Singapore\n业务窗口外，不进入采集和投递。`;
    trace.classList.add("warning");
    return;
  }
  if (claims.has(day)) {
    trace.textContent = `SKIPPED · business_date_already_claimed\n${day} 已认领，重复触发不再进入管线。\n真实后端会把认领写入磁盘；本页面只使用内存示例。`;
    trace.classList.add("warning");
    return;
  }
  claims.add(day);
  cycleCount += 1;
  byId("cycle-count").textContent = String(cycleCount);
  trace.classList.remove("warning");
  trace.textContent = `CLAIMED · ${day} ${time} Asia/Singapore\n→ 模拟采集与整理\n→ 模拟投递完成（未发送任何消息）\n再次触发，观察同一业务日的去重。`;
});
byId("reset-cycle").addEventListener("click", () => {
  claims.clear();
  cycleCount = 0;
  byId("cycle-count").textContent = "0";
  byId("cycle-trace").classList.remove("warning");
  byId("cycle-trace").textContent = "示例已重置。可以再次模拟触发。";
});

// 使用整数美分，避免展示模型自身引入浮点金额误差。
let spentCents = 0;
let heldCents = 0;
let attemptCount = 0;
const usd = (cents) => `$${(cents / 100).toFixed(2)}`;
function renderBudget() {
  byId("spent").textContent = usd(spentCents);
  byId("reserved").textContent = usd(heldCents);
  byId("available").textContent = usd(10 - spentCents - heldCents);
}
byId("run-request").addEventListener("click", () => {
  const trace = byId("budget-trace");
  if (10 - spentCents - heldCents < 6) {
    trace.classList.add("warning");
    trace.textContent =
      "BLOCKED · BudgetDenied\n可预留余额不足 $0.06，在模型调用前拒绝。\n未知费用需要对账，不能因为重试而自动释放。";
    return;
  }
  if (attemptCount === 0) byId("attempts").replaceChildren();
  attemptCount += 1;
  const unknown = byId("outcome").value === "unknown";
  if (unknown) heldCents += 6;
  else spentCents += 2;
  const row = document.createElement("tr");
  [
    `demo-${String(attemptCount).padStart(2, "0")}`,
    unknown ? "unknown" : "settled",
    "$0.06",
    unknown ? "待对账" : "$0.02",
  ].forEach((text, index) => {
    const cell = document.createElement("td");
    cell.textContent = text;
    if (index === 1)
      cell.className = unknown ? "state-unknown" : "state-settled";
    row.appendChild(cell);
  });
  byId("attempts").appendChild(row);
  trace.classList.toggle("warning", unknown);
  trace.textContent = unknown
    ? "RESERVED → DISPATCHED → UNKNOWN\n超时后继续保留 $0.06 敞口。再次调用，观察预算拒绝。"
    : "RESERVED → DISPATCHED → SETTLED\n预留 $0.06，示例结算 $0.02，释放差额 $0.04。";
  renderBudget();
});
byId("reset-budget").addEventListener("click", () => {
  spentCents = heldCents = attemptCount = 0;
  const row = document.createElement("tr");
  const cell = document.createElement("td");
  cell.colSpan = 4;
  cell.className = "empty";
  cell.textContent = "示例已重置，等待下一次模拟调用。";
  row.appendChild(cell);
  byId("attempts").replaceChildren(row);
  byId("budget-trace").classList.remove("warning");
  byId("budget-trace").textContent = "示例已重置。所有金额只在当前页面内变化。";
  renderBudget();
});
