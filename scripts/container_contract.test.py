"""Compose/health contract using synthetic files; never uses a production daemon.

Optional OE_DOCKER_TEST_HOST=unix://<isolated socket> enables a scratch-only
BuildKit context-export test. It starts no application or container.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class ContainerContract(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='oe-container-contract-', dir=os.getenv('OE_CONTAINER_TEST_TMP'))
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.context = self.root / 'packages/clawbot'
        self.context.mkdir(parents=True)
        (self.context / 'config').mkdir()
        for relative in ['docker-compose.yml', 'packages/clawbot/Dockerfile', 'packages/clawbot/.dockerignore']:
            shutil.copyfile(ROOT / relative, self.root / relative)
        (self.context / 'config/.env').write_text('')
        self.docker = os.getenv('OE_DOCKER') or shutil.which('docker')
        self.assertTrue(self.docker, 'Docker CLI required for Compose contract validation')
        config = self.root / 'docker-config'
        config.mkdir()
        plugins = Path('/Applications/Docker.app/Contents/Resources/cli-plugins')
        (config / 'config.json').write_text(json.dumps({'cliPluginsExtraDirs': [str(plugins)]} if plugins.is_dir() else {}))
        self.env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'DOCKER_CONFIG': str(config),
                    'DOCKER_HOST': 'unix:///nonexistent-oe-test-socket', 'COMPOSE_DISABLE_ENV_FILE': '1'}

    def compose(self, values):
        path = self.root / 'synthetic.env'
        path.write_text('\n'.join(f'{key}={value}' for key, value in values.items()) + '\n')
        return subprocess.run([self.docker, 'compose', '--project-directory', str(self.root), '--env-file', str(path),
                               '--file', str(self.root / 'docker-compose.yml'), 'config', '--format', 'json'],
                              env=self.env, cwd=self.root, capture_output=True, text=True, timeout=30)

    def test_missing_or_empty_secrets_fail_configuration(self):
        for values in [{}, {'REDIS_PASSWORD': 'synthetic'}, {'OPENCLAW_API_TOKEN': 'synthetic'},
                       {'REDIS_PASSWORD': 'synthetic', 'OPENCLAW_API_TOKEN': ''}]:
            with self.subTest(keys=list(values)):
                self.assertNotEqual(self.compose(values).returncode, 0)

    def test_normalized_compose_preserves_network_and_volume_contract(self):
        result = self.compose({'REDIS_PASSWORD': 'synthetic-redis', 'OPENCLAW_API_TOKEN': 'synthetic-api'})
        self.assertEqual(result.returncode, 0, result.stderr)
        config = json.loads(result.stdout)
        app = config['services']['openclaw']
        self.assertEqual(app['platform'], 'linux/amd64')
        self.assertEqual(app['environment']['API_HOST'], '0.0.0.0')
        self.assertEqual(app['environment']['ENV'], 'production')
        self.assertEqual(app['environment']['PYTHON_DOTENV_DISABLED'], '1')
        self.assertEqual(app['environment']['OPENCLAW_API_TOKEN'], 'synthetic-api')
        self.assertTrue(all(port['host_ip'] == '127.0.0.1' for port in app['ports']))
        self.assertFalse(config['services']['redis'].get('ports'))
        mounts = {mount['target']: mount for mount in app['volumes']}
        self.assertTrue(mounts['/app/config']['read_only'])
        self.assertFalse(mounts['/app/data'].get('read_only', False))
        self.assertFalse(mounts['/app/logs'].get('read_only', False))
        self.assertIn('ALL', app['cap_drop'])
        self.assertIn('no-new-privileges:true', app['security_opt'])
        self.assertTrue(config['networks']['clawbot-internal']['internal'])
        self.assertRegex(config['services']['redis']['image'], r'@sha256:[a-f0-9]{64}$')

    def test_actual_health_commands_require_and_forward_token(self):
        result = self.compose({'REDIS_PASSWORD': 'synthetic-redis', 'OPENCLAW_API_TOKEN': 'synthetic-api'})
        self.assertEqual(result.returncode, 0, result.stderr)
        commands = [json.loads(result.stdout)['services']['openclaw']['healthcheck']['test'][-1]]
        dockerfile = (self.context / 'Dockerfile').read_text()
        commands.append(re.search(r'CMD python -c "([^"]+)"', dockerfile).group(1))
        self.assertIn('USER clawbot', dockerfile)
        self.assertIn('--no-build-isolation', dockerfile)
        self.assertIn('--require-hashes', dockerfile)
        for command in commands:
            with patch.dict(os.environ, {'OPENCLAW_API_TOKEN': 'synthetic-api'}, clear=True), patch.object(urllib.request, 'urlopen') as transport:
                exec(compile(command, '<actual healthcheck>', 'exec'), {})
                request = transport.call_args.args[0]
                self.assertEqual(request.get_header('X-api-token'), 'synthetic-api')
                self.assertEqual(request.full_url, 'http://localhost:18790/api/v1/ping')
            with patch.dict(os.environ, {}, clear=True), patch.object(urllib.request, 'urlopen') as transport:
                with self.assertRaises(KeyError):
                    exec(compile(command, '<actual healthcheck>', 'exec'), {})
                transport.assert_not_called()

    @unittest.skipUnless(os.getenv('OE_DOCKER_TEST_HOST'), 'isolated Docker socket not supplied; context export unverified')
    def test_buildkit_context_excludes_synthetic_secrets(self):
        host = os.environ['OE_DOCKER_TEST_HOST']
        self.assertTrue(host.startswith('unix:///'), 'Only an explicitly supplied local test socket is supported')
        allowed = ['src/probe.py', 'src/nested/probe.py', 'multi_main.py', 'requirements-lock.txt', 'config/.env.example',
                   'config/bot_profiles.py', 'assets/intel/openclaw-intel-brief-dark.jpg']
        forbidden = ['secret.txt', 'config/.env', 'config/other.json', 'src/nested/runtime.token', 'src/nested/.env',
                     'src/nested/private.sqlite3', 'logs/raw.log', 'data/raw.json', 'src/nested/node_modules/leak.py']
        for path in allowed + forbidden:
            file = self.context / path
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text('SYNTHETIC_SECRET' if path in forbidden else 'public-fixture')
        probe = self.context / 'Dockerfile.context-probe'
        probe.write_text('FROM scratch\nCOPY . /\n')
        output = self.root / 'export'
        result = subprocess.run([self.docker, '--host', host, 'build', '--network', 'none', '--file', str(probe),
                                 '--output', f'type=local,dest={output}', str(self.context)],
                                env=self.env, cwd=self.root, capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr)
        for path in allowed:
            self.assertTrue((output / path).is_file(), path)
        for path in forbidden:
            self.assertFalse((output / path).exists(), path)
        self.assertFalse(any(b'SYNTHETIC_SECRET' in path.read_bytes() for path in output.rglob('*') if path.is_file()))


if __name__ == '__main__':
    unittest.main(verbosity=2)
