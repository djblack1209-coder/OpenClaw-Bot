import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import {
  access,
  appendFile,
  chmod,
  copyFile,
  mkdir,
  mkdtemp,
  readFile,
  realpath,
  readdir,
  rm,
  stat,
  symlink,
  writeFile,
} from 'node:fs/promises';
import { constants } from 'node:fs';
import { tmpdir } from 'node:os';
import { basename, join } from 'node:path';
import { spawn, spawnSync } from 'node:child_process';
import { test } from 'node:test';
import { setTimeout as delay } from 'node:timers/promises';

const scripts = [
  ['scripts/auto_health_check.sh', ['--json', 'OPENCLAW', 'cc_zhongzhuan_readiness_audit.mjs']],
  ['scripts/auto_recovery.sh', ['--dry-run', '--confirm', '--scope', 'make cc-seller-auto', 'launchctl']],
  ['scripts/local_backup.sh', ['OPENCLAW_BACKUP_DIR', 'tar', '30']],
  ['scripts/disaster_recovery.sh', ['--from-r2', '--dry-run', 'restore']],
  ['scripts/manage_backup_launchagent.sh', ['install', 'status', 'uninstall', 'StartCalendarInterval', '--drill']],
  ['scripts/tauri_build_install.sh', ['openclaw-app-backup', 'restore_previous_apps', 'npm run tauri:build']],
  ['scripts/tauri_rollback.sh', ['--check', '--confirm', 'codesign --verify']],
  ['scripts/check_clean_install.sh', ['npm ci', '--require-hashes', 'requirements-lock-macos.txt']],
];

async function writeExecutable(file, body) {
  await writeFile(file, `#!/usr/bin/env bash\n${body}\n`, 'utf8');
  await chmod(file, 0o755);
}

async function createOpsCommandStubs(sandbox) {
  const binDir = join(sandbox, 'bin');
  const callsFile = join(sandbox, 'calls.log');
  await mkdir(binDir, { recursive: true });
  await writeExecutable(join(binDir, 'curl'), 'echo 000');
  await writeExecutable(
    join(binDir, 'launchctl'),
    'printf "launchctl %s\\n" "$*" >> "$OPENCLAW_TEST_CALLS"; exit 1',
  );
  await writeExecutable(
    join(binDir, 'make'),
    'printf "make %s\\n" "$*" >> "$OPENCLAW_TEST_CALLS"',
  );
  await writeExecutable(join(binDir, 'node'), 'exit 1');
  return {
    callsFile,
    env: {
      ...process.env,
      PATH: `${binDir}:${process.env.PATH}`,
      OPENCLAW_TEST_CALLS: callsFile,
    },
  };
}

async function createBackupSandbox() {
  const sandbox = await mkdtemp(join(tmpdir(), 'openclaw-backup-contract-'));
  const project = join(sandbox, 'project');
  const home = join(sandbox, 'home');
  const backupDir = join(sandbox, 'backups');
  const scriptsDir = join(project, 'scripts');

  for (const directory of [
    scriptsDir,
    join(project, 'docs'),
    join(project, 'apps', 'frist-api', 'data'),
    join(project, 'apps', 'openclaw'),
    join(project, 'apps', 'openclaw-manager-src', 'src'),
    join(project, 'packages', 'clawbot', 'src'),
    join(project, 'packages', 'clawbot', 'scripts'),
    join(project, 'packages', 'clawbot', 'tests'),
    join(project, 'packages', 'clawbot', 'config'),
    join(project, 'packages', 'clawbot', 'data'),
    join(project, 'data', 'frist-api'),
    join(project, 'data', 'newapi'),
    join(home, '.openclaw', 'state'),
    backupDir,
  ]) {
    await mkdir(directory, { recursive: true });
  }

  await copyFile('scripts/local_backup.sh', join(scriptsDir, 'local_backup.sh'));
  await copyFile('scripts/disaster_recovery.sh', join(scriptsDir, 'disaster_recovery.sh'));
  await copyFile('scripts/manage_backup_launchagent.sh', join(scriptsDir, 'manage_backup_launchagent.sh'));
  await chmod(join(scriptsDir, 'local_backup.sh'), 0o755);
  await chmod(join(scriptsDir, 'disaster_recovery.sh'), 0o755);
  await chmod(join(scriptsDir, 'manage_backup_launchagent.sh'), 0o755);
  await writeFile(join(project, 'Makefile'), 'test:\n\t@true\n', 'utf8');
  await writeFile(join(project, 'docs', 'fixture.txt'), 'docs', 'utf8');
  await writeFile(join(project, '.env'), 'ROOT_SECRET=fixture\n', 'utf8');
  await writeFile(join(project, 'packages', 'clawbot', 'config', '.env'), 'BOT_SECRET=fixture\n', 'utf8');
  await writeFile(join(project, 'packages', 'clawbot', 'config', '.env.example'), 'BOT_SECRET=\n', 'utf8');
  await writeFile(join(project, 'apps', 'frist-api', 'data', 'runtime.json'), '{"ok":true}\n', 'utf8');
  const openclawConfig = join(home, '.openclaw', 'openclaw.json');
  await writeFile(openclawConfig, '{"gateway":"fixture"}\n', 'utf8');
  if (process.platform === 'darwin') {
    const tagged = spawnSync('xattr', ['-w', 'com.openclaw.backup-test', 'fixture', openclawConfig], {
      encoding: 'utf8',
    });
    assert.equal(tagged.status, 0, tagged.stderr);
  }

  const projectDb = join(project, 'packages', 'clawbot', 'data', 'history.db');
  const homeDb = join(home, '.openclaw', 'state', 'openclaw.sqlite');
  for (const database of [projectDb, homeDb]) {
    const created = spawnSync(
      'sqlite3',
      [database, 'CREATE TABLE records(value TEXT); INSERT INTO records VALUES ("consistent");'],
      { encoding: 'utf8' },
    );
    assert.equal(created.status, 0, created.stderr);
  }

  return { sandbox, project, home, backupDir, projectDb, homeDb };
}

function runLocalBackup(fixture, args = [], extraEnv = {}) {
  return spawnSync('/bin/bash', [join(fixture.project, 'scripts', 'local_backup.sh'), ...args], {
    cwd: fixture.project,
    encoding: 'utf8',
    env: {
      ...process.env,
      HOME: fixture.home,
      OPENCLAW_BACKUP_DIR: fixture.backupDir,
      OPENCLAW_BACKUP_RETENTION_DAYS: '30',
      OPENCLAW_BACKUP_RETENTION_COUNT: '5',
      OPENCLAW_BACKUP_OFFSITE_DIR: '',
      OPENCLAW_BACKUP_GPG_RECIPIENT: '',
      ...extraEnv,
    },
  });
}

function parseBackupResult(result) {
  const line = result.stdout.trim().split('\n').filter(Boolean).at(-1);
  return JSON.parse(line);
}

async function createBackupLaunchctlStubs(sandbox) {
  const binDir = join(sandbox, 'launchd-bin');
  const callsFile = join(sandbox, 'launchd-calls.log');
  const stateFile = join(sandbox, 'launchd-loaded');
  await mkdir(binDir, { recursive: true });
  await writeExecutable(join(binDir, 'uname'), 'echo Darwin');
  await writeExecutable(
    join(binDir, 'launchctl'),
    `set -eu
printf 'launchctl %s\\n' "$*" >> "$OPENCLAW_TEST_CALLS"
case "\${1:-}" in
  print)
    [[ -f "$OPENCLAW_TEST_STATE" ]]
    ;;
  bootstrap)
    if [[ "\${OPENCLAW_TEST_BOOTSTRAP_FAIL:-0}" == "1" ]]; then
      exit 70
    fi
    : > "$OPENCLAW_TEST_STATE"
    ;;
  bootout)
    rm -f "$OPENCLAW_TEST_STATE"
    ;;
  *)
    exit 64
    ;;
esac`,
  );
  return {
    callsFile,
    stateFile,
    env: {
      ...process.env,
      PATH: `${binDir}:${process.env.PATH}`,
      OPENCLAW_TEST_CALLS: callsFile,
      OPENCLAW_TEST_STATE: stateFile,
    },
  };
}

async function createSignedTestApp(appPath, versionMarker) {
  const executableDir = join(appPath, 'Contents', 'MacOS');
  await mkdir(executableDir, { recursive: true });
  await writeFile(
    join(appPath, 'Contents', 'Info.plist'),
    `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleExecutable</key><string>OpenClaw</string>
<key>CFBundleIdentifier</key><string>ai.openclaw.rollback-test</string>
<key>CFBundleName</key><string>OpenClaw</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleVersion</key><string>${versionMarker}</string>
</dict></plist>
`,
    'utf8',
  );
  const executable = join(executableDir, 'OpenClaw');
  await writeFile(executable, `#!/bin/sh\necho ${versionMarker}\n`, 'utf8');
  await chmod(executable, 0o755);
  const signed = spawnSync('codesign', ['--force', '--sign', '-', appPath], { encoding: 'utf8' });
  assert.equal(signed.status, 0, signed.stderr);
}

function cdhashFor(appPath) {
  const result = spawnSync('codesign', ['-dvvv', appPath], { encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr);
  return `${result.stdout}\n${result.stderr}`.match(/^CDHash=(.+)$/m)?.[1]?.trim() || '';
}

function writeRollbackManifest(manifestPath, currentHash, previousHash) {
  const commands = [
    ['-create', 'xml1', manifestPath],
    ['-insert', 'installedCDHash', '-string', currentHash, manifestPath],
    ['-insert', 'previousCDHash', '-string', previousHash, manifestPath],
    ['-insert', 'sourcePatchSHA256', '-string', 'a'.repeat(64), manifestPath],
    ['-insert', 'dmgSHA256', '-string', 'b'.repeat(64), manifestPath],
  ];
  for (const args of commands) {
    const result = spawnSync('plutil', args, { encoding: 'utf8' });
    assert.equal(result.status, 0, result.stderr);
  }
}

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

test('recovery defaults to a read-only preview and never invokes fulfillment', async () => {
  const sandbox = await mkdtemp(join(tmpdir(), 'openclaw-recovery-preview-'));
  try {
    const { callsFile, env } = await createOpsCommandStubs(sandbox);
    const result = spawnSync('bash', ['scripts/auto_recovery.sh'], {
      cwd: process.cwd(),
      encoding: 'utf8',
      env,
    });
    const calls = await readFile(callsFile, 'utf8').catch(() => '');

    assert.equal(result.status, 0, result.stderr);
    assert.match(result.stdout, /dry-run/);
    assert.doesNotMatch(calls, /^make /m);
    assert.doesNotMatch(calls, /launchctl kickstart/);
  } finally {
    await rm(sandbox, { recursive: true, force: true });
  }
});

test('fulfillment recovery requires both its isolated scope and confirmation', async () => {
  const sandbox = await mkdtemp(join(tmpdir(), 'openclaw-recovery-fulfillment-'));
  try {
    const { callsFile, env } = await createOpsCommandStubs(sandbox);
    const preview = spawnSync(
      'bash',
      ['scripts/auto_recovery.sh', '--scope', 'fulfillment'],
      { cwd: process.cwd(), encoding: 'utf8', env },
    );
    const previewCalls = await readFile(callsFile, 'utf8').catch(() => '');
    assert.equal(preview.status, 0, preview.stderr);
    assert.doesNotMatch(previewCalls, /^make /m);

    const confirmed = spawnSync(
      'bash',
      ['scripts/auto_recovery.sh', '--scope', 'fulfillment', '--confirm'],
      { cwd: process.cwd(), encoding: 'utf8', env },
    );
    const confirmedCalls = await readFile(callsFile, 'utf8').catch(() => '');
    assert.notEqual(confirmed.status, 0, 'strict post-action health check should fail against stubs');
    assert.match(confirmedCalls, /^make cc-seller-auto$/m);
  } finally {
    await rm(sandbox, { recursive: true, force: true });
  }
});

test('strict health check exits non-zero when required services are down', async () => {
  const sandbox = await mkdtemp(join(tmpdir(), 'openclaw-health-strict-'));
  try {
    const { env } = await createOpsCommandStubs(sandbox);
    const result = spawnSync('bash', ['scripts/auto_health_check.sh', '--json', '--strict'], {
      cwd: process.cwd(),
      encoding: 'utf8',
      env,
    });
    const report = JSON.parse(result.stdout);

    assert.equal(result.status, 1, result.stderr);
    assert.equal(report.ok, false);
    assert.equal(report.release_ready, false);
    assert.ok(report.checks.some((check) => check.status === 'bad'));
  } finally {
    await rm(sandbox, { recursive: true, force: true });
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
    'ai.openclaw.daily-backup',
    'backup_freshness',
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
  assert.match(script, /BACKUP_READY=0/);
  const backupReady = script.indexOf('BACKUP_READY=1');
  const destructiveCleanup = script.indexOf('rm -rf "$INSTALL_DIR/$app_name"', backupReady);
  assert.ok(backupReady >= 0 && destructiveCleanup > backupReady);
  assert.match(script, /ditto \"\$INSTALL_DIR\/\$app_name\" \"\$BACKUP_DIR\/\$app_name\"/);
  assert.ok(script.indexOf('rm -rf "$INSTALL_DIR/$app_name"') < script.indexOf('npm run tauri:build'));
  assert.ok(script.indexOf('mv "$INSTALL_TMP" "$INSTALL_APP"') < script.lastIndexOf('trap - EXIT INT TERM'));
});

test('desktop build never deletes an installed app before every local backup is ready', async () => {
  const sandbox = await mkdtemp(join(tmpdir(), 'openclaw-build-rollback-'));
  const installDir = join(sandbox, 'Applications');
  const rollbackDir = join(sandbox, 'rollback');
  const legacyApp = join(installDir, 'OpenEverything.app');
  const marker = join(legacyApp, 'marker.txt');
  try {
    await mkdir(legacyApp, { recursive: true });
    await writeFile(marker, 'previous-version', 'utf8');
    const result = spawnSync('bash', ['scripts/tauri_build_install.sh'], {
      cwd: process.cwd(),
      encoding: 'utf8',
      env: {
        ...process.env,
        OPENCLAW_INSTALL_DIR: installDir,
        OPENCLAW_ROLLBACK_DIR: rollbackDir,
        OPENCLAW_TEST_FAIL_AT: 'after-first-local-backup',
      },
    });

    assert.notEqual(result.status, 0);
    assert.equal(await readFile(marker, 'utf8'), 'previous-version');
    assert.match(`${result.stdout}\n${result.stderr}`, /未清理现有桌面版本/);
  } finally {
    await rm(sandbox, { recursive: true, force: true });
  }
});

test('desktop release keeps one signed previous version outside Applications for explicit rollback', async () => {
  const makefile = await readFile('Makefile', 'utf8');
  const buildScript = await readFile('scripts/tauri_build_install.sh', 'utf8');
  const rollbackScript = await readFile('scripts/tauri_rollback.sh', 'utf8');

  assert.match(buildScript, /Library\/Application Support\/OpenClaw\/release-backups/);
  assert.match(buildScript, /PERSISTENT_ROLLBACK_APP/);
  assert.match(buildScript, /sourcePatchSHA256/);
  assert.match(buildScript, /dmgSHA256/);
  assert.match(buildScript, /no-distinct-previous-version/);
  assert.match(buildScript, /codesign --verify --deep --strict --verbose=2 "\$PERSISTENT_ROLLBACK_TMP"/);
  assert.match(buildScript, /if \(\( status != 0 \)\); then[\s\S]*rm -rf "\$INSTALL_DIR\/\$app_name"[\s\S]*ditto "\$BACKUP_DIR\/\$app_name"/);
  assert.ok(buildScript.indexOf('mv "$INSTALL_TMP" "$INSTALL_APP"') < buildScript.indexOf('mv "$PERSISTENT_ROLLBACK_TMP" "$PERSISTENT_ROLLBACK_APP"'));
  assert.match(rollbackScript, /ROLLBACK_APP/);
  assert.match(rollbackScript, /--check/);
  assert.match(rollbackScript, /--confirm/);
  assert.match(rollbackScript, /mv "\$INSTALL_TMP" "\$INSTALL_APP"/);
  assert.match(rollbackScript, /manifest_value previousCDHash/);
  assert.match(rollbackScript, /manifest_value installedCDHash/);
  assert.match(rollbackScript, /回滚副本指纹与清单不一致/);
  assert.match(rollbackScript, /当前应用与回滚副本指纹相同/);
  assert.match(rollbackScript, /plutil -replace previousCDHash/);
  assert.match(rollbackScript, /plutil -replace installedCDHash/);
  assert.match(rollbackScript, /if \(\( status != 0 \)\)[\s\S]*rm -rf "\$INSTALL_APP"[\s\S]*ditto "\$CURRENT_TMP" "\$INSTALL_APP"/);
  assert.match(makefile, /tauri-rollback-check:[^\n]*\n\s+bash scripts\/tauri_rollback\.sh --check/);
  assert.match(makefile, /tauri-rollback:[^\n]*\n\s+bash scripts\/tauri_rollback\.sh --confirm/);
});

test('desktop rollback rejects identical builds and swaps two genuinely distinct signed versions', async (t) => {
  if (process.platform !== 'darwin') {
    t.skip('Tauri desktop rollback evidence is macOS-only');
    return;
  }
  const sandbox = await mkdtemp(join(tmpdir(), 'openclaw-distinct-rollback-'));
  const installDir = join(sandbox, 'Applications');
  const rollbackDir = join(sandbox, 'rollback');
  const currentApp = join(installDir, 'OpenClaw.app');
  const previousApp = join(rollbackDir, 'OpenClaw.app');
  const manifest = join(rollbackDir, 'manifest.plist');
  const env = { ...process.env, OPENCLAW_INSTALL_DIR: installDir, OPENCLAW_ROLLBACK_DIR: rollbackDir };
  try {
    await createSignedTestApp(currentApp, '2');
    await mkdir(rollbackDir, { recursive: true });
    await createSignedTestApp(previousApp, '1');
    const currentHash = cdhashFor(currentApp);
    const previousHash = cdhashFor(previousApp);
    assert.notEqual(currentHash, previousHash);
    writeRollbackManifest(manifest, currentHash, previousHash);

    const checked = spawnSync('bash', ['scripts/tauri_rollback.sh', '--check'], {
      cwd: process.cwd(),
      encoding: 'utf8',
      env,
    });
    assert.equal(checked.status, 0, checked.stderr);
    assert.match(checked.stdout, /rollback_ready=true/);

    const swapped = spawnSync('bash', ['scripts/tauri_rollback.sh', '--confirm'], {
      cwd: process.cwd(),
      encoding: 'utf8',
      env,
    });
    assert.equal(swapped.status, 0, swapped.stderr);
    assert.equal(cdhashFor(currentApp), previousHash);
    assert.equal(cdhashFor(previousApp), currentHash);

    const reverseChecked = spawnSync('bash', ['scripts/tauri_rollback.sh', '--check'], {
      cwd: process.cwd(),
      encoding: 'utf8',
      env,
    });
    assert.equal(reverseChecked.status, 0, reverseChecked.stderr);

    await rm(previousApp, { recursive: true, force: true });
    const copied = spawnSync('ditto', [currentApp, previousApp], { encoding: 'utf8' });
    assert.equal(copied.status, 0, copied.stderr);
    const identicalHash = cdhashFor(currentApp);
    writeRollbackManifest(manifest, identicalHash, identicalHash);
    const rejected = spawnSync('bash', ['scripts/tauri_rollback.sh', '--check'], {
      cwd: process.cwd(),
      encoding: 'utf8',
      env,
    });
    assert.notEqual(rejected.status, 0);
    assert.match(`${rejected.stdout}\n${rejected.stderr}`, /指纹相同，不构成有效回滚/);
  } finally {
    await rm(sandbox, { recursive: true, force: true });
  }
});

test('desktop JavaScript and Rust Tauri packages stay on the same major and minor version', async () => {
  const packageJson = JSON.parse(await readFile('apps/openclaw-manager-src/package.json', 'utf8'));
  const cargoLock = await readFile('apps/openclaw-manager-src/src-tauri/Cargo.lock', 'utf8');
  const rustTauri = cargoLock.match(/\[\[package\]\]\s+name = "tauri"\s+version = "([^"]+)"/);
  assert.ok(rustTauri, 'Cargo.lock should contain the Tauri crate');

  const rustMajorMinor = rustTauri[1].split('.').slice(0, 2).join('.');
  for (const [name, version] of [
    ['@tauri-apps/api', packageJson.dependencies['@tauri-apps/api']],
    ['@tauri-apps/cli', packageJson.devDependencies['@tauri-apps/cli']],
  ]) {
    const jsMajorMinor = version.match(/\d+\.\d+/)?.[0];
    assert.equal(jsMajorMinor, rustMajorMinor, `${name} should match Rust Tauri ${rustMajorMinor}.x`);
  }
});

test('desktop release metadata uses one patch version across npm, Cargo and Tauri', async () => {
  const packageJson = JSON.parse(await readFile('apps/openclaw-manager-src/package.json', 'utf8'));
  const packageLock = JSON.parse(await readFile('apps/openclaw-manager-src/package-lock.json', 'utf8'));
  const tauriConfig = JSON.parse(await readFile('apps/openclaw-manager-src/src-tauri/tauri.conf.json', 'utf8'));
  const cargoToml = await readFile('apps/openclaw-manager-src/src-tauri/Cargo.toml', 'utf8');
  const cargoVersion = cargoToml.match(/^version\s*=\s*"([^"]+)"/m)?.[1];

  assert.equal(packageJson.version, '0.1.1');
  assert.equal(packageLock.version, packageJson.version);
  assert.equal(packageLock.packages[''].version, packageJson.version);
  assert.equal(tauriConfig.version, packageJson.version);
  assert.equal(cargoVersion, packageJson.version);
});

test('desktop macOS internal bundle is ad-hoc signed and verified before installation', async () => {
  const tauriConfig = JSON.parse(await readFile('apps/openclaw-manager-src/src-tauri/tauri.conf.json', 'utf8'));
  assert.equal(tauriConfig.bundle.macOS.signingIdentity, '-', 'macOS internal builds should use Tauri ad-hoc signing');

  const buildScript = await readFile('scripts/tauri_build_install.sh', 'utf8');
  const bundleVerification = 'codesign --verify --deep --strict --verbose=2 "$BUNDLE_APP"';
  const installVerification = 'codesign --verify --deep --strict --verbose=2 "$INSTALL_TMP"';
  const installMove = 'mv "$INSTALL_TMP" "$INSTALL_APP"';
  assert.ok(buildScript.includes(bundleVerification), 'desktop build should verify the signed bundle before installation');
  assert.ok(buildScript.includes(installVerification), 'desktop build should verify the temporary install copy');
  assert.ok(buildScript.indexOf(bundleVerification) < buildScript.indexOf(installVerification));
  assert.ok(buildScript.indexOf(installVerification) < buildScript.indexOf(installMove));
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

test('backup publishes an atomic checksummed bundle with consistent SQLite snapshots', async () => {
  const fixture = await createBackupSandbox();
  const walReady = join(fixture.sandbox, 'wal-ready');
  const walWriter = spawn(
    'python3',
    [
      '-c',
      [
        'import pathlib,sqlite3,sys,time',
        'connection=sqlite3.connect(sys.argv[1])',
        'connection.execute("PRAGMA journal_mode=WAL")',
        'connection.execute("PRAGMA wal_autocheckpoint=0")',
        'connection.execute("INSERT INTO records VALUES (\\"wal-consistent\\")")',
        'connection.commit()',
        'pathlib.Path(sys.argv[2]).write_text("ready")',
        'time.sleep(30)',
      ].join('\n'),
      fixture.projectDb,
      walReady,
    ],
    { stdio: 'ignore' },
  );
  try {
    for (let attempt = 0; attempt < 100; attempt += 1) {
      if (await access(walReady, constants.F_OK).then(() => true, () => false)) break;
      await delay(20);
    }
    await access(walReady, constants.F_OK);

    const result = runLocalBackup(fixture, [], { OPENCLAW_BACKUP_STAMP: '20260805-010101' });
    assert.equal(result.status, 0, result.stderr);
    const report = parseBackupResult(result);
    const archive = report.archive;

    await access(archive, constants.F_OK);
    await access(`${archive}.sha256`, constants.F_OK);
    await access(`${archive}.ready`, constants.F_OK);
    assert.equal((await stat(archive)).mode & 0o777, 0o600);
    assert.equal((await stat(`${archive}.sha256`)).mode & 0o777, 0o600);
    assert.equal(
      (await readdir(fixture.backupDir)).some((name) => name.includes('.partial')),
      false,
    );

    const listed = spawnSync('tar', ['-tzf', archive], { encoding: 'utf8' });
    assert.equal(listed.status, 0, listed.stderr);
    assert.match(listed.stdout, /^FORMAT_VERSION$/m);
    assert.match(listed.stdout, /^INVENTORY\.tsv$/m);
    assert.match(listed.stdout, /^MANIFEST\.sha256$/m);
    assert.match(listed.stdout, /payload\/project\/packages\/clawbot\/data\/history\.db/);
    assert.match(listed.stdout, /payload\/home\/\.openclaw\/openclaw\.json/);
    assert.doesNotMatch(listed.stdout, /(^|\/)\._/m);

    const inspectDir = join(fixture.sandbox, 'inspect');
    await mkdir(inspectDir);
    const extracted = spawnSync('tar', ['-xzf', archive, '-C', inspectDir], { encoding: 'utf8' });
    assert.equal(extracted.status, 0, extracted.stderr);
    const snapshotDb = join(inspectDir, 'payload', 'project', 'packages', 'clawbot', 'data', 'history.db');
    const row = spawnSync('sqlite3', [snapshotDb, 'SELECT value FROM records ORDER BY rowid;'], { encoding: 'utf8' });
    assert.equal(row.status, 0, row.stderr);
    assert.equal(row.stdout.trim(), 'consistent\nwal-consistent');
    const inventory = await readFile(join(inspectDir, 'INVENTORY.tsv'), 'utf8');
    assert.match(inventory, /project\t\.env\tpresent/);
    assert.match(inventory, /home\t\.openclaw\/openclaw\.json\tpresent/);
    const source = await readFile(join(fixture.project, 'scripts', 'local_backup.sh'), 'utf8');
    assert.match(source, /\.backup/);
  } finally {
    walWriter.kill('SIGTERM');
    await rm(fixture.sandbox, { recursive: true, force: true });
  }
});

test('disaster restore defaults to preview, supports drills, and requires explicit confirmation', async () => {
  const fixture = await createBackupSandbox();
  try {
    const backup = runLocalBackup(fixture, [], { OPENCLAW_BACKUP_STAMP: '20260805-020202' });
    assert.equal(backup.status, 0, backup.stderr);
    const { archive } = parseBackupResult(backup);
    const restoreRoot = join(fixture.sandbox, 'restored-project');
    const restoreHome = join(fixture.sandbox, 'restored-home');
    const restoreEnv = {
      ...process.env,
      HOME: fixture.home,
      OPENCLAW_BACKUP_DIR: fixture.backupDir,
      OPENCLAW_RESTORE_ROOT: restoreRoot,
      OPENCLAW_RESTORE_HOME: restoreHome,
    };
    const recoveryScript = join(fixture.project, 'scripts', 'disaster_recovery.sh');

    const preview = spawnSync('/bin/bash', [recoveryScript, '--archive', archive], {
      cwd: fixture.project,
      encoding: 'utf8',
      env: restoreEnv,
    });
    assert.equal(preview.status, 0, preview.stderr);
    assert.match(preview.stdout, /restore dry-run/);
    await assert.rejects(access(join(restoreRoot, '.env'), constants.F_OK));

    const drill = spawnSync('/bin/bash', [recoveryScript, '--archive', archive, '--drill'], {
      cwd: fixture.project,
      encoding: 'utf8',
      env: restoreEnv,
    });
    assert.equal(drill.status, 0, drill.stderr);
    assert.match(drill.stdout, /restore drill passed/);
    await assert.rejects(access(join(restoreRoot, '.env'), constants.F_OK));

    const restored = spawnSync('/bin/bash', [recoveryScript, '--archive', archive, '--confirm'], {
      cwd: fixture.project,
      encoding: 'utf8',
      env: restoreEnv,
    });
    assert.equal(restored.status, 0, restored.stderr);
    assert.equal(await readFile(join(restoreRoot, '.env'), 'utf8'), 'ROOT_SECRET=fixture\n');
    assert.equal(
      await readFile(join(restoreHome, '.openclaw', 'openclaw.json'), 'utf8'),
      '{"gateway":"fixture"}\n',
    );
    const restoredDb = join(restoreRoot, 'packages', 'clawbot', 'data', 'history.db');
    const row = spawnSync('sqlite3', [restoredDb, 'SELECT value FROM records;'], { encoding: 'utf8' });
    assert.equal(row.status, 0, row.stderr);
    assert.equal(row.stdout.trim(), 'consistent');
  } finally {
    await rm(fixture.sandbox, { recursive: true, force: true });
  }
});

test('disaster restore rejects checksum damage and path traversal before writing', async () => {
  const fixture = await createBackupSandbox();
  try {
    const backup = runLocalBackup(fixture, [], { OPENCLAW_BACKUP_STAMP: '20260805-030303' });
    assert.equal(backup.status, 0, backup.stderr);
    const { archive } = parseBackupResult(backup);
    const recoveryScript = join(fixture.project, 'scripts', 'disaster_recovery.sh');
    const restoreRoot = join(fixture.sandbox, 'rejected-restore');
    const restoreEnv = {
      ...process.env,
      HOME: fixture.home,
      OPENCLAW_RESTORE_ROOT: restoreRoot,
      OPENCLAW_RESTORE_HOME: join(fixture.sandbox, 'rejected-home'),
    };

    const outsideTarget = join(fixture.sandbox, 'outside-target');
    await mkdir(restoreRoot, { recursive: true });
    await mkdir(outsideTarget, { recursive: true });
    await symlink(outsideTarget, join(restoreRoot, 'packages'), 'dir');
    const linkedTarget = spawnSync('/bin/bash', [recoveryScript, '--archive', archive, '--confirm'], {
      cwd: fixture.project,
      encoding: 'utf8',
      env: restoreEnv,
    });
    assert.notEqual(linkedTarget.status, 0);
    assert.match(`${linkedTarget.stdout}\n${linkedTarget.stderr}`, /restore_target_symlink/);
    await assert.rejects(access(join(outsideTarget, 'clawbot', 'data', 'history.db'), constants.F_OK));
    await rm(restoreRoot, { recursive: true, force: true });

    await appendFile(archive, 'tampered', 'utf8');
    const damaged = spawnSync('/bin/bash', [recoveryScript, '--archive', archive, '--confirm'], {
      cwd: fixture.project,
      encoding: 'utf8',
      env: restoreEnv,
    });
    assert.notEqual(damaged.status, 0);
    assert.match(`${damaged.stdout}\n${damaged.stderr}`, /checksum_mismatch/);
    await assert.rejects(access(join(restoreRoot, '.env'), constants.F_OK));

    const malicious = join(fixture.backupDir, 'openeverything-malicious.tgz');
    const built = spawnSync(
      'python3',
      [
        '-c',
        [
          'import io,sys,tarfile',
          'with tarfile.open(sys.argv[1], "w:gz") as archive:',
          '    item=tarfile.TarInfo("payload/project/../../escape.txt")',
          '    body=b"escape"',
          '    item.size=len(body)',
          '    archive.addfile(item, io.BytesIO(body))',
        ].join('\n'),
        malicious,
      ],
      { encoding: 'utf8' },
    );
    assert.equal(built.status, 0, built.stderr);
    const digest = createHash('sha256').update(await readFile(malicious)).digest('hex');
    await writeFile(`${malicious}.sha256`, `${digest}  ${basename(malicious)}\n`, 'utf8');
    await writeFile(`${malicious}.ready`, `${digest}\n`, 'utf8');

    const traversed = spawnSync('/bin/bash', [recoveryScript, '--archive', malicious], {
      cwd: fixture.project,
      encoding: 'utf8',
      env: restoreEnv,
    });
    assert.notEqual(traversed.status, 0);
    assert.match(`${traversed.stdout}\n${traversed.stderr}`, /unsafe_archive_path/);
    await assert.rejects(access(join(fixture.sandbox, 'escape.txt'), constants.F_OK));
  } finally {
    await rm(fixture.sandbox, { recursive: true, force: true });
  }
});

test('backup enforces optional offsite requirements and count retention', async () => {
  const fixture = await createBackupSandbox();
  let gpgHome = '';
  try {
    const missingOffsite = runLocalBackup(fixture, ['--require-offsite']);
    assert.notEqual(missingOffsite.status, 0);
    assert.match(`${missingOffsite.stdout}\n${missingOffsite.stderr}`, /offsite_not_configured/);

    const offsiteDir = join(fixture.sandbox, 'offsite');
    const unencryptedOffsite = runLocalBackup(fixture, [], {
      OPENCLAW_BACKUP_STAMP: '20260805-040400',
      OPENCLAW_BACKUP_OFFSITE_DIR: offsiteDir,
    });
    assert.notEqual(unencryptedOffsite.status, 0);
    assert.match(`${unencryptedOffsite.stdout}\n${unencryptedOffsite.stderr}`, /offsite_encryption_not_configured/);

    gpgHome = await mkdtemp(join(tmpdir(), 'ocgpg-'));
    await chmod(gpgHome, 0o700);
    const identity = 'OpenClaw Backup Test <backup-test@openclaw.invalid>';
    const generated = spawnSync(
      'gpg',
      ['--batch', '--homedir', gpgHome, '--passphrase', '', '--quick-generate-key', identity, 'rsa2048', 'encr', '1d'],
      { encoding: 'utf8' },
    );
    assert.equal(generated.status, 0, generated.stderr);
    const listed = spawnSync('gpg', ['--batch', '--homedir', gpgHome, '--with-colons', '--list-keys'], {
      encoding: 'utf8',
    });
    assert.equal(listed.status, 0, listed.stderr);
    const recipient = listed.stdout.split('\n').find((line) => line.startsWith('fpr:'))?.split(':')[9] || '';
    assert.match(recipient, /^[0-9A-F]{40}$/);

    for (const stamp of ['20260805-040401', '20260805-040402']) {
      const result = runLocalBackup(fixture, ['--require-offsite'], {
        OPENCLAW_BACKUP_STAMP: stamp,
        OPENCLAW_BACKUP_RETENTION_COUNT: '1',
        OPENCLAW_BACKUP_OFFSITE_DIR: offsiteDir,
        OPENCLAW_BACKUP_GPG_RECIPIENT: recipient,
        GNUPGHOME: gpgHome,
      });
      assert.equal(result.status, 0, result.stderr);
    }

    const localArchives = (await readdir(fixture.backupDir)).filter((name) => name.endsWith('.tgz'));
    const offsiteArchives = (await readdir(offsiteDir)).filter((name) => name.endsWith('.tgz.gpg'));
    assert.deepEqual(localArchives, ['openeverything-20260805-040402.tgz']);
    assert.deepEqual(offsiteArchives, ['openeverything-20260805-040402.tgz.gpg']);
    await access(join(offsiteDir, `${offsiteArchives[0]}.sha256`), constants.F_OK);
    await access(join(offsiteDir, `${offsiteArchives[0]}.ready`), constants.F_OK);
    assert.equal((await readdir(offsiteDir)).some((name) => name.endsWith('.tgz')), false);

    const recoveryScript = join(fixture.project, 'scripts', 'disaster_recovery.sh');
    const drill = spawnSync('/bin/bash', [recoveryScript, '--from-offsite', '--drill'], {
      cwd: fixture.project,
      encoding: 'utf8',
      env: {
        ...process.env,
        HOME: fixture.home,
        GNUPGHOME: gpgHome,
        OPENCLAW_BACKUP_DIR: fixture.backupDir,
        OPENCLAW_BACKUP_OFFSITE_DIR: offsiteDir,
      },
    });
    assert.equal(drill.status, 0, drill.stderr);
    assert.match(drill.stdout, /restore drill passed/);
  } finally {
    if (gpgHome) {
      spawnSync('gpgconf', ['--homedir', gpgHome, '--kill', 'gpg-agent'], { encoding: 'utf8' });
      await rm(gpgHome, { recursive: true, force: true });
    }
    await rm(fixture.sandbox, { recursive: true, force: true });
  }
});

test('daily backup LaunchAgent install status and uninstall are safe and idempotent', async () => {
  const fixture = await createBackupSandbox();
  try {
    const stubs = await createBackupLaunchctlStubs(fixture.sandbox);
    const manager = join(fixture.project, 'scripts', 'manage_backup_launchagent.sh');
    const launchAgent = join(fixture.home, 'Library', 'LaunchAgents', 'ai.openclaw.daily-backup.plist');
    const env = {
      ...stubs.env,
      HOME: fixture.home,
      OPENCLAW_BACKUP_DIR: fixture.backupDir,
      OPENCLAW_BACKUP_HOUR: '4',
      OPENCLAW_BACKUP_MINUTE: '15',
      OPENCLAW_BACKUP_OFFSITE_DIR: '',
      OPENCLAW_BACKUP_GPG_RECIPIENT: '',
    };

    const installed = spawnSync('/bin/bash', [manager, 'install'], {
      cwd: fixture.project,
      encoding: 'utf8',
      env,
    });
    assert.equal(installed.status, 0, installed.stderr);
    assert.equal((await stat(launchAgent)).mode & 0o777, 0o600);
    const parsed = spawnSync(
      'python3',
      [
        '-c',
        'import json,plistlib,sys; print(json.dumps(plistlib.load(open(sys.argv[1], "rb"))))',
        launchAgent,
      ],
      { encoding: 'utf8' },
    );
    assert.equal(parsed.status, 0, parsed.stderr);
    const plist = JSON.parse(parsed.stdout);
    const canonicalManager = await realpath(manager);
    assert.equal(plist.Label, 'ai.openclaw.daily-backup');
    assert.deepEqual(plist.ProgramArguments, ['/bin/bash', canonicalManager, 'run']);
    assert.deepEqual(plist.StartCalendarInterval, { Hour: 4, Minute: 15 });
    assert.equal(plist.EnvironmentVariables.HOME, fixture.home);
    assert.equal(plist.EnvironmentVariables.OPENCLAW_BACKUP_DIR, fixture.backupDir);
    assert.equal(plist.RunAtLoad, false);
    assert.equal(plist.KeepAlive, false);

    const status = spawnSync('/bin/bash', [manager, 'status'], {
      cwd: fixture.project,
      encoding: 'utf8',
      env,
    });
    assert.equal(status.status, 0, status.stderr);
    assert.equal(JSON.parse(status.stdout).loaded, true);

    const reinstalled = spawnSync('/bin/bash', [manager, 'install'], {
      cwd: fixture.project,
      encoding: 'utf8',
      env,
    });
    assert.equal(reinstalled.status, 0, reinstalled.stderr);
    const calls = await readFile(stubs.callsFile, 'utf8');
    assert.equal((calls.match(/launchctl bootstrap /g) || []).length, 2);
    assert.match(calls, /launchctl bootout /);

    for (let attempt = 0; attempt < 2; attempt += 1) {
      const removed = spawnSync('/bin/bash', [manager, 'uninstall'], {
        cwd: fixture.project,
        encoding: 'utf8',
        env,
      });
      assert.equal(removed.status, 0, removed.stderr);
    }
    await assert.rejects(access(launchAgent, constants.F_OK));

    const failed = spawnSync('/bin/bash', [manager, 'install'], {
      cwd: fixture.project,
      encoding: 'utf8',
      env: { ...env, OPENCLAW_TEST_BOOTSTRAP_FAIL: '1' },
    });
    assert.notEqual(failed.status, 0);
    assert.match(`${failed.stdout}\n${failed.stderr}`, /launchagent_bootstrap_failed/);
    await assert.rejects(access(launchAgent, constants.F_OK));
  } finally {
    await rm(fixture.sandbox, { recursive: true, force: true });
  }
});

test('daily backup runner creates a local backup and drills it before reporting success', async () => {
  const fixture = await createBackupSandbox();
  try {
    const manager = join(fixture.project, 'scripts', 'manage_backup_launchagent.sh');
    const env = {
      ...process.env,
      HOME: fixture.home,
      OPENCLAW_BACKUP_DIR: fixture.backupDir,
      OPENCLAW_BACKUP_STAMP: '20260805-050501',
      OPENCLAW_BACKUP_OFFSITE_DIR: '',
      OPENCLAW_BACKUP_GPG_RECIPIENT: '',
    };
    const run = spawnSync('/bin/bash', [manager, 'run'], {
      cwd: fixture.project,
      encoding: 'utf8',
      env,
    });
    assert.equal(run.status, 0, run.stderr);
    assert.match(run.stdout, /restore drill passed/);
    await access(join(fixture.backupDir, 'openeverything-20260805-050501.tgz.ready'), constants.F_OK);

    await writeExecutable(
      join(fixture.project, 'scripts', 'disaster_recovery.sh'),
      'printf "forced drill failure\\n" >&2; exit 78',
    );
    const drillFailed = spawnSync('/bin/bash', [manager, 'run'], {
      cwd: fixture.project,
      encoding: 'utf8',
      env: { ...env, OPENCLAW_BACKUP_STAMP: '20260805-050502' },
    });
    assert.notEqual(drillFailed.status, 0);
    assert.match(drillFailed.stderr, /daily_backup_drill_failed/);
    assert.doesNotMatch(drillFailed.stdout, /"ok":\s*true/);

    const failed = spawnSync('/bin/bash', [manager, 'run'], {
      cwd: fixture.project,
      encoding: 'utf8',
      env: { ...env, OPENCLAW_BACKUP_STAMP: 'invalid' },
    });
    assert.notEqual(failed.status, 0);
    assert.doesNotMatch(failed.stdout, /restore drill passed/);
  } finally {
    await rm(fixture.sandbox, { recursive: true, force: true });
  }
});

test('daily backup LaunchAgent rejects incomplete or unsafe offsite configuration', async () => {
  const fixture = await createBackupSandbox();
  try {
    const stubs = await createBackupLaunchctlStubs(fixture.sandbox);
    const manager = join(fixture.project, 'scripts', 'manage_backup_launchagent.sh');
    const baseEnv = {
      ...stubs.env,
      HOME: fixture.home,
      OPENCLAW_BACKUP_DIR: fixture.backupDir,
    };

    const incomplete = spawnSync('/bin/bash', [manager, 'install'], {
      cwd: fixture.project,
      encoding: 'utf8',
      env: {
        ...baseEnv,
        OPENCLAW_BACKUP_OFFSITE_DIR: join(fixture.sandbox, 'offsite'),
        OPENCLAW_BACKUP_GPG_RECIPIENT: '',
      },
    });
    assert.notEqual(incomplete.status, 0);
    assert.match(`${incomplete.stdout}\n${incomplete.stderr}`, /offsite_config_incomplete/);

    const relative = spawnSync('/bin/bash', [manager, 'install'], {
      cwd: fixture.project,
      encoding: 'utf8',
      env: {
        ...baseEnv,
        OPENCLAW_BACKUP_OFFSITE_DIR: 'relative/offsite',
        OPENCLAW_BACKUP_GPG_RECIPIENT: '0123456789ABCDEF',
      },
    });
    assert.notEqual(relative.status, 0);
    assert.match(
      `${relative.stdout}\n${relative.stderr}`,
      /openclaw_backup_offsite_dir_must_be_absolute/,
    );

    const source = await readFile(manager, 'utf8');
    assert.doesNotMatch(source, /BEGIN (PGP|PRIVATE KEY)|GPG_PASSPHRASE|SECRET_KEY/);
  } finally {
    await rm(fixture.sandbox, { recursive: true, force: true });
  }
});
