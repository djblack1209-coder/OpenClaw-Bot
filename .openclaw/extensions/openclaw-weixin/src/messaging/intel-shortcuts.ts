/** Route retired news entrypoints to the existing local Intel bridge. */
export function isLegacyNewsShortcut(text: string): boolean {
  const cleaned = String(text ?? "").trim();
  return /^104(?:\s+.*)?$/.test(cleaned)
    || /^(?:\/news|(?:帮我|给我|请|麻烦|我想|想要)?(?:看看|查看|看一下|查一下|看|来个|来条|打开)?(?:今天的?|今日的?)?(?:新闻|科技早报|早报|今日新闻|最新消息|今天新闻)(?:吧|啊|呢|呀|一下|看看)?[。！!?？]?)$/i.test(cleaned);
}

export const LEGACY_NEWS_BRIDGE_UNAVAILABLE = "科技早报已归并至 Global Intelligence Bot。当前入口暂不可用，请打开你已添加的 Global Intelligence Bot，使用 /today、/ai 或 /market。";

export function shouldHandleIntelBriefShortcut(text: string): boolean {
  const cleaned = String(text ?? "").trim();
  if (!cleaned) return false;
  if (isLegacyNewsShortcut(cleaned)) return true;
  if (/^70[0-8](\s+.+)?$/.test(cleaned)) return true;
  const exactShortcuts = new Set([
    "菜单", "帮助", "help", "今日简报", "看今日简报", "每日简报",
    "我的订阅", "订阅状态", "简报状态", "市场资金", "AI科技", "AI 科技",
    "天气预警", "推送时间", "设置时间", "添加追踪", "简报帮助", "暂停简报", "暂停",
  ]);
  if (exactShortcuts.has(cleaned)) return true;
  return ["推送时间", "设置时间", "添加追踪", "追踪"].some((prefix) => cleaned.startsWith(`${prefix} `));
}
