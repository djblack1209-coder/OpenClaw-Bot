"""Actual entry statements and pure bot configuration with synthetic files only."""
import ast
import importlib.util
import os
from pathlib import Path

import dotenv.main
import pytest


def run_entry(kind, directory):
    package = Path(__file__).resolve().parents[1]
    if kind == 'main':
        tree = ast.parse((package / 'multi_main.py').read_text())
        nodes = [node for node in tree.body if (
            isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == 'config_path' for target in node.targets)
        ) or (
            isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name) and node.value.func.id == 'load_dotenv'
        )]
        assert len(nodes) == 2
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<actual main config>', 'exec'), {
            'Path': Path, '__file__': str(directory / 'multi_main.py'), 'load_dotenv': dotenv.main.load_dotenv,
        })
    else:
        target = directory / 'src/bot/config.py'
        target.parent.mkdir(parents=True)
        target.write_bytes((package / 'src/bot/config.py').read_bytes())
        spec = importlib.util.spec_from_file_location('synthetic_bot_config', target)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


@pytest.mark.parametrize('kind', ['main', 'bot'])
def test_injected_environment_skips_unreadable_private_file(kind, tmp_path, monkeypatch):
    private = tmp_path / 'config/.env'
    private.parent.mkdir()
    private.write_text('SILICONFLOW_KEYS=synthetic-file-only\n')
    private.chmod(0o600)
    monkeypatch.setenv('PYTHON_DOTENV_DISABLED', '1')
    monkeypatch.setenv('SILICONFLOW_KEYS', 'synthetic-injected')
    monkeypatch.setenv('OPENCLAW_API_TOKEN', 'synthetic-api')
    opened = []

    def denied(*args, **kwargs):
        opened.append(args[0])
        raise PermissionError('synthetic owner mismatch')

    monkeypatch.setattr(dotenv.main, 'open', denied, raising=False)
    module = run_entry(kind, tmp_path)
    assert opened == []
    assert os.environ['OPENCLAW_API_TOKEN'] == 'synthetic-api'
    assert os.environ['SILICONFLOW_KEYS'] == 'synthetic-injected'
    if module:
        assert module.SILICONFLOW_KEYS == ['synthetic-injected']


@pytest.mark.parametrize('kind', ['main', 'bot'])
def test_local_file_loading_preserves_explicit_environment(kind, tmp_path, monkeypatch):
    private = tmp_path / 'config/.env'
    private.parent.mkdir()
    private.write_text('SILICONFLOW_KEYS=synthetic-file-only\nALLOWED_USER_IDS=999\n')
    monkeypatch.delenv('PYTHON_DOTENV_DISABLED', raising=False)
    monkeypatch.setenv('SILICONFLOW_KEYS', 'synthetic-injected')
    monkeypatch.delenv('ALLOWED_USER_IDS', raising=False)
    module = run_entry(kind, tmp_path)
    assert os.environ['SILICONFLOW_KEYS'] == 'synthetic-injected'
    assert os.environ['ALLOWED_USER_IDS'] == '999'
    if module:
        assert module.ALLOWED_USER_IDS == {999}


@pytest.mark.parametrize('kind', ['main', 'bot'])
def test_unreadable_local_configuration_is_not_silently_ignored(kind, tmp_path, monkeypatch):
    private = tmp_path / 'config/.env'
    private.parent.mkdir()
    private.write_text('SILICONFLOW_KEYS=synthetic-file-only\n')
    monkeypatch.delenv('PYTHON_DOTENV_DISABLED', raising=False)

    def denied(*args, **kwargs):
        raise PermissionError('synthetic owner mismatch')

    monkeypatch.setattr(dotenv.main, 'open', denied, raising=False)
    with pytest.raises(PermissionError, match='synthetic owner mismatch'):
        run_entry(kind, tmp_path)
