import assert from 'node:assert/strict';
import { access, readFile } from 'node:fs/promises';
import { constants } from 'node:fs';
import { test } from 'node:test';

const scripts = [
  ['scripts/auto_health_check.sh', ['--json', 'OPENCLAW', 'cc_zhongzhuan_readiness_audit.mjs']],
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
