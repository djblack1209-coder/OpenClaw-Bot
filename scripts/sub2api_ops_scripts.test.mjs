import assert from 'node:assert/strict';
import { access, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { constants } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';

const manager = 'scripts/sub2api_oracle_manage.sh';
const broker = 'scripts/sub2api_jiyu_update_broker.sh';
const compatibilityWorkflow = '.github/workflows/sub2api-jiyu-compat.yml';
const compatibilityPatches = [
  'scripts/sub2api-jiyu-v0.1.172.patch',
  'scripts/sub2api-jiyu-v0.1.173.patch',
];
const regionPatches = [
  'scripts/sub2api-region-filter-v0.1.172.patch',
  'scripts/sub2api-region-filter-v0.1.173.patch',
];
const brandLogo = 'scripts/assets/jiyu-ai-logo-email.png';

test('Sub2API 管理入口可执行且 Bash 语法有效', async () => {
  await access(manager, constants.X_OK);
  await access(broker, constants.X_OK);
  for (const file of [manager, broker]) {
    const syntax = spawnSync('bash', ['-n', file], { encoding: 'utf8' });
    assert.equal(syntax.status, 0, syntax.stderr);
  }
});

test('共享配置目录不会在 Cloudflare 或 WebUI 配置时切断 Redis 读取权限', async () => {
  const content = await readFile(manager, 'utf8');
  assert.match(content, /prepare_config_directory\(\)/);
  assert.match(
    content,
    /setfacl -m u:sub2api:--x,u:sub2api-redis:--x,m::r-x "\$CONFIG_DIR"/,
  );
  assert.match(content, /runuser -u sub2api-redis -- test -x "\$CONFIG_DIR"/);
  assert.equal(
    (content.match(/install -d -m 0750 -o root -g root "\$CONFIG_DIR"/g) || []).length,
    1,
  );
  assert.equal(
    (content.match(/install -d -m 0750 -o root -g (?:sub2api|sub2api-redis) "\$CONFIG_DIR"/g) || [])
      .length,
    0,
  );
  assert.match(
    content,
    /finish_install\(\)[\s\S]*chown root:sub2api-redis "\$REDIS_CONFIG"[\s\S]*chmod 0640 "\$REDIS_CONFIG"[\s\S]*prepare_config_directory/,
  );
});

test('生产更新改为只检查，完整备份覆盖品牌与页面', async () => {
  const content = await readFile(manager, 'utf8');
  const regionPatchContents = await Promise.all(regionPatches.map(file => readFile(file, 'utf8')));
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
  assert.match(content, /reload_apache_with_recovery/);
  assert.match(content, /systemctl restart apache2\.service/);
  assert.equal((content.match(/systemctl reload apache2\.service/g) || []).length, 1);
  assert.match(
    content,
    /reload_apache_with_recovery\(\)[\s\S]*apache2ctl configtest[\s\S]*systemctl reload apache2\.service[\s\S]*verify_public_url[\s\S]*systemctl restart apache2\.service[\s\S]*verify_public_url/,
  );
  assert.match(content, /reload_apache_with_recovery "https:\/\/\$\{DOMAIN\}\/api\/status"/);
  assert.match(content, /api\.deepseek\.com/);
  assert.match(content, /api\.siliconflow\.cn/);
  assert.match(content, /region-enforcement <enable\|disable>/);
  assert.match(content, /cn-production <pause\|resume>/);
  assert.match(content, /JIYU-CN-PRODUCTION-GATE-BEGIN/);
  assert.match(content, /中国生产面 .*已恢复/);
  assert.match(content, /地域强制配置应用失败，已恢复原配置/);
  for (const regionPatchContent of regionPatchContents) {
    assert.match(regionPatchContent, /func IsJiyuGroupAllowed/);
    assert.match(regionPatchContent, /backend\/internal\/handler\/api_key_handler\.go/);
    assert.match(regionPatchContent, /backend\/internal\/handler\/available_channel_handler\.go/);
    assert.match(regionPatchContent, /backend\/internal\/handler\/model_plaza_handler\.go/);
    assert.match(regionPatchContent, /norm\.NFKC\.String/);
  }
});

test('地域可信头只安装到 JIYU HTTPS VirtualHost', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'sub2api-region-headers-'));
  const source = join(directory, 'site.conf');
  const destination = join(directory, 'rewritten.conf');
  const secondDestination = join(directory, 'rewritten-again.conf');
  const fixture = `<VirtualHost *:80>
    ServerName example.test
    # JIYU-REGION-TRUST-BOUNDARY: misplaced legacy block
    SetEnvIf CF-IPCountry "^([A-Z]{2})$" JIYU_CF_COUNTRY=$1
    RequestHeader unset X-JIYU-Country
    RequestHeader set X-JIYU-Country "%{JIYU_CF_COUNTRY}e" env=JIYU_CF_COUNTRY
    RequestHeader unset CF-IPCountry
</VirtualHost>
<VirtualHost *:443>
    ServerName example.test
    ProxyPass / http://127.0.0.1:18080/
</VirtualHost>
<VirtualHost *:443>
    ServerName legacy.example.test
</VirtualHost>
`;
  try {
    await writeFile(source, fixture);
    const rewrite = spawnSync(
      'bash',
      [
        '-c',
        `source <(sed '$d' "$1"); rewrite_jiyu_region_headers "$2" "$3" example.test`,
        'bash',
        manager,
        source,
        destination,
      ],
      { encoding: 'utf8' },
    );
    assert.equal(rewrite.status, 0, rewrite.stderr);
    const output = await readFile(destination, 'utf8');
    const httpEnd = output.indexOf('</VirtualHost>');
    const targetStart = output.indexOf('<VirtualHost *:443>');
    const targetEnd = output.indexOf('</VirtualHost>', targetStart);
    const marker = output.indexOf('JIYU-REGION-TRUST-BOUNDARY-BEGIN');
    assert.equal((output.match(/JIYU-REGION-TRUST-BOUNDARY-BEGIN/g) || []).length, 1);
    assert.ok(marker > targetStart && marker < targetEnd);
    assert.ok(marker > httpEnd);
    const secondRewrite = spawnSync(
      'bash',
      [
        '-c',
        `source <(sed '$d' "$1"); rewrite_jiyu_region_headers "$2" "$3" example.test`,
        'bash',
        manager,
        destination,
        secondDestination,
      ],
      { encoding: 'utf8' },
    );
    assert.equal(secondRewrite.status, 0, secondRewrite.stderr);
    assert.equal(await readFile(secondDestination, 'utf8'), output);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test('中国生产闸门只位于 JIYU HTTPS VirtualHost 且可幂等恢复', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'sub2api-cn-gate-'));
  const source = join(directory, 'site.conf');
  const paused = join(directory, 'paused.conf');
  const resumed = join(directory, 'resumed.conf');
  const fixture = `<VirtualHost *:80>
    ServerName example.test
</VirtualHost>
<VirtualHost *:443>
    ServerName example.test
    ProxyPass / http://127.0.0.1:18080/
</VirtualHost>
<VirtualHost *:443>
    ServerName legacy.example.test
</VirtualHost>
`;
  try {
    await writeFile(source, fixture);
    const pause = spawnSync(
      'bash',
      [
        '-c',
        `source <(sed '$d' "$1"); rewrite_jiyu_cn_production_gate "$2" "$3" example.test pause`,
        'bash',
        manager,
        source,
        paused,
      ],
      { encoding: 'utf8' },
    );
    assert.equal(pause.status, 0, pause.stderr);
    const pausedOutput = await readFile(paused, 'utf8');
    const targetStart = pausedOutput.indexOf('<VirtualHost *:443>');
    const targetEnd = pausedOutput.indexOf('</VirtualHost>', targetStart);
    const marker = pausedOutput.indexOf('JIYU-CN-PRODUCTION-GATE-BEGIN');
    assert.equal((pausedOutput.match(/JIYU-CN-PRODUCTION-GATE-BEGIN/g) || []).length, 1);
    assert.ok(marker > targetStart && marker < targetEnd);
    assert.match(pausedOutput, /Require not env JIYU_CN_PRODUCTION_PAUSED/);
    const resume = spawnSync(
      'bash',
      [
        '-c',
        `source <(sed '$d' "$1"); rewrite_jiyu_cn_production_gate "$2" "$3" example.test resume`,
        'bash',
        manager,
        paused,
        resumed,
      ],
      { encoding: 'utf8' },
    );
    assert.equal(resume.status, 0, resume.stderr);
    const resumedOutput = await readFile(resumed, 'utf8');
    assert.doesNotMatch(resumedOutput, /JIYU-CN-PRODUCTION-GATE-BEGIN/);
    assert.doesNotMatch(resumedOutput, /JIYU_CN_PRODUCTION_PAUSED/);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test('充值页只使用固定公开整店且 WebUI 更新只能进入固定 root 代理', async () => {
  const content = await readFile(manager, 'utf8');
  const brokerContent = await readFile(broker, 'utf8');
  const workflowContent = await readFile(compatibilityWorkflow, 'utf8');
  const patchContents = await Promise.all(compatibilityPatches.map(file => readFile(file, 'utf8')));
  assert.match(content, /readonly CHAIN_STORE_URL="\$\{CHAIN_STORE_ORIGIN\}\/shop\/ZCUGEDMV"/);
  assert.doesNotMatch(content, /<iframe src="\$\{CHAIN_STORE_URL\}"/);
  assert.match(content, /\[打开 JIYU AI 链动小铺\]\(\$\{CHAIN_STORE_URL\}\)/);
  assert.doesNotMatch(content, /pay\.ldxp\.cn[^"']*[?&](?:user_id|token|cookie)=/i);
  assert.match(content, /security\.setdefault\("csp", \{\}\)/);
  assert.match(content, /origin_directives != \[frame_directive\]/);
  assert.match(content, /matches != \[\("frame-src", 1\)\]/);
  assert.match(content, /cc-switch-download-grid/);
  assert.match(content, /grid-template-columns:repeat\(auto-fit,minmax\(130px,1fr\)\)/);
  assert.match(content, /min-height:52px/);
  assert.doesNotMatch(content, /window\.html/);
  assert.match(content, /LocationMatch "\^\/api\/v1\/admin\/system\/\(update\|rollback\)\$"/);
  assert.match(content, /Require all denied/);
  assert.match(content, /ListenStream=\/run\/sub2api-jiyu-update\.sock/);
  assert.doesNotMatch(content, /sub2api ALL=\(root\) NOPASSWD/);
  assert.match(content, /SUB2API_JIYU_MANAGED_UPDATE=1/);
  assert.match(content, /JIYU-RESPONSES-WEBSOCKET/);
  assert.match(content, /upgrade=websocket retry=0 timeout=120/);
  assert.match(content, /responses-websocket/);
  assert.match(content, /GATEWAY_OPENAI_WS_MODE_ROUTER_V2_ENABLED=true/);
  assert.match(content, /openai-ws-http-bridge/);
  assert.match(content, /openai-ws-legacy/);
  assert.match(content, /set_openai_ws_mode_router true/);
  assert.match(content, /set_openai_ws_mode_router false/);
  assert.match(brokerContent, /\[\[ "\$#" -eq 0 \]\]/);
  assert.match(brokerContent, /sha256sum/);
  assert.match(brokerContent, /MAX_ARTIFACT_BYTES/);
  assert.match(brokerContent, /兼容包大小不一致/);
  assert.match(brokerContent, /trap cleanup EXIT/);
  assert.match(brokerContent, /\[\[ "\$current" == "\$version" \]\]/);
  assert.match(brokerContent, /JIYU_UPDATE_STATUS=noop/);
  assert.match(brokerContent, /JIYU_UPDATE_STATUS=staged/);
  assert.match(brokerContent, /stage_output=.*stage-jiyu-build/);
  assert.ok(
    brokerContent.indexOf('stage_output=') < brokerContent.indexOf("printf 'JIYU_UPDATE_STATUS=staged"),
  );
  assert.doesNotMatch(brokerContent, /current_base/);
  assert.doesNotMatch(brokerContent, /eval |bash -c|sh -c/);
  assert.match(workflowContent, /go test -tags embed \.\/internal\/web/);
  assert.match(workflowContent, /go build -tags embed/);
  assert.match(workflowContent, /v0\.1\.172 \| v0\.1\.173/);
  assert.match(workflowContent, /sub2api-jiyu-\$\{UPSTREAM_TAG\}\.patch/);
  assert.match(workflowContent, /EVENT_NAME: \$\{\{ github\.event_name \}\}/);
  assert.match(workflowContent, /release_tag="\$\{BASE_RELEASE_TAG\}-r\$\{GITHUB_RUN_ID\}"/);
  assert.match(workflowContent, /RELEASE_TAG: \$\{\{ steps\.existing\.outputs\.release_tag \}\}/);
  assert.match(workflowContent, /gh release upload jiyu-latest jiyu-update-manifest\.json --clobber/);
  for (const patchContent of patchContents) {
    assert.match(patchContent, /diff --git a\/frontend\/src\/views\/admin\/AccountsView\.vue/);
    assert.match(patchContent, /-function accountHomepageUrl\(row: Account\): string/);
    assert.doesNotMatch(patchContent, /^\+.*accountHomepageUrl/m);
    assert.doesNotMatch(patchContent, /^\+.*:href="accountHomepageUrl/m);
    assert.match(patchContent, /v-else-if="isJiyuBuild"/);
    assert.match(patchContent, /DialContext\(ctx, "unix", socketPath\)/);
    assert.match(patchContent, /JIYU_UPDATE_STATUS=noop/);
    assert.doesNotMatch(patchContent, /exec\.CommandContext|sudo/);
    assert.match(patchContent, /const JIYU_RECHARGE_PAGE_ID = 'recharge-center'/);
    assert.match(patchContent, /const JIYU_RECHARGE_URL = 'https:\/\/pay\.ldxp\.cn\/shop\/ZCUGEDMV'/);
    assert.match(patchContent, /v-if="isJiyuRechargePage" class="jiyu-recharge-shell"/);
    assert.match(patchContent, /height: calc\(100dvh - 64px\)/);
    assert.doesNotMatch(patchContent, /height: calc\(100dvh - 64px -/);
    assert.match(
      patchContent,
      /@media \(max-width: 767px\)[\s\S]*\.jiyu-recharge-shell[\s\S]*position: fixed[\s\S]*top: 64px[\s\S]*left: 0[\s\S]*width: 100vw[\s\S]*margin: 0[\s\S]*\.jiyu-recharge-open[\s\S]*display: none/,
    );
    assert.match(patchContent, /:src="JIYU_RECHARGE_URL"/);
    assert.doesNotMatch(patchContent, /^\+.*buildEmbeddedUrl\([\s\S]*JIYU_RECHARGE_URL/m);
  }
  assert.match(content, /StandardInput=socket/);
  assert.match(content, /NoNewPrivileges=yes/);
});

test('JIYU 图形 Logo 是 512 像素 PNG', async () => {
  const image = await readFile(brandLogo);
  assert.equal(image.subarray(0, 8).toString('hex'), '89504e470d0a1a0a');
  assert.equal(image.readUInt32BE(16), 512);
  assert.equal(image.readUInt32BE(20), 512);
});
