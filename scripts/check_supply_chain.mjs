import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

const root = new URL('../', import.meta.url);
const read = (path) => readFileSync(new URL(path, root), 'utf8');

for (const composeFile of ['docker-compose.yml', 'docker-compose.frist-api.yml', 'docker-compose.newapi.yml']) {
  const compose = read(composeFile);
  for (const match of compose.matchAll(/^\s*image:\s*([^\s#]+)/gm)) {
    assert.match(
      match[1],
      /^[^@\s]+@sha256:[0-9a-f]{64}$/,
      `${composeFile}: 外部容器镜像必须固定 tag@sha256 digest`,
    );
  }
}

const clawbotDockerfile = read('packages/clawbot/Dockerfile');
const compose = read('docker-compose.yml');
const pinnedPythonImage = 'python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de';
assert.equal(
  [...clawbotDockerfile.matchAll(/^FROM\s+([^\s]+)(?:\s+AS\s+\w+)?$/gm)].filter((match) => match[1].startsWith('python:')).length,
  2,
  'ClawBot Dockerfile 应保留 builder/runtime 两个 Python 阶段',
);
for (const match of clawbotDockerfile.matchAll(/^FROM\s+(python:[^\s]+)(?:\s+AS\s+\w+)?$/gm)) {
  assert.equal(match[1], pinnedPythonImage, 'ClawBot Python 基础镜像必须固定当前多架构 digest');
}
assert.match(clawbotDockerfile, /COPY requirements-lock\.txt/);
assert.match(clawbotDockerfile, /pip install[^\n]*--require-hashes[^\n]*--only-binary=:all:/);
const sourceBuildAllowlist = clawbotDockerfile.match(/--no-binary=([^\s]+)/)?.[1];
assert.equal(
  sourceBuildAllowlist,
  'jieba,jsonpath,pyjsparser,sgmllib3k,snownlp,ta',
  '源码构建白名单只允许六个没有 Python 3.12/Linux wheel 的纯 Python 包',
);
assert.match(compose, /openclaw:\n(?:[\s\S]*?\n)?\s+platform: linux\/amd64\n/);
assert.match(compose, /X-API-Token/);
assert.doesNotMatch(clawbotDockerfile, /COPY requirements\.txt|\s-r requirements\.txt/);

const workflowDir = new URL('.github/workflows/', root);
const workflowFiles = readdirSync(workflowDir)
  .filter((name) => name.endsWith('.yml') || name.endsWith('.yaml'))
  .sort();
const ciWorkflow = read('.github/workflows/ci.yml');
const ciLines = ciWorkflow.split('\n');
const pullRequestStart = ciLines.findIndex((line) => line === '  pull_request:');
assert.notEqual(pullRequestStart, -1, '主 CI 必须监听 pull_request');
const pullRequestBody = [];
for (const line of ciLines.slice(pullRequestStart + 1)) {
  if (line !== '' && !line.startsWith('    ')) break;
  pullRequestBody.push(line);
}
assert.ok(
  !pullRequestBody.some((line) => line.startsWith('    branches:')),
  '主 CI 的 pull_request 不得限制目标分支，否则堆叠 PR 会绕过门禁',
);

const makefile = read('Makefile');
for (const target of ['shellcheck', 'gitleaks-check', 'dependency-audit', 'rust-audit', 'supply-chain-check']) {
  assert.match(makefile, new RegExp(`^${target}:`, 'm'), `Makefile 缺少 ${target} 门禁`);
}
for (const target of ['shellcheck', 'dependency-audit', 'supply-chain-check']) {
  assert.match(ciWorkflow, new RegExp(`run: make ${target}`), `主 CI 未执行 make ${target}`);
}
assert.match(ciWorkflow, /uses: gitleaks\/gitleaks-action@[0-9a-f]{40}/, '主 CI 未执行固定 SHA 的 Gitleaks');
assert.match(ciWorkflow, /cargo install cargo-audit --locked/, '主 CI 未安装锁定的 RustSec 审计工具');
assert.match(ciWorkflow, /cargo audit --file Cargo\.lock/, '主 CI 未审计桌面 Cargo.lock');

let actionCount = 0;
for (const name of workflowFiles) {
  const source = read(join('.github/workflows', name));
  assert.doesNotMatch(
    source,
    /paths-ignore:[\s\S]*?apps\/openclaw\/\*\*/,
    `${name}: 运行资产目录 apps/openclaw 不得整体跳过 CI`,
  );
  for (const match of source.matchAll(/\buses:\s*([^\s#]+)/g)) {
    const action = match[1];
    if (action.startsWith('./')) continue;
    const separator = action.lastIndexOf('@');
    assert.notEqual(separator, -1, `${name}: Action 缺少版本引用: ${action}`);
    const revision = action.slice(separator + 1);
    assert.match(revision, /^[0-9a-f]{40}$/, `${name}: Action 必须固定完整 commit SHA: ${action}`);
    actionCount += 1;
  }
}

const runtimeDir = 'apps/openclaw-manager-src/src-tauri/npm-runtime-lock/';
const runtimePackage = JSON.parse(read(`${runtimeDir}package.json`));
const runtimeLock = JSON.parse(read(`${runtimeDir}package-lock.json`));
assert.equal(runtimeLock.lockfileVersion, 3, '受管 npm 运行时必须使用 lockfileVersion 3');
assert.ok(Object.hasOwn(runtimePackage.dependencies, 'openclaw'), '受管运行时必须登记 OpenClaw');

const exactVersion = /^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$/;
for (const [name, version] of Object.entries(runtimePackage.dependencies)) {
  assert.match(version, exactVersion, `${name} 必须固定精确版本`);
  const entry = runtimeLock.packages[`node_modules/${name}`];
  assert.ok(entry, `${name} 未进入 npm 完整性锁`);
  assert.equal(entry.version, version, `${name} 的 manifest 与 lock 版本不一致`);
  assert.match(entry.integrity || '', /^sha512-/, `${name} 缺少 SHA-512 完整性`);
  assert.match(entry.resolved || '', /^https:\/\/registry\.npmjs\.org\//, `${name} 不是固定 npm registry 工件`);
}

for (const [name, version] of Object.entries(runtimePackage.overrides || {})) {
  assert.match(version, exactVersion, `${name} 的安全覆盖必须固定精确版本`);
  const suffix = `node_modules/${name}`;
  const entries = Object.entries(runtimeLock.packages).filter(([path]) => path.endsWith(suffix));
  assert.ok(entries.length > 0, `${name} 的安全覆盖没有进入 npm 完整性锁`);
  for (const [path, entry] of entries) {
    assert.equal(entry.version, version, `${path} 未使用登记的安全覆盖版本`);
    assert.match(entry.integrity || '', /^sha512-/, `${path} 的安全覆盖缺少 SHA-512 完整性`);
  }
}

function assertRegistryLockedPackage(path, entry) {
  assert.match(
    entry.resolved || '',
    /^https:\/\/registry\.npmjs\.org\//,
    `${path} 的传递依赖不是受信 npm registry 工件`,
  );
  assert.match(entry.integrity || '', /^sha512-/, `${path} 的传递依赖缺少 SHA-512 完整性`);
}

for (const [path, entry] of Object.entries(runtimeLock.packages)) {
  if (!path) continue;
  assertRegistryLockedPackage(path, entry);
}
assert.throws(
  () => assertRegistryLockedPackage('node_modules/untrusted', { resolved: 'git+https://example.invalid/repo.git' }),
  /不是受信 npm registry 工件/,
  '供应链门必须拒绝未来新增的 git/http/file 传递依赖',
);

const snapshotPackage = JSON.parse(read('packages/openclaw-npm/package.json'));
const snapshotZalo = JSON.parse(read('packages/openclaw-npm/extensions/zalo/package.json'));
const snapshotSecurityPins = {
  hono: '4.12.34',
  sharp: '0.35.0',
  tar: '7.5.21',
  undici: '7.29.0',
};
for (const [name, version] of Object.entries(snapshotSecurityPins)) {
  assert.equal(snapshotPackage.dependencies[name], version, `OpenClaw 上游快照的 ${name} 安全版本已漂移`);
}
for (const [name, version] of Object.entries({
  hono: '4.12.34',
  tar: '7.5.21',
  undici: '7.29.0',
  postcss: '8.5.25',
  'fast-uri': '3.1.4',
  'js-yaml': '4.3.0',
  minimatch: '10.2.6',
})) {
  assert.equal(snapshotPackage.pnpm.overrides[name], version, `OpenClaw 上游快照的 ${name} override 已漂移`);
}
assert.equal(snapshotZalo.dependencies.undici, '7.29.0', 'Zalo 扩展必须使用已修复的 Undici');

const weixinDir = '.openclaw/extensions/openclaw-weixin/';
const weixinPackage = JSON.parse(read(`${weixinDir}package.json`));
const weixinLock = JSON.parse(read(`${weixinDir}package-lock.json`));
for (const [name, version] of Object.entries({ 'brace-expansion': '2.1.4', postcss: '8.5.25' })) {
  assert.equal(weixinPackage.overrides[name], version, `微信插件的 ${name} 安全覆盖已漂移`);
  const suffix = `node_modules/${name}`;
  const entries = Object.entries(weixinLock.packages).filter(([path]) => path.endsWith(suffix));
  assert.ok(entries.length > 0, `微信插件的 ${name} 安全覆盖没有进入 lock`);
  for (const [path, entry] of entries) {
    assert.equal(entry.version, version, `${path} 未使用微信插件登记的安全覆盖版本`);
    assertRegistryLockedPackage(path, entry);
  }
}

const installer = read('apps/openclaw-manager-src/src-tauri/src/commands/installer.rs');
const desktopConfig = read('apps/openclaw-manager-src/src-tauri/src/commands/config.rs');
const mcp = read('apps/openclaw-manager-src/src-tauri/src/commands/mcp.rs');
const npmRuntime = read('apps/openclaw-manager-src/src-tauri/src/commands/npm_runtime.rs');
assert.doesNotMatch(installer, /npm install -g/, '桌面安装器不得绕过 npm 完整性锁做全局安装');
assert.match(
  desktopConfig,
  /openclaw plugins install @m1heng-clawd\/feishu@0\.1\.19/,
  '飞书插件安装必须固定已审计精确版本',
);
assert.doesNotMatch(
  desktopConfig,
  /openclaw plugins install @m1heng-clawd\/feishu(?:["\\]|\s|$)/,
  '飞书插件不得保留无版本安装指引',
);
assert.match(mcp, /MANAGED_MCP_PACKAGES/, 'MCP Store 必须从类型化受管注册表派生目录');
assert.doesNotMatch(mcp, /Command::new|Stdio::null|std::fs/, 'MCP Store 不得伪装成未实现的 stdio 客户端');

const managedPackages = [...npmRuntime.matchAll(
  /ManagedMcpPackage\s*\{[\s\S]*?package_name:\s*"([^"]+)"[\s\S]*?binary_name:\s*"([^"]+)"[\s\S]*?\}/g,
)];
assert.equal(managedPackages.length, Object.keys(runtimePackage.dependencies).length - 1);
for (const [, packageName, binaryName] of managedPackages) {
  const entry = runtimeLock.packages[`node_modules/${packageName}`];
  assert.ok(entry, `MCP 注册包 ${packageName} 未进入 lock`);
  assert.ok(Object.hasOwn(entry.bin || {}, binaryName), `${packageName} 缺少注册二进制 ${binaryName}`);
}

console.log(`供应链检查通过：${workflowFiles.length} 个工作流、${actionCount} 个 Action SHA、${Object.keys(runtimeLock.packages).length - 1} 个 npm 锁定包`);
