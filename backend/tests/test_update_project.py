import subprocess
import sys

import pytest
from scripts import update_project as updater


def test_ai_environment_merge_preserves_existing_values(tmp_path):
    path = tmp_path / '.env'
    original = 'DB_PASSWORD=local-test-value\nDEEPSEEK_API_KEY=existing-test-key\nWHISPER_MODEL=D:/models/custom\n'
    path.write_text(original, encoding='utf-8')
    updater.merge_ai_environment(path)
    first = path.read_text(encoding='utf-8')
    assert first.startswith(original)
    assert first.count('DEEPSEEK_API_KEY=') == 1
    assert first.count('WHISPER_MODEL=') == 1
    assert 'WHISPER_COMPUTE_TYPE=int8' in first
    updater.merge_ai_environment(path)
    assert path.read_text(encoding='utf-8') == first


def test_update_refuses_dirty_checkout_without_reset(monkeypatch):
    calls = []
    def fake_run(command, **kwargs):
        calls.append(command)
        if command[1] == 'rev-parse':
            return 'true'
        if command[1] == 'branch':
            return 'main'
        return ' M frontend/src/example.vue'
    monkeypatch.setattr(updater, 'run', fake_run)
    with pytest.raises(RuntimeError, match='未提交'):
        updater.require_clean_checkout()
    assert all('reset' not in command and 'clean' not in command for command in calls)


def test_check_mode_does_not_pull_or_modify_configuration(monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['update_project.py', '--check'])
    monkeypatch.setattr(updater, 'preflight', lambda: 'npm.cmd')
    monkeypatch.setattr(updater, 'run', lambda *args, **kwargs: pytest.fail('检查模式不应更新文件'))
    updater.main()


def test_failed_backup_stops_before_code_pull_and_migration(tmp_path, monkeypatch):
    backend = tmp_path / 'backend'
    backend.mkdir()
    (backend / '.env').write_text('DB_NAME=sample\n', encoding='utf-8')
    monkeypatch.setattr(sys, 'argv', ['update_project.py'])
    monkeypatch.setattr(updater, 'BACKEND', backend)
    monkeypatch.setattr(updater, 'preflight', lambda: 'npm.cmd')
    calls = []
    def fake_run(command, **kwargs):
        calls.append([str(x) for x in command])
        if updater.SNAPSHOT_CODE in command:
            raise subprocess.CalledProcessError(1, 'backup')
        return 'old-commit'
    monkeypatch.setattr(updater, 'run', fake_run)
    with pytest.raises(subprocess.CalledProcessError):
        updater.main()
    assert not any('pull' in command or 'upgrade' in command or 'pip' in command for command in calls)
    assert (backend / '.env').read_text(encoding='utf-8') == 'DB_NAME=sample\n'


def test_live_service_is_reported_without_termination(monkeypatch):
    class FakeSocket:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def settimeout(self, timeout):
            pass
        def connect_ex(self, address):
            return 0
    monkeypatch.setattr(updater.socket, 'socket', FakeSocket)
    with pytest.raises(RuntimeError, match='5000'):
        updater.require_stopped_services()


def test_divergent_history_stops_before_any_backup(tmp_path, monkeypatch):
    backend = tmp_path / 'backend'
    backend.mkdir()
    monkeypatch.setattr(sys, 'argv', ['update_project.py'])
    monkeypatch.setattr(updater, 'BACKEND', backend)
    monkeypatch.setattr(updater, 'preflight', lambda: 'npm.cmd')
    def fake_run(command, **kwargs):
        if 'merge-base' in command:
            raise subprocess.CalledProcessError(1, command)
        return 'old-commit'
    monkeypatch.setattr(updater, 'run', fake_run)
    with pytest.raises(RuntimeError, match='不兼容'):
        updater.main()
    assert not (backend / 'backups').exists()
