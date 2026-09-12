#!/usr/bin/env python3
"""Verify public locks in temporary directories on macOS, with guarded builds.

Fetches use public registries and an empty tool configuration. All package
lifecycle scripts are disabled; build/test commands run without outbound IP.
Python installs the host lock only. Cross-platform audits are a separate gate.
"""
import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from dependency_audit import audit_environment
from run_clawbot_offline_tests import copy_test_source

FRONTEND = 'apps/openclaw-manager-src'
RUNTIME = FRONTEND + '/src-tauri/npm-runtime-lock'
WEIXIN = '.openclaw/extensions/openclaw-weixin'
# These exact pure-Python source archives have had their build entrypoints reviewed.
SOURCE_HASHES = {
    'jieba': '055ca12f62674fafed09427f176506079bc135638a14e23e25be909131928db2',
    'jsonpath': 'd87ef2bcbcded68ee96bc34c1809b69457ecec9b0c4dd471658a12bd391002d1',
    'pyjsparser': 'be60da6b778cc5a5296a69d8e7d614f1f870faf94e1b1b6ac591f2ad5d729579',
    'sgmllib3k': '7868fb1c8bfa764c1ac563d3cf369c381d1325d36124933a726f29fcdaa812e9',
    'snownlp': 'c92accd025b70dd16706a10690f556ac9204bb6189f7dc68ece5c207c9bc27d8',
    'ta': 'de86af43418420bd6b088a2ea9b95483071bf453c522a8441bc2f12bcf8493fd',
}


def public_path(relative):
    path = Path(relative)
    if any(part in {'node_modules', '__pycache__', '.git'} or part.startswith('.venv') for part in path.parts):
        return False
    if '.env' in path.name:
        return False
    if relative.startswith((FRONTEND + '/src/', FRONTEND + '/public/', FRONTEND + '/src-tauri/src/',
                            FRONTEND + '/src-tauri/capabilities/', FRONTEND + '/src-tauri/icons/', WEIXIN + '/src/')):
        return True
    if path.parent == Path(FRONTEND):
        return path.name in {'package.json', 'package-lock.json', 'index.html', 'vite.config.ts', 'tsconfig.json',
                             'tsconfig.node.json', 'eslint.config.js', 'postcss.config.js', 'tailwind.config.js', 'components.json'}
    if path.parent == Path(FRONTEND + '/src-tauri'):
        return path.name in {'Cargo.toml', 'Cargo.lock', 'build.rs', 'tauri.conf.json'}
    if path.parent in {Path(RUNTIME), Path(WEIXIN)}:
        return path.name in {'package.json', 'package-lock.json', 'index.ts', 'openclaw.plugin.json'}
    return relative in {'scripts/cost_telemetry.test.mjs', 'scripts/onboarding.test.mjs'} or relative in {
        'packages/clawbot/requirements-lock.txt', 'packages/clawbot/requirements-lock-macos.txt'}


def copy_public_source(root, target, paths):
    copy_test_source(root, target, paths)
    for relative in set(paths):
        original = root / relative
        if public_path(relative) and original.is_file() and not original.is_symlink():
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, destination)


def supported_tool_version(tool, version):
    values = re.search(r'(\d+)\.(\d+)\.(\d+)', version)
    if values is None:
        return False
    major, minor, _ = map(int, values.groups())
    if tool == 'python':
        return (major, minor) == (3, 12)
    if tool == 'node':
        return (major == 22 and minor >= 19) or major == 24
    if tool == 'npm':
        return major in (10, 11)
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--component', choices=['all', 'desktop', 'runtime', 'weixin', 'python'], default='all')
    parser.add_argument('--keep', action='store_true', help='retain temporary installations and reports')
    parser.add_argument('--python', default=shutil.which('python3.12'))
    args = parser.parse_args()
    if sys.platform != 'darwin' or not Path('/usr/bin/sandbox-exec').is_file():
        parser.error('this local verifier requires the macOS filesystem sandbox; Linux CI verifies its own lock separately')
    if platform.machine() != 'arm64':
        parser.error('the macOS lock is verified for arm64 only')
    required = ['node', 'npm'] if args.component != 'python' else []
    if args.component in ('all', 'python'):
        required.extend(['python', 'uv'])
    for tool in required:
        executable = args.python if tool == 'python' else shutil.which(tool)
        if not executable:
            parser.error(f'{tool} is required before verification')
        version = subprocess.check_output([executable, '--version'], text=True).strip()
        if tool != 'uv' and not supported_tool_version(tool, version):
            parser.error(f'unsupported {tool} version: {version}; use Python 3.12, Node 22.19+/24, npm 10/11')
        print(f'TOOL {tool}: {version}', flush=True)
    root = Path(__file__).resolve().parents[1]
    work = Path(tempfile.mkdtemp(prefix='oe-clean-install-'))
    source = work / 'source'
    paths = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=root).decode().split('\0')
    copy_public_source(root, source, paths)
    env = audit_environment(work / 'config')
    env.update(NPM_CONFIG_IGNORE_SCRIPTS='true', XDG_CACHE_HOME=str(work / 'cache'),
               XDG_CONFIG_HOME=str(work / 'config'), UV_CACHE_DIR=str(work / 'uv-cache'),
               UV_NO_CONFIG='1', PIP_CONFIG_FILE=os.devnull, PIP_DISABLE_PIP_VERSION_CHECK='1', CI='true')
    exceptions = []
    for tool in ('node', 'npm', 'uv'):
        found = shutil.which(tool)
        if found:
            actual = Path(found).resolve()
            exceptions.append(actual.parents[1] if tool == 'npm' else actual)
    base = '(version 1)(allow default)' + '(deny file-read-data (require-all (subpath ' + json.dumps(str(Path.home().resolve())) + ') ' + ' '.join('(require-not (subpath ' + json.dumps(str(path)) + '))' for path in exceptions) + '))' + '(deny file-write* (subpath ' + json.dumps(str(Path.home().resolve())) + '))'
    (work / 'fetch.sb').write_text(base)
    (work / 'build.sb').write_text(base + '(deny network-outbound (remote ip "*:*"))')
    results = []
    print(f'WORK_DIR={work}', flush=True)

    def run(name, command, cwd=source, fetch=False, timeout=900):
        log = work / (name + '.log')
        row = {'name': name, 'command': command, 'log': str(log), 'network': 'public-fetch' if fetch else 'denied'}
        with log.open('w') as output:
            try:
                result = subprocess.run(['/usr/bin/sandbox-exec', '-f', str(work / ('fetch.sb' if fetch else 'build.sb')), *command],
                                        cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT, timeout=timeout)
                row['exit_code'] = result.returncode
            except (OSError, subprocess.TimeoutExpired) as exc:
                row.update(exit_code=1, failure=type(exc).__name__)
        results.append(row)
        (work / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
        print(f'{name}: exit={row["exit_code"]}; {log}', flush=True)
        return row['exit_code'] == 0

    try:
        if not run('isolation-probe', [args.python or '/usr/bin/python3', '-c',
                'import os,pathlib,socket,sys\n'
                'assert "HOME" not in os.environ and "CODEX_HOME" not in os.environ\n'
                'try: pathlib.Path(sys.argv[1]).read_bytes()\n'
                'except PermissionError: pass\n'
                'else: raise AssertionError("real workspace readable")\n'
                'try: socket.create_connection(("192.0.2.1",443),timeout=0.1)\n'
                'except PermissionError: pass\n'
                'else: raise AssertionError("outbound connection not denied")\n'
                'print("Guard PASS: real workspace and outbound network denied")', str(root / 'README.md')]):
            return 1
        for component, relative in [('desktop', FRONTEND), ('runtime', RUNTIME), ('weixin', WEIXIN)]:
            if args.component not in ('all', component):
                continue
            cwd = source / relative
            print(f'{component} lock SHA256: {hashlib.sha256((cwd / "package-lock.json").read_bytes()).hexdigest()}', flush=True)
            command = ['npm', 'ci', '--ignore-scripts', '--no-audit', '--no-fund']
            if component == 'runtime':
                command.append('--omit=dev')
            if not run(component + '-install', command, cwd, fetch=True):
                continue
            if component == 'desktop':
                run('desktop-types', ['node', 'node_modules/typescript/bin/tsc', '--noEmit'], cwd)
                run('desktop-lint', ['npm', 'run', 'lint'], cwd)
                run('desktop-build', ['npm', 'run', 'build'], cwd)
                run('desktop-security', ['node', '--test', FRONTEND + '/src/lib/security-hardening.static.test.mjs',
                    FRONTEND + '/src/components/Social/social-growth-feedback.static.test.mjs', 'scripts/cost_telemetry.test.mjs', 'scripts/onboarding.test.mjs'])
            elif component == 'runtime':
                run('runtime-bins', ['node', '-e', "const fs=require('fs'),p=require('path');const root=require('./package.json');for(const [name,version] of Object.entries(root.dependencies)){const dir=p.join('node_modules',name);const m=JSON.parse(fs.readFileSync(p.join(dir,'package.json')));if(m.version!==version)throw Error(name+' version');for(const bin of Object.values(typeof m.bin==='string'?{bin:m.bin}:m.bin||{})){if(!fs.statSync(p.join(dir,bin)).isFile())throw Error(name+' bin')}}console.log('exact direct versions and declared bin files verified; no runtime started')"], cwd)
            else:
                run('weixin-vitest-cli', ['node', 'node_modules/vitest/vitest.mjs', '--version'], cwd)
                run('weixin-source-syntax', ['node', '-e', "const fs=require('fs'),p=require('path'),ts=require('typescript');let count=0;function check(file){const result=ts.transpileModule(fs.readFileSync(file,'utf8'),{fileName:file,reportDiagnostics:true,compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}});const errors=(result.diagnostics||[]).filter(d=>d.category===ts.DiagnosticCategory.Error);if(errors.length)throw Error(ts.formatDiagnosticsWithColorAndContext(errors,{getCanonicalFileName:x=>x,getCurrentDirectory:()=>process.cwd(),getNewLine:()=>String.fromCharCode(10)}));count++}function walk(dir){for(const e of fs.readdirSync(dir,{withFileTypes:true})){const file=p.join(dir,e.name);if(e.isDirectory())walk(file);else if(file.endsWith('.ts')&&!file.endsWith('.d.ts'))check(file)}}check('index.ts');walk('src');console.log(count+' source files transpiled; semantic SDK types and upstream tests not verified')"], cwd)
                print('Weixin published source omits tsconfig and upstream tests: syntax and CLI only; semantic compilation/upstream suite not claimed.', flush=True)
        if args.component in ('all', 'python'):
            if not args.python:
                raise RuntimeError('python3.12 is required')
            lock = source / 'packages/clawbot/requirements-lock-macos.txt'
            print(f'Python macOS lock SHA256: {hashlib.sha256(lock.read_bytes()).hexdigest()}', flush=True)
            blocks = re.split(r'\n(?=[A-Za-z0-9])', lock.read_text())
            sources = [block for block in blocks if block.split('==')[0] in SOURCE_HASHES]
            for block in sources:
                if SOURCE_HASHES[block.split('==')[0]] not in block:
                    raise RuntimeError('source archive hash changed; review the new build entrypoint first')
            wheel_lock = work / 'wheels.txt'
            wheel_lock.write_text('\n'.join(block for block in blocks if block not in sources))
            bootstrap = work / 'bootstrap.txt'
            bootstrap.write_text('\n'.join(block for block in blocks if block.startswith(('setuptools==', 'packaging=='))))
            wheelhouse = work / 'wheelhouse'
            wheelhouse.mkdir()
            if run('python-wheel-fetch', [args.python, '-m', 'pip', 'download', '--index-url', 'https://pypi.org/simple', '--no-deps', '--require-hashes', '--only-binary=:all:', '-r', str(wheel_lock), '--dest', str(wheelhouse)], fetch=True):
                fetcher = work / 'fetch_sources.py'
                fetcher.write_text('import hashlib,json,pathlib,urllib.request\n' + f'items={repr([(b.split("==")[0], b.split("==")[1].split()[0], SOURCE_HASHES[b.split("==")[0]]) for b in sources])}\n' + f'out=pathlib.Path({str(wheelhouse)!r})\n' + '''for name,version,digest in items:
    with urllib.request.urlopen(f'https://pypi.org/pypi/{name}/{version}/json') as response: data=json.load(response)
    entry=next(item for item in data['urls'] if item['packagetype']=='sdist' and item['digests']['sha256']==digest)
    with urllib.request.urlopen(entry['url']) as response: content=response.read()
    assert hashlib.sha256(content).hexdigest()==digest
    (out/entry['filename']).write_bytes(content)
    print(name,version,'hash verified')
''')
                if run('python-source-fetch', [args.python, str(fetcher)], fetch=True) and run('python-venv', ['uv', 'venv', str(work / 'python'), '--python', args.python, '--no-project']):
                    interpreter = str(work / 'python/bin/python')
                    install = ['uv', 'pip', 'install', '--python', interpreter, '--offline', '--no-index', '--find-links', str(wheelhouse), '--require-hashes', '--no-deps', '--no-build-isolation']
                    if run('python-build-tools', [*install, '-r', str(bootstrap)]) and run('python-hash-install', [*install, '-r', str(lock)]):
                        run('python-check', ['uv', 'pip', 'check', '--python', interpreter])
                        # This runner applies its own guard and copies only approved source.
                        with (work / 'python-tests.log').open('w') as output:
                            process = subprocess.run([sys.executable, str(root / 'scripts/run_clawbot_offline_tests.py'), '--python', interpreter,
                                'tests/test_cost_ledger.py', 'tests/test_cost_control.py', 'tests/test_litellm_router.py', 'tests/test_litellm_accounting.py',
                                'tests/test_llm_cache.py', 'tests/test_structured_llm_router_isolation.py', 'tests/test_cost_api.py', 'tests/test_api_mixin.py',
                                'tests/test_llm_routing_config.py', 'tests/test_http_client.py', 'tests/test_chat_router_cost_controls.py',
                                'tests/test_rate_limiter.py', 'tests/test_api_security_middleware.py', 'tests/test_security.py',
                                'tests/test_api_routes_regression.py', 'tests/test_offline_isolation.py'], cwd=root, stdout=output, stderr=subprocess.STDOUT, timeout=900)
                        results.append({'name': 'python-tests', 'exit_code': process.returncode, 'log': str(work / 'python-tests.log')})
                        print(f'python-tests: exit={process.returncode}', flush=True)
        (work / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
        return int(any(row['exit_code'] for row in results))
    finally:
        if args.keep:
            print(f'Retained temporary evidence: {work}', flush=True)
        else:
            shutil.rmtree(work)


if __name__ == '__main__':
    raise SystemExit(main())
