import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');

test('Social App 中控展示 Chrome 插件增长复盘摘要', () => {
  const social = read('apps/openclaw-manager-src/src/components/Social/index.tsx');
  assert.match(social, /interface GrowthFeedbackData/, '需要定义增长复盘数据结构');
  assert.match(social, /growth_feedback\?: GrowthFeedbackData/, 'ops-workspace 返回体需要包含 growth_feedback');
  assert.match(social, /const activeGrowthFeedback =/, 'Social 页需要合并 workspace 与直连接口的复盘摘要');
  assert.match(social, /social\.growthFeedbackTitle/, 'Social 页需要渲染增长复盘卡片');
  assert.match(social, /growthSignals\.map/, '增长复盘卡片需要展示高信号内容列表');
});

test('桌面端 API 与 Tauri 命令代理增长复盘端点', () => {
  const api = read('apps/openclaw-manager-src/src/lib/api.ts');
  const ipc = read('apps/openclaw-manager-src/src/lib/tauri-ipc.ts');
  const rust = read('apps/openclaw-manager-src/src-tauri/src/commands/clawbot_api.rs');
  const main = read('apps/openclaw-manager-src/src-tauri/src/main.rs');
  assert.match(api, /clawbotSocialGrowthFeedback/, '前端 API wrapper 需要暴露增长复盘读取');
  assert.match(ipc, /clawbotSocialGrowthFeedback/, 'Tauri IPC wrapper 需要暴露增长复盘读取');
  assert.match(rust, /clawbot_api_social_growth_feedback/, 'Rust 命令需要代理增长复盘 REST endpoint');
  assert.match(main, /clawbot_api::clawbot_api_social_growth_feedback/, 'Tauri invoke handler 需要注册增长复盘命令');
});

test('Social App 中控提供复盘反哺待审草稿按钮', () => {
  const social = read('apps/openclaw-manager-src/src/components/Social/index.tsx');
  const api = read('apps/openclaw-manager-src/src/lib/api.ts');
  const ipc = read('apps/openclaw-manager-src/src/lib/tauri-ipc.ts');
  const rust = read('apps/openclaw-manager-src/src-tauri/src/commands/clawbot_api.rs');
  const main = read('apps/openclaw-manager-src/src-tauri/src/main.rs');
  assert.match(social, /growth_draft_action\?: GrowthDraftAction/, 'workspace 类型需要带增长反哺动作');
  assert.match(social, /handleGenerateGrowthDrafts/, 'Social 页需要触发复盘生成待审草稿');
  assert.match(social, /social\.generateGrowthDrafts/, 'Social 页需要渲染按钮文案');
  assert.match(api, /clawbotSocialGrowthDrafts/, '前端 API wrapper 需要暴露增长反哺草稿');
  assert.match(ipc, /clawbotSocialGrowthDrafts/, 'Tauri IPC wrapper 需要暴露增长反哺草稿');
  assert.match(rust, /clawbot_api_social_growth_drafts/, 'Rust 命令需要代理增长反哺草稿端点');
  assert.match(main, /clawbot_api::clawbot_api_social_growth_drafts/, 'Tauri invoke handler 需要注册增长反哺草稿命令');
});


test('Social App 中控展示 no-code 运营打法摘要', () => {
  const social = read('apps/openclaw-manager-src/src/components/Social/index.tsx');
  const zh = read('apps/openclaw-manager-src/src/i18n/zh-CN.ts');
  const en = read('apps/openclaw-manager-src/src/i18n/en-US.ts');
  assert.match(social, /interface StrategySummaryData/, 'workspace 类型需要包含策略摘要结构');
  assert.match(social, /strategy_summary\?: StrategySummaryData/, 'ops-workspace 返回体需要暴露 strategy_summary');
  assert.match(social, /activeStrategySummary/, 'Social 页需要合并插件状态里的当前策略');
  assert.match(social, /social\.strategySummaryTitle/, 'Social 页需要渲染当前运营打法摘要');
  assert.match(social, /strategyLabel/, '平台卡需要展示运营打法标签');
  assert.match(social, /growthLoop/, '平台卡需要展示增长闭环');
  assert.match(zh, /social\.strategySummaryTitle/, '中文文案需要包含运营打法摘要');
  assert.match(en, /social\.strategySummaryTitle/, '英文文案需要包含运营打法摘要');
});


test('Social App 中控可以 no-code 保存运营打法但不授权自动发布', () => {
  const social = read('apps/openclaw-manager-src/src/components/Social/index.tsx');
  const api = read('apps/openclaw-manager-src/src/lib/api.ts');
  const ipc = read('apps/openclaw-manager-src/src/lib/tauri-ipc.ts');
  const rust = read('apps/openclaw-manager-src/src-tauri/src/commands/clawbot_api.rs');
  const main = read('apps/openclaw-manager-src/src-tauri/src/main.rs');
  assert.match(social, /strategyPresetOptions/, 'Social 页需要提供 no-code 运营打法选项');
  assert.match(social, /handleStrategyUpdate/, 'Social 页需要保存当前运营打法');
  assert.match(social, /clawbotSocialStrategyUpdate/, 'Social 页保存打法需要走统一 API wrapper');
  assert.match(social, /social\.strategySaveHint/, 'UI 需要解释保存打法不会自动外发');
  assert.match(api, /\/api\/v1\/social\/extension\/strategy/, '浏览器降级模式需要调用策略更新 REST endpoint');
  assert.match(ipc, /clawbot_api_social_strategy_update/, 'Tauri IPC 需要代理策略更新命令');
  assert.match(rust, /auto_publish_enabled"\s*:\s*false/, 'Rust 代理必须固定不授权自动发布');
  assert.match(main, /clawbot_api::clawbot_api_social_strategy_update/, 'Tauri invoke handler 需要注册策略更新命令');
});

test('桌面端发布草稿必须把最终确认传到 HTTP 与 Tauri 边界', () => {
  const social = read('apps/openclaw-manager-src/src/components/Social/index.tsx');
  const api = read('apps/openclaw-manager-src/src/lib/api.ts');
  const ipc = read('apps/openclaw-manager-src/src/lib/tauri-ipc.ts');
  const rust = read('apps/openclaw-manager-src/src-tauri/src/commands/clawbot_api.rs');
  assert.match(social, /clawbotSocialDraftPublish\(pendingAction\.index, true\)/, '最终确认框确认后必须显式传 true');
  assert.match(api, /publish\?confirmed=\$\{finalConfirmed\}/, '浏览器 API 必须把最终确认写入请求参数');
  assert.match(ipc, /clawbotSocialDraftPublish = \(index: number, finalConfirmed = false\)/, 'Tauri IPC 默认必须保持未确认');
  assert.match(rust, /final_confirmed: bool/, 'Rust 命令必须接收最终确认参数');
});

test('浏览器健康探针复用环境感知 API 封装，不硬编码真实服务端口', () => {
  const header = read('apps/openclaw-manager-src/src/components/Layout/Header.tsx');
  const sidebar = read('apps/openclaw-manager-src/src/components/Layout/Sidebar.tsx');
  for (const source of [header, sidebar]) {
    assert.doesNotMatch(source, /fetch\(['"]http:\/\/127\.0\.0\.1:18790\/api\/v1\/status/, '浏览器探针不能绕过 VITE_API_PORT 和统一认证');
    assert.match(source, /clawbotFetchJson/, '浏览器探针应复用统一 API 封装');
  }
});
