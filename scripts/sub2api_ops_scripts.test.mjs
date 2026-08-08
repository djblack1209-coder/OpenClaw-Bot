import assert from 'node:assert/strict';
import { access, readFile } from 'node:fs/promises';
import { constants } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { test } from 'node:test';

const manager = 'scripts/sub2api_oracle_manage.sh';
const broker = 'scripts/sub2api_jiyu_update_broker.sh';
const brandLogo = 'scripts/assets/jiyu-ai-logo-email.png';

test('Sub2API 管理入口可执行且 Bash 语法有效', async () => {
  await access(manager, constants.X_OK);
  await access(broker, constants.X_OK);
  for (const file of [manager, broker]) {
    const syntax = spawnSync('bash', ['-n', file], { encoding: 'utf8' });
    assert.equal(syntax.status, 0, syntax.stderr);
  }
});

test('生产更新改为只检查，完整备份覆盖品牌与页面', async () => {
  const content = await readFile(manager, 'utf8');
  assert.match(content, /ExecStart=.* check-upstream/);
  assert.doesNotMatch(content, /ExecStart=.* update\s*$/m);
  assert.match(content, /SUB2API_ALLOW_UPSTREAM_BINARY_UPDATE/);
  assert.match(content, /data\/pages/);
  assert.match(content, /brand-assets/);
  assert.match(content, /SHA256SUMS/);
  assert.match(content, /install-jiyu-build/);
  assert.match(content, /stage-jiyu-build/);
  assert.match(content, /verify-jiyu-stage/);
  assert.match(content, /systemd-run/);
  assert.match(content, /\/proc\/\$\{current_pid\}\/exe/);
  assert.match(content, /restore_database "\$\{backup_dir\}\/sub2api\.dump"/);
  assert.match(content, /enable-web-update/);
  assert.match(content, /JIYU 构建健康检查失败，正在恢复发布前版本和数据库/);
});

test('充值页无 CSP iframe，WebUI 更新只能进入固定 root 代理', async () => {
  const content = await readFile(manager, 'utf8');
  const brokerContent = await readFile(broker, 'utf8');
  assert.doesNotMatch(content, /<iframe/i);
  assert.doesNotMatch(content, /window\.html/);
  assert.match(content, /LocationMatch "\^\/api\/v1\/admin\/system\/\(update\|rollback\)\$"/);
  assert.match(content, /Require all denied/);
  assert.match(content, /sub2api ALL=\(root\) NOPASSWD/);
  assert.match(content, /SUB2API_JIYU_MANAGED_UPDATE=1/);
  assert.match(brokerContent, /\[\[ "\$#" -eq 0 \]\]/);
  assert.match(brokerContent, /sha256sum/);
  assert.match(brokerContent, /MAX_ARTIFACT_BYTES/);
  assert.match(brokerContent, /兼容包大小不一致/);
  assert.doesNotMatch(brokerContent, /eval |bash -c|sh -c/);
});

test('JIYU 图形 Logo 是 512 像素 PNG', async () => {
  const image = await readFile(brandLogo);
  assert.equal(image.subarray(0, 8).toString('hex'), '89504e470d0a1a0a');
  assert.equal(image.readUInt32BE(16), 512);
  assert.equal(image.readUInt32BE(20), 512);
});
