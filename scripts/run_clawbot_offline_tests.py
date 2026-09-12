#!/usr/bin/env python3
"""Run selected ClawBot tests in a fresh source copy without credentials/network.

Usage: python3 scripts/run_clawbot_offline_tests.py tests/test_cost_ledger.py
Uses the existing packages/clawbot/.venv312 interpreter. Output is ordinary pytest
output and the process exit status is preserved; no package installation occurs.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CONFIG_FILES = {
    "bot_profiles.py",
    "prompts.py",
    "notifications.yaml",
    "omega.yaml",
    "llm_routing.json",
}
CLI_FILES = {"intel_scheduler_gate_probe.py", "intel_scheduled_sandbox.py",
             "intel_telegram_sandbox_probe.py", "intel_telegram_summary_probe.py",
             "intel_telegram_update_processor_sandbox.py", "intel_production_cycle.py",
             "intel_collect_once.py", "intel_worker_remote_run.py", "intel_worker_bundle.py",
             "intel_launch_package.py", "intel_launchagent_next_run_readiness.py"}
ASSET_FILES = {"assets/intel/openclaw-intel-brief-dark.jpg"}


def copy_test_source(root, copied, paths):
    for relative in set(paths):
        if relative.startswith("packages/clawbot/config/"):
            if relative not in {
                f"packages/clawbot/config/{name}" for name in CONFIG_FILES
            }:
                continue
        elif not relative.startswith(
            ("packages/clawbot/src/", "packages/clawbot/tests/")
        ) and relative not in {
            "packages/clawbot/pytest.ini",
            "packages/clawbot/ruff.toml",
            "packages/clawbot/multi_main.py",
            *(f"packages/clawbot/{name}" for name in ASSET_FILES),
            *(f"packages/clawbot/scripts/{name}" for name in CLI_FILES),
        }:
            continue
        original = root / relative
        if not original.is_file() or original.is_symlink() or ".env" in original.name:
            continue
        destination = copied / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, destination)


GUARD = """import socket
import os
import pwd
test_directory = os.environ["OE_TEST_HOME"]
original_expanduser = os.path.expanduser
def expanduser(path):
    value = os.fspath(path)
    marker = b"~" if isinstance(value, bytes) else "~"
    slash = b"/" if isinstance(value, bytes) else "/"
    if value == marker or value.startswith(marker + slash):
        base = os.fsencode(test_directory) if isinstance(value, bytes) else test_directory
        return base + value[1:]
    return original_expanduser(path)
os.path.expanduser = expanduser
original_getpwuid = pwd.getpwuid
def getpwuid(uid):
    entry = original_getpwuid(uid)
    if uid == os.getuid():
        fields = list(entry)
        fields[5] = test_directory
        return pwd.struct_passwd(fields)
    return entry
pwd.getpwuid = getpwuid
def denied(*args, **kwargs):
    raise RuntimeError("offline test: network and DNS disabled")
def wrap(original):
    def checked(self, *args, **kwargs):
        if self.family in (socket.AF_INET, socket.AF_INET6):
            return denied()
        return original(self, *args, **kwargs)
    return checked
for name in ("connect", "connect_ex", "sendto", "sendmsg"):
    if hasattr(socket.socket, name):
        setattr(socket.socket, name, wrap(getattr(socket.socket, name)))
for name in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr"):
    setattr(socket, name, denied)
"""


def select_interpreter(root, override=None):
    if override is None:
        return root / "packages/clawbot/.venv312/bin/python"
    # Preserve the venv executable symlink: resolving it selects system Python.
    interpreter = Path(os.path.abspath(override))
    venv = interpreter.parent.parent
    if (not venv.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve())
            or not (venv / "pyvenv.cfg").is_file()
            or not interpreter.is_file()):
        raise ValueError("--python must belong to a temporary virtual environment")
    return interpreter


def copy_tokenizer_data(interpreter, destination):
    # A hashed dependency already carries this public vocabulary. Do not depend
    # on another run's shared /tmp cache or initiate downloads during testing.
    name = '9b5ad71b2ce5302211f9c61530b329a4922fc6a4'
    relative = 'lib/python3.12/site-packages/litellm/litellm_core_utils/tokenizers'
    data = (interpreter.parent.parent / relative / name).read_bytes()
    if hashlib.sha256(data).hexdigest() != '223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7':
        raise ValueError('bundled public tokenizer digest does not match the frozen SDK')
    destination.mkdir()
    (destination / name).write_bytes(data)


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--python')
    options, pytest_args = parser.parse_known_args()
    root = Path(__file__).resolve().parents[1]
    interpreter = select_interpreter(root, options.python)
    if not interpreter.is_file():
        raise SystemExit(
            "Existing Python 3.12 environment is required: packages/clawbot/.venv312"
        )
    paths = (
        subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=root,
        )
        .decode()
        .split("\0")
    )
    with tempfile.TemporaryDirectory(prefix="oe-offline-") as directory:
        copied = Path(directory)
        copy_test_source(root, copied, paths)
        digest = hashlib.sha256()
        for source in sorted(path for path in copied.rglob('*') if path.is_file()):
            digest.update(str(source.relative_to(copied)).encode() + b'\0' + source.read_bytes() + b'\0')
        print(f'Source snapshot SHA256: {digest.hexdigest()}', flush=True)
        guard = copied / "guard"
        guard.mkdir()
        (guard / "sitecustomize.py").write_text(GUARD)
        copy_tokenizer_data(interpreter, guard / "tokenizers")
        env = {
            key: value
            for key, value in os.environ.items()
            if key in {"PATH", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT"}
        }
        test_directory = copied / "user"
        test_directory.mkdir()
        env.update(
            TESTING="true",
            LITELLM_LOG="ERROR",
            PYTHONDONTWRITEBYTECODE="1",
            PYTHONPATH=str(guard),
            OE_TEST_HOME=str(test_directory),
            TIKTOKEN_CACHE_DIR=str(guard / "tokenizers"),
            XDG_CACHE_HOME=str(test_directory / ".cache"),
            PYTHON_DOTENV_DISABLED="1",
        )
        # macOS enforces the boundary for native libraries and child processes,
        # too. HOME/CODEX_HOME are never reassigned. Only the installed venv is
        # readable below the real user directory; all user-directory writes fail.
        if sys.platform != "darwin" or not Path("/usr/bin/sandbox-exec").is_file():
            raise SystemExit("This local runner requires the macOS filesystem sandbox")
        profile = copied / "offline.sb"
        real_user = json.dumps(str(Path.home().resolve()))
        dependency_path = json.dumps(str(interpreter.parent.parent.resolve()))
        profile.write_text(
            "(version 1)(allow default)"
            '(deny network-outbound (remote ip "*:*"))'
            f"(deny file-read-data (require-all (subpath {real_user}) "
            f"(require-not (subpath {dependency_path}))))"
            f"(deny file-write* (subpath {real_user}))"
        )
        prefix = ["/usr/bin/sandbox-exec", "-f", str(profile)]
        probe = """import os, pathlib, socket, sys
assert str(pathlib.Path.home()) == os.environ["OE_TEST_HOME"]
assert os.path.expanduser("~") == os.environ["OE_TEST_HOME"]
assert "HOME" not in os.environ and "CODEX_HOME" not in os.environ
try:
    pathlib.Path(sys.argv[1]).read_bytes()
except PermissionError:
    pass
else:
    raise AssertionError("real workspace outside copied source was readable")
try:
    socket.create_connection(("192.0.2.1", 443), timeout=0.1)
except RuntimeError:
    pass
else:
    raise AssertionError("network guard failed")
print("Offline guard PASS: temporary user paths, real home denied, network denied", flush=True)
"""
        subprocess.run(
            [*prefix, str(interpreter), "-c", probe, str(root / "README.md")],
            cwd=copied,
            env=env,
            check=True,
        )
        command = [
            str(interpreter),
            "-m",
            "pytest",
            *pytest_args,
            "--tb=short",
            "-q",
            "-o",
            "addopts=",
            "--timeout=30",
        ]
        return subprocess.call(
            [*prefix, *command], cwd=copied / "packages/clawbot", env=env
        )


if __name__ == "__main__":
    raise SystemExit(main())
