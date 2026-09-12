"""Execute the documented config preparation only in a synthetic directory."""
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class LocalConfigExample(unittest.TestCase):
    def test_documented_generation_is_private_and_never_overwrites(self):
        document = (ROOT / 'docs/005-quickstart.md').read_text()
        code = re.search(r"python3 - <<'PYCONFIG'\n(.*?)\nPYCONFIG", document, re.S).group(1)
        with tempfile.TemporaryDirectory(prefix='oe-config-example-') as directory:
            base = Path(directory)
            config = base / 'packages/clawbot/config'
            config.mkdir(parents=True)
            (config / '.env.example').write_bytes((ROOT / 'packages/clawbot/config/.env.example').read_bytes())
            result = subprocess.run([sys.executable, '-c', code], cwd=base, capture_output=True, text=True,
                                    env={'PATH': os.environ.get('PATH', '/usr/bin:/bin')}, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            path = config / '.env'
            content = path.read_bytes()
            values = dict(re.findall(rb'^(OPENCLAW_API_TOKEN|REDIS_PASSWORD)=([^\n]+)$', content, re.M))
            self.assertEqual(set(values), {b'OPENCLAW_API_TOKEN', b'REDIS_PASSWORD'})
            for token in values.values():
                self.assertRegex(token, rb'^[a-f0-9]{64}$')
                self.assertNotIn(token.decode(), result.stdout + result.stderr)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            again = subprocess.run([sys.executable, '-c', code], cwd=base, capture_output=True, text=True, timeout=10)
            self.assertNotEqual(again.returncode, 0)
            self.assertIn('FileExistsError', again.stderr)
            self.assertEqual(path.read_bytes(), content)
            for token in values.values():
                self.assertNotIn(token.decode(), again.stdout + again.stderr)


if __name__ == '__main__':
    unittest.main()
