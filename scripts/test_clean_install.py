import tempfile
import unittest
from pathlib import Path
from check_clean_install import public_path, supported_tool_version
from run_clawbot_offline_tests import select_interpreter


class GuardTests(unittest.TestCase):
    def test_supported_versions_reject_unverified_platform_toolchains(self):
        for tool, version in [('python', 'Python 3.12.13'), ('node', 'v22.22.3'), ('node', 'v24.1.0'), ('npm', '10.9.8'), ('npm', '11.0.0')]:
            self.assertTrue(supported_tool_version(tool, version))
        for tool, version in [('python', '3.13.0'), ('node', 'v18.0.0'), ('node', 'v22.18.0'), ('node', 'v23.0.0'), ('npm', '9.9.9'), ('node', 'unknown')]:
            self.assertFalse(supported_tool_version(tool, version))

    def test_public_source_boundary(self):
        for name in ['apps/openclaw-manager-src/src/x.ts', '.openclaw/extensions/openclaw-weixin/src/x.ts']:
            self.assertTrue(public_path(name))
        for name in ['apps/openclaw-manager-src/.env.local', 'apps/openclaw-manager-src/src/node_modules/secret', 'data/private.json', '.openclaw/credentials.json']:
            self.assertFalse(public_path(name))

    def test_override_requires_temporary_virtualenv_and_keeps_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            executable = base / 'venv/bin/python'
            executable.parent.mkdir(parents=True)
            executable.symlink_to('/usr/bin/python3')
            with self.assertRaises(ValueError):
                select_interpreter(Path('/synthetic'), str(executable))
            (base / 'venv/pyvenv.cfg').write_text('synthetic fixture')
            self.assertEqual(select_interpreter(Path('/synthetic'), str(executable)), executable)
        with self.assertRaises(ValueError):
            select_interpreter(Path('/synthetic'), '/usr/bin/python3')


if __name__ == '__main__':
    unittest.main()
