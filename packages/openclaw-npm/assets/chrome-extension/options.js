import { deriveRelayToken } from './background-utils.js'
import { classifyRelayCheckException, classifyRelayCheckResponse } from './options-validation.js'
import {
  AUTOMATION_LEVELS,
  CONTENT_MODEL_OPTIONS,
  DEFAULT_SOCIAL_SETTINGS,
  IMAGE_MODEL_OPTIONS,
  INTERACTION_LEVELS,
  PERSONA_TAG_OPTIONS,
  STRATEGY_PRESET_OPTIONS,
  TREND_SOURCE_OPTIONS,
  mergeSocialSettings,
  syncSocialSettingsFromStatus,
} from './social-core.js'

const DEFAULT_PORT = 18792

const fields = {
  form: document.getElementById('social-settings-form'),
  port: document.getElementById('port'),
  token: document.getElementById('token'),
  relayUrl: document.getElementById('relay-url'),
  strategyPreset: document.getElementById('strategy-preset'),
  personaTags: document.getElementById('persona-tags'),
  automationLevel: document.getElementById('automation-level'),
  interactionLevel: document.getElementById('interaction-level'),
  contentModel: document.getElementById('content-model'),
  imageModel: document.getElementById('image-model'),
  apiBaseUrl: document.getElementById('api-base-url'),
  trendSources: document.getElementById('trend-sources'),
  save: document.getElementById('save'),
  reset: document.getElementById('reset'),
  status: document.getElementById('status'),
}

const PREVIEW_STORAGE_KEY = 'openclawSocialPilotPreview'

function hasChromeStorage() {
  return Boolean(globalThis.chrome?.storage?.local)
}

function hasChromeRuntime() {
  return Boolean(globalThis.chrome?.runtime?.sendMessage)
}

async function storageGet(keys) {
  if (hasChromeStorage()) return await chrome.storage.local.get(keys)
  try {
    return JSON.parse(globalThis.localStorage?.getItem(PREVIEW_STORAGE_KEY) || '{}')
  } catch {
    return {}
  }
}

async function storageSet(values) {
  if (hasChromeStorage()) {
    await chrome.storage.local.set(values)
    return
  }
  const existing = await storageGet([])
  globalThis.localStorage?.setItem(PREVIEW_STORAGE_KEY, JSON.stringify({ ...existing, ...values }))
}

function clampPort(value) {
  const n = Number.parseInt(String(value || ''), 10)
  if (!Number.isFinite(n)) return DEFAULT_PORT
  if (n <= 0 || n > 65535) return DEFAULT_PORT
  return n
}

function updateRelayUrl(port) {
  fields.relayUrl.textContent = `http://127.0.0.1:${port}/`
}

function setStatus(kind, message) {
  fields.status.dataset.kind = kind || ''
  fields.status.textContent = message || ''
}

function optionEntriesToSelect(select, entries) {
  select.innerHTML = ''
  for (const [value, label] of Object.entries(entries)) {
    const option = document.createElement('option')
    option.value = value
    option.textContent = label
    select.appendChild(option)
  }
}

function renderCheckboxGroup(container, name, entries, selectedValues) {
  container.innerHTML = ''
  const selected = new Set(selectedValues || [])
  const pairs = Array.isArray(entries) ? entries.map((value) => [value, value]) : Object.entries(entries)
  for (const [value, label] of pairs) {
    const wrapper = document.createElement('label')
    wrapper.className = 'chip'
    const input = document.createElement('input')
    input.type = 'checkbox'
    input.name = name
    input.value = value
    input.checked = selected.has(value)
    const text = document.createElement('span')
    text.textContent = label
    wrapper.append(input, text)
    container.appendChild(wrapper)
  }
}

function selectedCheckboxValues(name) {
  return Array.from(document.querySelectorAll(`input[name="${name}"]:checked`)).map((input) => input.value)
}

function renderSocialSettings(settings) {
  renderCheckboxGroup(fields.personaTags, 'personaTags', PERSONA_TAG_OPTIONS, settings.personaTags)
  renderCheckboxGroup(fields.trendSources, 'trendSources', TREND_SOURCE_OPTIONS, settings.trendSources)
  optionEntriesToSelect(fields.strategyPreset, STRATEGY_PRESET_OPTIONS)
  optionEntriesToSelect(fields.automationLevel, AUTOMATION_LEVELS)
  optionEntriesToSelect(fields.interactionLevel, INTERACTION_LEVELS)
  optionEntriesToSelect(fields.contentModel, CONTENT_MODEL_OPTIONS)
  optionEntriesToSelect(fields.imageModel, IMAGE_MODEL_OPTIONS)
  fields.strategyPreset.value = settings.strategyPreset
  fields.automationLevel.value = settings.automationLevel
  fields.interactionLevel.value = settings.interactionLevel
  fields.contentModel.value = settings.contentModel
  fields.imageModel.value = settings.imageModel
  fields.apiBaseUrl.value = settings.apiBaseUrl
}

function readSocialSettings() {
  return mergeSocialSettings({
    personaTags: selectedCheckboxValues('personaTags'),
    strategyPreset: fields.strategyPreset.value,
    trendSources: selectedCheckboxValues('trendSources'),
    automationLevel: fields.automationLevel.value,
    interactionLevel: fields.interactionLevel.value,
    contentModel: fields.contentModel.value,
    imageModel: fields.imageModel.value,
    apiBaseUrl: fields.apiBaseUrl.value,
  })
}

async function checkRelayReachable(port, token) {
  const url = `http://127.0.0.1:${port}/json/version`
  const trimmedToken = String(token || '').trim()
  if (!trimmedToken) {
    setStatus('ok', '社媒设置已保存；Browser Relay token 未填写，跳过 Relay 连通性检查。')
    return
  }
  if (!hasChromeRuntime()) {
    setStatus('ok', '预览模式：社媒设置已保存；安装为 Chrome 插件后会检查 Relay 连通性。')
    return
  }
  try {
    const relayToken = await deriveRelayToken(trimmedToken, port)
    // 通过后台 service worker 发请求，避免自定义 Header 触发页面侧 CORS 预检。
    const res = await chrome.runtime.sendMessage({
      type: 'relayCheck',
      url,
      token: relayToken,
    })
    const result = classifyRelayCheckResponse(res, port)
    if (result.action === 'throw') throw new Error(result.error)
    setStatus(result.kind, `社媒设置已保存；${result.message}`)
  } catch (err) {
    const result = classifyRelayCheckException(err, port)
    setStatus(result.kind, `社媒设置已保存；${result.message}`)
  }
}

async function refreshCoreStrategySettings(currentSettings) {
  const settings = mergeSocialSettings(currentSettings || readSocialSettings())
  if (!hasChromeRuntime()) return settings
  try {
    const result = await chrome.runtime.sendMessage({
      type: 'socialStatusFetch',
      payload: { settings },
    })
    if (!result?.ok) return settings
    const synced = result.settings
      ? mergeSocialSettings(result.settings)
      : syncSocialSettingsFromStatus(settings, result.json || {})
    await storageSet({ socialSettings: synced })
    renderSocialSettings(synced)
    setStatus('ok', '已从 OpenEverything 中控同步当前运营打法；自动化权限仍保持本地安全设置。')
    return synced
  } catch {
    return settings
  }
}

async function load() {
  optionEntriesToSelect(fields.automationLevel, AUTOMATION_LEVELS)
  optionEntriesToSelect(fields.interactionLevel, INTERACTION_LEVELS)
  optionEntriesToSelect(fields.contentModel, CONTENT_MODEL_OPTIONS)
  optionEntriesToSelect(fields.imageModel, IMAGE_MODEL_OPTIONS)

  const stored = await storageGet(['relayPort', 'gatewayToken', 'socialSettings'])
  const port = clampPort(stored.relayPort)
  const token = String(stored.gatewayToken || '').trim()
  const settings = mergeSocialSettings(stored.socialSettings || {})
  fields.port.value = String(port)
  fields.token.value = token
  updateRelayUrl(port)
  renderSocialSettings(settings)
  await checkRelayReachable(port, token)
  await refreshCoreStrategySettings(settings)
}

async function save() {
  const port = clampPort(fields.port.value)
  const token = String(fields.token.value || '').trim()
  const socialSettings = readSocialSettings()
  await storageSet({ relayPort: port, gatewayToken: token, socialSettings })
  fields.port.value = String(port)
  fields.token.value = token
  updateRelayUrl(port)
  renderSocialSettings(socialSettings)
  await checkRelayReachable(port, token)
}

async function reset() {
  const socialSettings = mergeSocialSettings(DEFAULT_SOCIAL_SETTINGS)
  await storageSet({ socialSettings })
  renderSocialSettings(socialSettings)
  setStatus('ok', '已恢复安全默认值：只生成草稿、互动关闭、Gemini 网页额度优先。')
}

fields.form.addEventListener('submit', (event) => {
  event.preventDefault()
  void save()
})
fields.reset.addEventListener('click', () => void reset())
fields.port.addEventListener('input', () => updateRelayUrl(clampPort(fields.port.value)))
void load()
