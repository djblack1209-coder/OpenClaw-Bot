import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const __dirname = dirname(fileURLToPath(import.meta.url))
const popupJs = readFileSync(resolve(__dirname, '../popup.js'), 'utf8')
const popupHtml = readFileSync(resolve(__dirname, '../popup.html'), 'utf8')
const backgroundJs = readFileSync(resolve(__dirname, '../background.js'), 'utf8')

test('popup exposes schedule reminder panel without missing handlers', () => {
  assert.match(popupHtml, /id="refresh-schedule"/)
  assert.match(popupHtml, /id="schedule-list"/)
  assert.match(popupJs, /async function refreshScheduleQueue\(/)
  assert.match(popupJs, /async function scheduleDraftForLater\(/)
  assert.match(popupJs, /async function finalConfirmScheduledDraft\(/)
  assert.match(popupJs, /normalizeScheduleItems/)
  assert.match(popupJs, /socialScheduleFetch/)
})

test('popup exposes persona review pack without missing handlers', () => {
  assert.match(popupHtml, /id="refresh-review-pack"/)
  assert.match(popupHtml, /id="persona-panel"/)
  assert.match(popupHtml, /id="persona-approve"/)
  assert.match(popupHtml, /id="persona-reject"/)
  assert.match(popupJs, /async function refreshReviewPack\(/)
  assert.match(popupJs, /async function reviewPersonaDirection\(/)
  assert.match(popupJs, /normalizeReviewPack/)
  assert.match(popupJs, /socialReviewPackFetch/)
  assert.match(popupJs, /socialPersonaReview/)
})

test('background bridges schedule fetch to the local social API', () => {
  assert.match(backgroundJs, /async function fetchSocialSchedule\(/)
  assert.match(backgroundJs, /social\/extension\/schedule/)
  assert.match(backgroundJs, /msg\?\.type === 'socialScheduleFetch'/)
})

test('background bridges persona review pack and review actions', () => {
  assert.match(backgroundJs, /async function fetchSocialReviewPack\(/)
  assert.match(backgroundJs, /social\/review-pack/)
  assert.match(backgroundJs, /async function reviewSocialPersona\(/)
  assert.match(backgroundJs, /social\/persona-review/)
  assert.match(backgroundJs, /msg\?\.type === 'socialReviewPackFetch'/)
  assert.match(backgroundJs, /msg\?\.type === 'socialPersonaReview'/)
})


test('background reports page probe calibration to the local social API', () => {
  assert.match(backgroundJs, /buildPageProbeReportPayload/)
  assert.match(backgroundJs, /async function reportSocialPageProbe\(/)
  assert.match(backgroundJs, /social\/extension\/page-probe/)
})

test('popup tells the owner whether page probe calibration synced', () => {
  assert.match(popupJs, /calibrationOk/)
  assert.match(popupJs, /校准结果已同步/)
  assert.match(popupJs, /本地检测成功，但未同步中控/)
})

test('popup renders MCN trend card operating signals', () => {
  assert.match(popupJs, /content_angle/)
  assert.match(popupJs, /growth_reason/)
  assert.match(popupJs, /risk_level/)
  assert.match(popupJs, /platform_playbook/)
})

test('popup exposes content and image asset plan beside the draft editor', () => {
  assert.match(popupHtml, /id="draft-asset-plan"/)
  assert.match(popupHtml, /素材计划/)
  assert.match(popupHtml, /id="asset-cover-prompt"/)
  assert.match(popupJs, /normalizeDraftAssetPlan/)
  assert.match(popupJs, /function renderDraftAssetPlan\(/)
  assert.match(popupJs, /cover_prompt/)
  assert.match(popupJs, /safety_checklist/)
})

test('popup preview drafts include asset plans for local visual QA', () => {
  assert.match(popupJs, /content_plan:/)
  assert.match(popupJs, /image_plan:/)
  assert.match(popupJs, /platform_style:/)
  assert.match(popupJs, /format_checklist:/)
})

test('popup exposes web model relay actions without auto submitting to providers', () => {
  assert.match(popupHtml, /id="draft-web-model"/)
  assert.match(popupHtml, /网页登录额度/)
  assert.match(popupHtml, /id="web-model-copy"/)
  assert.match(popupHtml, /id="web-model-open"/)
  assert.match(popupJs, /buildWebModelRelayTask/)
  assert.match(popupJs, /function renderWebModelRelayTask\(/)
  assert.match(popupJs, /async function copyWebModelPrompt\(/)
  assert.match(popupJs, /socialWebModelOpen/)
})

test('background opens web model provider tabs but has no auto-submit path', () => {
  assert.match(backgroundJs, /function openSocialWebModel\(/)
  assert.match(backgroundJs, /chrome\.tabs\.create/)
  assert.match(backgroundJs, /msg\?\.type === 'socialWebModelOpen'/)
  assert.doesNotMatch(backgroundJs, /socialWebModelSubmit/)
})


test('popup exposes interaction scan without automatic commenting', () => {
  assert.match(popupHtml, /id="scan-interactions"/)
  assert.match(popupHtml, /id="interaction-list"/)
  assert.match(popupJs, /normalizeInteractionSignals/)
  assert.match(popupJs, /buildInteractionDraftPayload/)
  assert.match(popupJs, /async function scanInteractions\(/)
  assert.match(popupJs, /async function createDraftFromInteraction\(/)
  assert.match(popupJs, /socialInteractionScan/)
  assert.doesNotMatch(popupJs, /socialInteractionSubmit/)
})

test('background scans interactions but has no comment submit path', () => {
  assert.match(backgroundJs, /runSocialInteractionScanInPage/)
  assert.match(backgroundJs, /async function scanSocialInteractions\(/)
  assert.match(backgroundJs, /msg\?\.type === 'socialInteractionScan'/)
  assert.doesNotMatch(backgroundJs, /socialInteractionSubmit/)
})


test('popup exposes performance capture for growth feedback without publishing', () => {
  assert.match(popupHtml, /id="capture-performance"/)
  assert.match(popupHtml, /id="performance-panel"/)
  assert.match(popupJs, /normalizePerformanceSnapshot/)
  assert.match(popupJs, /buildPerformanceSnapshotPayload/)
  assert.match(popupJs, /async function capturePerformanceSnapshot\(/)
  assert.match(popupJs, /socialPerformanceScan/)
  assert.match(popupJs, /socialPerformanceRecord/)
  assert.doesNotMatch(popupJs, /socialPerformanceBoost/)
})

test('background scans and records performance but has no boost path', () => {
  assert.match(backgroundJs, /runSocialPerformanceScanInPage/)
  assert.match(backgroundJs, /async function scanSocialPerformance\(/)
  assert.match(backgroundJs, /async function recordSocialPerformance\(/)
  assert.match(backgroundJs, /msg\?\.type === 'socialPerformanceScan'/)
  assert.match(backgroundJs, /msg\?\.type === 'socialPerformanceRecord'/)
  assert.doesNotMatch(backgroundJs, /socialPerformanceBoost/)
})


test('popup exposes growth feedback recap without enabling automation', () => {
  assert.match(popupHtml, /id="refresh-growth-feedback"/)
  assert.match(popupHtml, /id="growth-panel"/)
  assert.match(popupJs, /normalizeGrowthFeedbackSummary/)
  assert.match(popupJs, /async function refreshGrowthFeedback\(/)
  assert.match(popupJs, /function renderGrowthFeedback\(/)
  assert.match(popupJs, /socialGrowthFeedbackFetch/)
  assert.doesNotMatch(popupJs, /socialGrowthFeedbackAutopublish/)
})

test('background bridges growth feedback recap but has no autopublish path', () => {
  assert.match(backgroundJs, /async function fetchSocialGrowthFeedback\(/)
  assert.match(backgroundJs, /social\/extension\/growth-feedback/)
  assert.match(backgroundJs, /msg\?\.type === 'socialGrowthFeedbackFetch'/)
  assert.doesNotMatch(backgroundJs, /socialGrowthFeedbackAutopublish/)
})

test('popup can generate review drafts from growth feedback without autopublish', () => {
  assert.match(popupHtml, /id="generate-growth-drafts"/)
  assert.match(popupHtml, /复盘生成草稿/)
  assert.match(popupJs, /async function generateGrowthDrafts\(/)
  assert.match(popupJs, /socialGrowthDraftsCreate/)
  assert.match(popupJs, /renderDraftEditor/)
  assert.doesNotMatch(popupJs, /socialGrowthDraftsAutopublish/)
})

test('background bridges growth draft generation to local social API only', () => {
  assert.match(backgroundJs, /async function createSocialGrowthDrafts\(/)
  assert.match(backgroundJs, /social\/extension\/growth-drafts/)
  assert.match(backgroundJs, /msg\?\.type === 'socialGrowthDraftsCreate'/)
  assert.doesNotMatch(backgroundJs, /socialGrowthDraftsAutopublish/)
})

test('popup and options expose no-code strategy preset without prompt editing', () => {
  const optionsHtml = readFileSync(resolve(__dirname, '../options.html'), 'utf8')
  const optionsJs = readFileSync(resolve(__dirname, '../options.js'), 'utf8')
  assert.match(optionsHtml, /id="strategy-preset"/)
  assert.match(optionsHtml, /一键选择 MCN 风格/)
  assert.match(optionsJs, /STRATEGY_PRESET_OPTIONS/)
  assert.match(optionsJs, /strategyPreset/)
  assert.match(popupHtml, /id="strategy-preset"/)
  assert.match(popupJs, /STRATEGY_PRESET_OPTIONS/)
  assert.match(popupJs, /growth_loop/)
})

test('popup and options sync backend no-code strategy into local Chrome settings', () => {
  const optionsJs = readFileSync(resolve(__dirname, '../options.js'), 'utf8')
  assert.match(backgroundJs, /async function fetchSocialExtensionStatus\(/)
  assert.match(backgroundJs, /social\/extension\/status/)
  assert.match(backgroundJs, /syncSocialSettingsFromStatus/)
  assert.match(backgroundJs, /chrome\.storage\.local\.set\(\{ socialSettings: syncedSettings \}\)/)
  assert.match(backgroundJs, /msg\?\.type === 'socialStatusFetch'/)
  assert.match(popupJs, /async function refreshCoreStrategySettings\(/)
  assert.match(popupJs, /socialStatusFetch/)
  assert.match(popupJs, /打法已同步/)
  assert.match(optionsJs, /async function refreshCoreStrategySettings\(/)
  assert.match(optionsJs, /socialStatusFetch/)
  assert.match(optionsJs, /已从 OpenEverything 中控同步当前运营打法/)
})

test('options page wraps credential fields in a real form for browser UX', () => {
  const optionsHtml = readFileSync(resolve(__dirname, '../options.html'), 'utf8')
  const optionsJs = readFileSync(resolve(__dirname, '../options.js'), 'utf8')
  assert.match(optionsHtml, /<form[^>]+id="social-settings-form"/)
  assert.match(optionsHtml, /<input id="token" type="password" autocomplete="off"/)
  assert.match(optionsHtml, /<button id="save" type="submit"/)
  assert.match(optionsJs, /fields\.form\.addEventListener\('submit'/)
  assert.match(optionsJs, /event\.preventDefault\(\)/)
})

test('repository includes a real-browser social pilot smoke script for all supported platforms', () => {
  const smokeScript = readFileSync(resolve(__dirname, '../test/social-browser-smoke.mjs'), 'utf8')
  assert.match(smokeScript, /PLATFORM_SCENARIOS/)
  assert.match(smokeScript, /https:\/\/x\.com\/home/)
  assert.match(smokeScript, /https:\/\/www\.xiaohongshu\.com\/explore/)
  assert.match(smokeScript, /https:\/\/www\.goofish\.com\/item\?id=1/)
  assert.match(smokeScript, /runSocialFieldPlanInPage/)
  assert.match(smokeScript, /runSocialPageContextScanInPage/)
  assert.match(smokeScript, /contextResult\.ready/)
  assert.match(smokeScript, /runPopupPreviewSmoke/)
  assert.match(smokeScript, /scan-page-context/)
  assert.match(smokeScript, /page-context-panel/)
  assert.match(smokeScript, /social-pilot-popup-context-20260624\.png/)
  assert.match(smokeScript, /publishClicked === false/)
  assert.match(smokeScript, /output\/playwright\/social-pilot-browser-smoke-20260624/)
})



test('popup exposes current page context scan panel for hotspot draft creation', () => {
  assert.match(popupHtml, /id="scan-page-context"/)
  assert.match(popupHtml, /id="page-context-panel"/)
  assert.match(popupHtml, /当前页热点\/上下文/)
  assert.match(popupJs, /async function scanPageContext\(/)
  assert.match(popupJs, /function renderPageContextPanel\(/)
  assert.match(popupJs, /socialPageContextScan/)
  assert.match(popupJs, /根据当前页上下文生成待审草稿/)
})

test('background bridges current page context scan without publishing', () => {
  assert.match(backgroundJs, /async function scanSocialPageContext\(/)
  assert.match(backgroundJs, /runSocialPageContextScanInPage/)
  assert.match(backgroundJs, /msg\?\.type === 'socialPageContextScan'/)
  assert.doesNotMatch(backgroundJs, /socialPageContextPublish/)
})

test('background uses the shared page context runner for draft creation', () => {
  assert.match(backgroundJs, /runSocialPageContextScanInPage/)
  assert.match(backgroundJs, /func: runSocialPageContextScanInPage/)
  assert.match(backgroundJs, /action: 'scan_page_context'/)
})
