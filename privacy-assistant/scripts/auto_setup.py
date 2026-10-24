"""Automatic local installation. A successful copy is never a security receipt.

This entry deliberately refuses the disposable Windows session: that session
cannot satisfy the persistent-login requirement. Backend readiness is live,
not inferred from an old state file or from the Agent's statement.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import assistant
from task_channel import get_json, put_json, regular


def probe(agent, app, base):
    """Only synthetic canaries are used. No business-file argument is accepted."""
    if sys.platform == 'win32':
        return {'status': 'requires_runtime_bootstrap', 'code': 'start_local_installer',
                'persistent_session_verified': False}
    if sys.platform != 'darwin':
        return {'status': 'blocked', 'code': 'local_backend_unavailable',
                'persistent_session_verified': False}
    if agent == 'workbuddy':
        return {'status': 'blocked', 'code': 'workbuddy_gui_backend_pending',
                'persistent_session_verified': False}
    if assistant.shutil.which(agent) is None:
        return {'status': 'blocked', 'code': 'agent_runtime_missing',
                'persistent_session_verified': False}
    cmd = [sys.executable, '-B', str(app / 'scripts/python_entry.py'),
           str(app / 'skill/scripts/agent_boundary.py'),
           '--vault', str(base / 'Vault'), '--exchange', str(base / 'Exchange'), '--check']
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    try:
        receipt = json.loads(result.stdout)
    except (ValueError, TypeError):
        receipt = {}
    if result.returncode or receipt.get('status') != 'boundary_probe_passed':
        return {'status': 'blocked', 'code': 'isolation_probe_failed',
                'persistent_session_verified': False}
    # CLI profiles are left where the client owns them. This does not assert
    # that a cloud provider will never expire credentials, or isolate its GUI.
    return {'status': 'cli_boundary_verified', 'code': 'new_cli_only',
            'persistent_session_verified': False,
            'scope': 'new_cli_vault_access_only'}


def run(agent, launch=False, base=None, skill_home=None, install_only=False):
    if agent not in assistant.AGENTS:
        raise ValueError('agent_invalid')
    assistant.check_package()
    if sys.platform not in ('darwin', 'win32'):
        return {'status': 'blocked', 'code': 'local_desktop_required',
                'current_agent_isolated': False}
    base = assistant.initialise(base)
    state = base / 'Settings/automatic-setup.json'
    regular(state)
    # No passwords, tokens, data paths, or raw error messages enter this journal.
    previous = get_json(state) if state.exists() else {}
    installed = assistant.install(agent, base, skill_home)
    app = base / 'App' / assistant.VERSION
    if sys.platform == 'win32':
        if install_only:
            return {'status':'installed','current_agent_isolated':False,'runtime_started':False}
        # Run the installed immutable copy. A ZIP's extraction folder can be moved.
        if launch:
            put_json(base/'Settings/show-window.json',{'show':True})
        command=[str(app/'runtime/pythonw.exe'),'-I','-B',str(app/'scripts/windows_service.py')]
        if not launch:command.append('--background')
        subprocess.Popen(command,
                         stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=0x08000000)
        return {'status':'automatic_installation_started','current_agent_isolated':False,
                'next':'后台准备保护组件；处理任务时再打开受保护的 WorkBuddy'}
    status = probe(agent, app, base)
    receipt = {'version': assistant.VERSION, 'agent': agent,
               'installation': installed['status'],
               'installation_reused': previous.get('version') == assistant.VERSION
                   and previous.get('agent') == agent,
               'configuration_required_from_teacher': False,
               'account_files_modified': False,
               'current_agent_isolated': False,
               'release_qualified': False,
               **status}
    put_json(state, receipt)
    # Do not revive the old disposable workflow on an unsupported platform.
    if receipt['status'] == 'blocked' or not launch:
        return receipt
    launched = assistant.start(agent, show_ui=False, base=base)
    if launched.get('status') != 'isolation_launcher_opened':
        receipt.update(status='blocked', code=launched.get('code', 'launch_failed'))
    else:
        receipt.update(status='local_table_window_started')
    put_json(state, receipt)
    return receipt


def main():
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument('--agent', required=True, choices=assistant.AGENTS)
        mode=parser.add_mutually_exclusive_group()
        mode.add_argument('--install-only', action='store_true')
        mode.add_argument('--open', action='store_true', help='Explicitly open the legacy local file workflow')
        args = parser.parse_args()
        result = run(args.agent, launch=args.open, install_only=args.install_only)
    except Exception:
        result = {'status': 'blocked', 'code': 'automatic_setup_incomplete',
                  'current_agent_isolated': False, 'release_qualified': False}
    print(json.dumps(result, ensure_ascii=False))
    return 2 if result['status'] == 'blocked' else 0


if __name__ == '__main__':
    sys.exit(main())
