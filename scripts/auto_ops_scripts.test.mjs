import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { access, readFile } from 'node:fs/promises';
import path from 'node:path';
import { constants } from 'node:fs';
import { test } from 'node:test';

const scripts = [
  ['scripts/auto_health_check.sh', ['--json', 'OPENCLAW', 'cc_zhongzhuan_readiness_audit.mjs', 'check_renewals.py', '30/14/7/3/1']],
  ['scripts/auto_recovery.sh', ['--dry-run', 'make cc-seller-auto', 'launchctl']],
  ['scripts/local_backup.sh', ['OPENCLAW_BACKUP_DIR', 'tar', '30']],
  ['scripts/disaster_recovery.sh', ['--from-r2', '--dry-run', 'restore']],
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

test('auto recovery is dry-run by default and requires explicit confirmation', async () => {
  const content = await readFile('scripts/auto_recovery.sh', 'utf8');
  assert.ok(content.includes('DRY_RUN=1'), 'auto recovery must default to dry-run');
  assert.ok(content.includes('--confirm'), 'real recovery must require --confirm');
  assert.ok(!content.includes('[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1'));
});

test('health check never suggests bypassing the recovery confirmation contract', async () => {
  const content = await readFile('scripts/auto_health_check.sh', 'utf8');
  assert.ok(
    content.includes('scripts/auto_recovery.sh --confirm'),
    'real recovery guidance must name the explicit --confirm flag',
  );
  assert.ok(!content.includes('去掉 --dry-run'), 'health guidance must not suggest removing a safety flag');
  assert.ok(!content.includes('scripts/auto_recovery.sh 清理旧日志'));
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
  assert.ok(
    !content.includes('clickButton:'),
    'relist inspection must never pass a click override to the page runner',
  );
});

test('seller bridge and extension advertise a read-only default contract', async () => {
  const bridge = 'scripts/cc_zhongzhuan_seller_bridge.mjs';
  const bridgeSource = await readFile(bridge, 'utf8');
  const output = execFileSync(process.execPath, [bridge, '--contract', '--json'], {
    cwd: path.resolve('.'),
    encoding: 'utf8',
  });
  const contract = JSON.parse(output);
  assert.equal(contract.ok, true);
  assert.equal(contract.defaultMode, 'read_only_watch');
  assert.equal(contract.highRiskActions.delivery, false);
  assert.equal(contract.highRiskActions.confirmShipment, false);
  assert.equal(contract.highRiskActions.relist, false);
  assert.equal(contract.oneShotHumanGateRequired, true);
  assert.equal(contract.relistMode, 'simulation_only');
  assert.ok(bridgeSource.includes('readOnlyWatch'), 'default watch should be implemented as a read-only mode');
  assert.ok(
    !bridgeSource.includes('/api/cc-operator-mode/one-shot-delivery'),
    'the browser bridge must not mint its own one-shot authorization',
  );
  assert.ok(
    bridgeSource.includes("reason: 'human_confirmation_required'"),
    'delivery-only runs must not click confirm shipment after sending a message',
  );
  assert.ok(
    bridgeSource.includes('production_relist_requires_human_confirmation'),
    'production relist must stay blocked without a separate human confirmation gate',
  );
  assert.ok(
    bridgeSource.includes('oneShotHumanAuthorized: hasConsumedOneShotDeliveryAuthorization(pending)'),
    'the page runner may click send only after the backend consumed a one-shot ticket',
  );
  assert.ok(!bridgeSource.includes('clickSend: true'), 'ordinary bridge payloads must not enable a send click');

  const configureScript = await readFile('scripts/cc_zhongzhuan_configure_seller_extension.mjs', 'utf8');
  assert.ok(configureScript.includes('xianyu_delivery_send: false'));
  assert.ok(configureScript.includes('xianyu_confirm_shipment: false'));
  assert.ok(configureScript.includes('xianyu_relist_item: false'));
  assert.ok(configureScript.includes('xianyu_one_shot_delivery_human_gated: true'));
  assert.ok(configureScript.includes('relist_queue_watch: false'));
});


test('health check treats renewals as read-only reminders and never payments', async () => {
  const content = await readFile('scripts/auto_health_check.sh', 'utf8');
  assert.ok(content.includes('packages/clawbot/config/renewals.json'));
  assert.ok(content.includes('系统不会代付'));
  assert.ok(content.includes('不要写密码、Token、Cookie 或恢复码'));
  assert.ok(!content.includes('auto_renew_changed=true'));
});
