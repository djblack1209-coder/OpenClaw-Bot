#!/usr/bin/env bash
# 微信控制医生：只做权限/窗口/截图可见性诊断，不发送任何消息。
set -euo pipefail

MODE=""
DEEP_PROBE="0"
OPEN_PERMISSIONS="0"
for arg in "$@"; do
  case "$arg" in
    --json)
      MODE="--json"
      ;;
    --deep)
      DEEP_PROBE="1"
      ;;
    --open-permissions)
      OPEN_PERMISSIONS="1"
      ;;
    *)
      printf '未知参数: %s\n' "$arg" >&2
      exit 64
      ;;
  esac
done
APP_PATH="/Applications/WeChat.app"
CODEX_BUNDLE_ID="com.openai.codex"
CUA_BUNDLE_ID="com.openai.sky.CUAService"
PROBE_DIR="${TMPDIR:-/tmp}/openclaw-wechat-control-doctor"
mkdir -p "$PROBE_DIR"

json_escape() {
  python3 -c 'import json,sys; print(json.dumps(sys.stdin.read().strip(), ensure_ascii=False)[1:-1])'
}

kv() {
  local key="$1"
  local value="$2"
  printf '%s=%s\n' "$key" "$value"
}

say() {
  if [[ "$MODE" != "--json" ]]; then
    printf '%s\n' "$*"
  fi
}

query_tcc_auth() {
  local service="$1"
  local client="$2"
  local db="$HOME/Library/Application Support/com.apple.TCC/TCC.db"
  if [[ ! -r "$db" ]]; then
    printf 'unreadable'
    return 0
  fi
  sqlite3 "$db" "select auth_value from access where service='$service' and client='$client' order by last_modified desc limit 1;" 2>/dev/null || true
}

probe_wechat_window() {
  local swift_file="$PROBE_DIR/list_wechat_window.swift"
  cat >"$swift_file" <<'SWIFT'
import CoreGraphics

let opts = CGWindowListOption(arrayLiteral: .optionOnScreenOnly, .excludeDesktopElements)
let windows = CGWindowListCopyWindowInfo(opts, kCGNullWindowID) as? [[String: Any]] ?? []
var best: [String: Any]? = nil
var bestArea: Double = -1
for window in windows {
    let owner = window[kCGWindowOwnerName as String] as? String ?? ""
    let name = window[kCGWindowName as String] as? String ?? ""
    if owner.contains("WeChat") || owner.contains("微信") || name.contains("微信") {
        let bounds = window[kCGWindowBounds as String] as? [String: Any] ?? [:]
        let width = bounds["Width"] as? Double ?? 0
        let height = bounds["Height"] as? Double ?? 0
        let area = width * height
        if area > bestArea {
            bestArea = area
            best = window
        }
    }
}
if let window = best {
    let owner = window[kCGWindowOwnerName as String] as? String ?? ""
    let name = window[kCGWindowName as String] as? String ?? ""
    let number = window[kCGWindowNumber as String] ?? ""
    let layer = window[kCGWindowLayer as String] ?? ""
    let alpha = window[kCGWindowAlpha as String] ?? ""
    let sharing = window[kCGWindowSharingState as String] ?? ""
    let onscreen = window[kCGWindowIsOnscreen as String] ?? ""
    let bounds = window[kCGWindowBounds as String] as? [String: Any] ?? [:]
    let x = bounds["X"] ?? ""
    let y = bounds["Y"] ?? ""
    let width = bounds["Width"] ?? ""
    let height = bounds["Height"] ?? ""
    print("owner=\(owner)")
    print("name=\(name)")
    print("number=\(number)")
    print("layer=\(layer)")
    print("alpha=\(alpha)")
    print("sharing_state=\(sharing)")
    print("onscreen=\(onscreen)")
    print("bounds=x:\(x),y:\(y),w:\(width),h:\(height)")
    exit(0)
}
print("owner=")
print("name=")
print("number=")
print("layer=")
print("alpha=")
print("sharing_state=")
print("onscreen=")
print("bounds=")
SWIFT
  swift "$swift_file" 2>/dev/null || true
}

open_permission_panes() {
  open "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture" || true
  open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility" || true
  open "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation" || true
}

probe_wechat_ax_content() {
  local swift_file="$PROBE_DIR/probe_wechat_ax_content.swift"
  cat >"$swift_file" <<'SWIFT'
import Cocoa
import ApplicationServices

func attr(_ el: AXUIElement, _ name: CFString) -> AnyObject? {
    var value: AnyObject?
    let err = AXUIElementCopyAttributeValue(el, name, &value)
    if err == .success { return value }
    return nil
}

func strAttr(_ el: AXUIElement, _ name: CFString) -> String {
    if let value = attr(el, name) { return String(describing: value) }
    return ""
}

let apps = NSWorkspace.shared.runningApplications.filter { app in
    (app.bundleIdentifier ?? "") == "com.tencent.xinWeChat" || (app.localizedName ?? "").contains("WeChat")
}

if apps.isEmpty {
    print("ax_trusted=\(AXIsProcessTrusted())")
    print("ax_window_count=0")
    print("ax_child_count=0")
    print("ax_editable_count=0")
    print("ax_content_visible=0")
    exit(0)
}

let axApp = AXUIElementCreateApplication(apps[0].processIdentifier)
let windows = attr(axApp, kAXWindowsAttribute as CFString) as? [AXUIElement] ?? []
var childCount = 0
var editableCount = 0
var visited = 0

func walk(_ el: AXUIElement, _ depth: Int) {
    if depth > 7 || visited > 600 { return }
    visited += 1
    let role = strAttr(el, kAXRoleAttribute as CFString)
    if role == "AXTextArea" || role == "AXTextField" || role == "AXComboBox" {
        editableCount += 1
    }
    let children = attr(el, kAXChildrenAttribute as CFString) as? [AXUIElement] ?? []
    childCount += children.count
    for child in children.prefix(80) {
        walk(child, depth + 1)
    }
}

for window in windows {
    walk(window, 0)
}

let contentVisible = childCount > 10 || editableCount > 0
print("ax_trusted=\(AXIsProcessTrusted())")
print("ax_window_count=\(windows.count)")
print("ax_child_count=\(childCount)")
print("ax_editable_count=\(editableCount)")
print("ax_content_visible=\(contentVisible ? 1 : 0)")
SWIFT
  swift "$swift_file" 2>/dev/null || true
}

probe_target_window_capture() {
  local window_number="$1"
  local out_file="$PROBE_DIR/wechat-window-probe.png"
  rm -f "$out_file"
  if [[ -z "$window_number" ]]; then
    printf 'window_capture_ok=0\n'
    printf 'window_capture_reason=no_window_number\n'
    return 0
  fi
  local capture_output
  capture_output="$(screencapture -x -l "$window_number" "$out_file" 2>&1 || true)"
  if [[ -s "$out_file" ]]; then
    rm -f "$out_file"
    printf 'window_capture_ok=1\n'
    printf 'window_capture_reason=ok\n'
  else
    printf 'window_capture_ok=0\n'
    if [[ -n "$capture_output" ]]; then
      printf 'window_capture_reason=%s\n' "$capture_output"
    else
      printf 'window_capture_reason=no_output_file\n'
    fi
  fi
}

probe_fullscreen_capture() {
  local out_file="$PROBE_DIR/fullscreen-probe.png"
  rm -f "$out_file"
  local capture_output
  capture_output="$(screencapture -x "$out_file" 2>&1 || true)"
  if [[ -s "$out_file" ]]; then
    rm -f "$out_file"
    printf 'fullscreen_capture_ok=1\n'
    printf 'fullscreen_capture_reason=ok\n'
  else
    printf 'fullscreen_capture_ok=0\n'
    if [[ -n "$capture_output" ]]; then
      printf 'fullscreen_capture_reason=%s\n' "$capture_output"
    else
      printf 'fullscreen_capture_reason=no_output_file\n'
    fi
  fi
}

say "== 微信控制医生：开始 =="

if [[ ! -d "$APP_PATH" ]]; then
  say "未找到 /Applications/WeChat.app。"
  kv status "wechat_app_missing"
  exit 1
fi

if [[ "$OPEN_PERMISSIONS" == "1" ]]; then
  say "诊断结束后会打开 macOS 隐私权限页面；只打开页面，不替你改系统开关。"
fi

ui_enabled="$(osascript -e 'tell application "System Events" to get UI elements enabled' 2>/dev/null || printf 'false')"
apple_events_auth="$(query_tcc_auth "kTCCServiceAppleEvents" "$CODEX_BUNDLE_ID")"
screen_capture_auth="$(query_tcc_auth "kTCCServiceScreenCapture" "$CODEX_BUNDLE_ID")"
cua_screen_capture_auth="$(query_tcc_auth "kTCCServiceScreenCapture" "$CUA_BUNDLE_ID")"
cua_apple_events_auth="$(query_tcc_auth "kTCCServiceAppleEvents" "$CUA_BUNDLE_ID")"

say "辅助功能可用: $ui_enabled"
say "Codex 自动化授权: ${apple_events_auth:-missing}"
say "Codex 屏幕读取授权记录: ${screen_capture_auth:-missing}"
say "Computer Use 辅助进程屏幕读取授权记录: ${cua_screen_capture_auth:-missing}"

say "正在把微信拉到前台并恢复窗口位置..."
osascript <<'APPLESCRIPT' >/dev/null 2>&1 || true
tell application id "com.tencent.xinWeChat"
  activate
  reopen
end tell
delay 0.5
tell application "System Events"
  tell process "WeChat"
    set visible to true
    set frontmost to true
    try
      perform action "AXRaise" of window 1
    end try
    try
      set position of window 1 to {260, 120}
      set size of window 1 to {1000, 740}
    end try
  end tell
end tell
APPLESCRIPT

front_app="$(osascript -e 'tell application "System Events" to get name of first application process whose frontmost is true' 2>/dev/null || true)"
window_probe="$(probe_wechat_window)"
sharing_state="$(printf '%s\n' "$window_probe" | awk -F= '/^sharing_state=/{print $2; exit}')"
onscreen="$(printf '%s\n' "$window_probe" | awk -F= '/^onscreen=/{print $2; exit}')"
bounds="$(printf '%s\n' "$window_probe" | awk -F= '/^bounds=/{sub(/^bounds=/,""); print; exit}')"
window_number="$(printf '%s\n' "$window_probe" | awk -F= '/^number=/{print $2; exit}')"

ax_probe="$(probe_wechat_ax_content)"
ax_trusted="$(printf '%s\n' "$ax_probe" | awk -F= '/^ax_trusted=/{print $2; exit}')"
ax_child_count="$(printf '%s\n' "$ax_probe" | awk -F= '/^ax_child_count=/{print $2; exit}')"
ax_editable_count="$(printf '%s\n' "$ax_probe" | awk -F= '/^ax_editable_count=/{print $2; exit}')"
ax_content_visible="$(printf '%s\n' "$ax_probe" | awk -F= '/^ax_content_visible=/{print $2; exit}')"

window_capture_ok="not_run"
window_capture_reason="not_run"
fullscreen_capture_ok="not_run"
fullscreen_capture_reason="not_run"
if [[ "$DEEP_PROBE" == "1" ]]; then
  window_capture_probe="$(probe_target_window_capture "$window_number")"
  window_capture_ok="$(printf '%s\n' "$window_capture_probe" | awk -F= '/^window_capture_ok=/{print $2; exit}')"
  window_capture_reason="$(printf '%s\n' "$window_capture_probe" | awk -F= '/^window_capture_reason=/{sub(/^window_capture_reason=/,""); print; exit}')"
  fullscreen_capture_probe="$(probe_fullscreen_capture)"
  fullscreen_capture_ok="$(printf '%s\n' "$fullscreen_capture_probe" | awk -F= '/^fullscreen_capture_ok=/{print $2; exit}')"
  fullscreen_capture_reason="$(printf '%s\n' "$fullscreen_capture_probe" | awk -F= '/^fullscreen_capture_reason=/{sub(/^fullscreen_capture_reason=/,""); print; exit}')"
fi

say "当前前台应用: ${front_app:-unknown}"
say "微信窗口 onscreen: ${onscreen:-unknown}"
say "微信窗口 sharing_state: ${sharing_state:-unknown}"
say "微信窗口 bounds: ${bounds:-unknown}"
say "微信辅助功能内部控件可见: ${ax_content_visible:-unknown}，输入框数量: ${ax_editable_count:-0}"
if [[ "$DEEP_PROBE" == "1" ]]; then
  say "微信单窗口截图可用: $window_capture_ok ($window_capture_reason)"
  say "全屏截图可用: $fullscreen_capture_ok ($fullscreen_capture_reason)"
fi

status="ok"
next_action="可以继续用 Computer Use 读取微信窗口。"
can_visual_control="true"
can_ax_control="true"
if [[ "$ui_enabled" != "true" ]]; then
  status="needs_accessibility_permission"
  next_action="请在 系统设置 → 隐私与安全性 → 辅助功能 允许 Codex，然后重跑本脚本。"
  can_visual_control="false"
  can_ax_control="false"
elif [[ "$front_app" != "WeChat" && "$front_app" != "微信" ]]; then
  status="wechat_not_frontmost"
  next_action="微信没有稳定到前台；请先手动点一下 Dock 里的微信，再重跑本脚本。"
  can_visual_control="false"
  can_ax_control="false"
elif [[ -z "$sharing_state" ]]; then
  status="wechat_window_not_detected"
  next_action="没有检测到微信主窗口；请手动打开微信主聊天窗口后重跑本脚本。"
  can_visual_control="false"
  can_ax_control="false"
elif [[ "$DEEP_PROBE" == "1" && "$fullscreen_capture_ok" == "0" ]]; then
  status="needs_screen_recording_permission"
  next_action="系统全屏截图失败。请在 系统设置 → 隐私与安全性 → 屏幕录制 允许 Codex/Terminal/WeChat，重启 Codex 和微信后重跑。"
  can_visual_control="false"
  can_ax_control="false"
elif [[ "$sharing_state" == "0" ]]; then
  status="blocked_by_wechat_capture_protection"
  next_action="微信窗口禁止被单窗口截图读取，且辅助功能看不到聊天输入框。不要坐标盲点发消息；建议继续用 OpenClaw Weixin 插件桥做真实入站。若要视觉接管，请先给 Codex/WeChat 屏幕录制权限，并在微信设置里关闭截图隐藏/隐私保护后重启微信。"
  can_visual_control="false"
  can_ax_control="false"
elif [[ "${ax_content_visible:-0}" != "1" || "${ax_editable_count:-0}" == "0" ]]; then
  status="wechat_ax_content_hidden"
  next_action="微信窗口能被系统看到，但聊天内部控件没有暴露给辅助功能。不要坐标盲点发消息；建议继续用 OpenClaw Weixin 插件桥做真实入站。"
  can_ax_control="false"
elif [[ "$DEEP_PROBE" == "1" && "$window_capture_ok" == "0" ]]; then
  status="blocked_by_wechat_window_capture"
  next_action="微信窗口单独截图失败，Computer Use 可能仍看不到聊天内容；建议继续用插件桥，或关闭微信隐私保护后重启微信。"
  can_visual_control="false"
elif [[ -z "$screen_capture_auth" || "$screen_capture_auth" == "unreadable" || -z "$cua_screen_capture_auth" || "$cua_screen_capture_auth" == "unreadable" ]]; then
  status="screen_recording_permission_uncertain"
  next_action="诊断未读到 Codex 或 Computer Use 辅助进程的屏幕录制授权记录；若 Computer Use 仍是白屏，请在 系统设置 → 隐私与安全性 → 屏幕录制 给 Codex、OpenAI/CUAService、WeChat 授权后重启 Codex 和微信。"
fi

say "诊断结果: $status"
say "下一步: $next_action"

if [[ "$MODE" == "--json" ]]; then
  status_json="$(printf '%s' "$status" | json_escape)"
  next_json="$(printf '%s' "$next_action" | json_escape)"
  front_json="$(printf '%s' "${front_app:-}" | json_escape)"
  bounds_json="$(printf '%s' "${bounds:-}" | json_escape)"
  window_capture_reason_json="$(printf '%s' "${window_capture_reason:-}" | json_escape)"
  fullscreen_capture_reason_json="$(printf '%s' "${fullscreen_capture_reason:-}" | json_escape)"
  cat <<JSON
{"status":"$status_json","ui_enabled":"$ui_enabled","front_app":"$front_json","apple_events_auth":"${apple_events_auth:-}","screen_capture_auth":"${screen_capture_auth:-}","cua_apple_events_auth":"${cua_apple_events_auth:-}","cua_screen_capture_auth":"${cua_screen_capture_auth:-}","wechat_onscreen":"${onscreen:-}","wechat_sharing_state":"${sharing_state:-}","wechat_bounds":"$bounds_json","wechat_window_number":"${window_number:-}","ax_trusted":"${ax_trusted:-}","ax_child_count":"${ax_child_count:-}","ax_editable_count":"${ax_editable_count:-}","ax_content_visible":"${ax_content_visible:-}","window_capture_ok":"$window_capture_ok","window_capture_reason":"$window_capture_reason_json","fullscreen_capture_ok":"$fullscreen_capture_ok","fullscreen_capture_reason":"$fullscreen_capture_reason_json","can_visual_control":"$can_visual_control","can_ax_control":"$can_ax_control","next_action":"$next_json"}
JSON
fi

if [[ "$OPEN_PERMISSIONS" == "1" ]]; then
  open_permission_panes
fi

case "$status" in
  ok|screen_recording_permission_uncertain)
    exit 0
    ;;
  *)
    exit 2
    ;;
esac
