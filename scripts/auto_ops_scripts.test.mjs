import assert from 'node:assert/strict';
import { access, readFile } from 'node:fs/promises';
import { constants } from 'node:fs';
import { test } from 'node:test';

const scripts = [
  ['scripts/auto_health_check.sh', ['--json', 'OPENCLAW', 'cc_zhongzhuan_readiness_audit.mjs']],
  ['scripts/auto_recovery.sh', ['--dry-run', 'make cc-seller-auto', 'launchctl']],
  ['scripts/local_backup.sh', ['OPENCLAW_BACKUP_DIR', 'tar', '30']],
  ['scripts/disaster_recovery.sh', ['--from-r2', '--dry-run', 'restore']],
  ['scripts/tauri_build_install.sh', ['openclaw-app-backup', 'restore_previous_apps', 'npm run tauri:build']],
];

test('ops automation scripts exist, are executable, and expose safe modes', async () => {
  for (const [file, requiredText] of scripts) {
    await access(file, constants.X_OK);
    const content = await readFile(file, 'utf8');
    assert.match(content, /^#!\/usr\/bin\/env bash/);
    for (const text of requiredText) {
      assert.ok(content.includes(text), `${file} should mention ${text}`);
    }
  }
});

test('health check validates required runtimes and distinguishes disabled optional services', async () => {
  const content = await readFile('scripts/auto_health_check.sh', 'utf8');
  for (const required of [
    'ai.openclaw.clawbot-agent',
    'ai.openclaw.gateway',
    'ai.openclaw.xianyu',
    'ai.openclaw.intel-brief.telegram-listener',
    'ai.openclaw.cc-seller-bridge',
    'http://127.0.0.1:18790/api/v1/status',
    'http://127.0.0.1:18789/health',
    'release_ready',
    'G4F_ENABLED',
    'KIRO_GATEWAY_ENABLED',
    'OLLAMA_ENABLED',
    'IBKR_ENABLED',
  ]) {
    assert.ok(content.includes(required), `health check should enforce ${required}`);
  }
  assert.match(content, /\"\$state\" == \"running\"/);
  assert.match(content, /"disabled"/);
});

test('optional LaunchAgents fail quietly when their reproducible runtimes are absent', async () => {
  for (const file of [
    'tools/launchagents/ai.openclaw.g4f.plist',
    'tools/launchagents/ai.openclaw.kiro-gateway.plist',
  ]) {
    const content = await readFile(file, 'utf8');
    assert.match(content, /if \[\[ ! -x \"\$PYTHON\" \]\]/);
    assert.match(content, /<key>RunAtLoad<\/key>\s*<false\/>/);
  }
});

test('desktop build entry keeps a rollback copy until the new app is installed', async () => {
  const makefile = await readFile('Makefile', 'utf8');
  const script = await readFile('scripts/tauri_build_install.sh', 'utf8');
  assert.match(makefile, /tauri-build:[^\n]*\n\s+bash scripts\/tauri_build_install\.sh/);
  assert.match(script, /trap restore_previous_apps EXIT INT TERM/);
  assert.match(script, /ditto \"\$INSTALL_DIR\/\$app_name\" \"\$BACKUP_DIR\/\$app_name\"/);
  assert.ok(script.indexOf('rm -rf "$INSTALL_DIR/$app_name"') < script.indexOf('npm run tauri:build'));
  assert.ok(script.indexOf('mv "$INSTALL_TMP" "$INSTALL_APP"') < script.lastIndexOf('trap - EXIT INT TERM'));
});

test('seller bridge exposes relist-only simulation mode without delivery or confirm actions', async () => {
  const file = 'scripts/cc_zhongzhuan_seller_bridge.mjs';
  await access(file, constants.F_OK);
  const content = await readFile(file, 'utf8');
  assert.ok(content.includes("--relist-only"), 'bridge should expose relist-only mode');
  assert.ok(content.includes("--simulation-relist"), 'bridge should expose simulation relist mode');
  assert.ok(content.includes("cc-xianyu-relist/next?mode="), 'bridge should call the relist queue with an explicit mode');
  assert.ok(
    content.includes("relist_only_requires_exactly_one_xianyu_page"),
    'relist-only mode should refuse to run when more than one Xianyu page is open',
  );
  assert.ok(content.includes("online_verified"), 'bridge should mark already-online product pages as verified');
  assert.ok(content.includes("deliveries: []"), 'relist-only result should not run delivery actions');
  assert.ok(content.includes("confirms: []"), 'relist-only result should not run confirm-shipment actions');
});
