#!/usr/bin/env python3
"""Network-denied launcher. Never relay child output or exception messages."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


class QuietParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError('invalid_arguments')


def emit(code):
    print(json.dumps({'status': 'blocked', 'code': code, 'cloud_release': False}))


def main():
    try:
        parser = QuietParser(description='Local privacy processor; no raw content is printed.')
        parser.add_argument('--input', required=True)
        parser.add_argument('--policy', required=True)
        parser.add_argument('--out', required=True)
        parser.add_argument('--mode', choices=['deidentify','prepare-import','prepare-summary'], default='deidentify')
        parser.add_argument('--job')
        parser.add_argument('--results')
        parser.add_argument('--import-policy')
        parser.add_argument('--summary-policy')
        args = parser.parse_args()
        if sys.platform not in ('darwin','win32'):
            emit('unsupported_isolation_platform')
            return 2
        worker = Path(__file__).with_name('deidentify.py')
        # This deny applies to this process and its children, including external tools.
        profile = '(version 1) (allow default) (deny network*)'
        env = {k: os.environ[k] for k in ('PATH', 'TMPDIR', 'LANG', 'LC_ALL', 'SystemRoot', 'WINDIR', 'TEMP', 'TMP', 'USERNAME', 'USERPROFILE', 'LOCALAPPDATA') if k in os.environ}
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        command = ['/usr/bin/sandbox-exec', '-p', profile, sys.executable, '-B', str(worker),
                   '--input', args.input, '--policy', args.policy, '--out', args.out, '--mode', args.mode]
        if sys.platform == 'win32':
            # Ordinary Windows hosts are rejected by the worker before reading.
            command = [sys.executable, '-I', '-B', str(worker)] + command[6:]
        if args.mode == 'prepare-import':
            if not all([args.job,args.results,args.import_policy]):
                emit('invalid_arguments');return 2
            command += ['--job',args.job,'--results',args.results,'--import-policy',args.import_policy]
        if args.mode == 'prepare-summary':
            if not all([args.job, args.summary_policy]):
                emit('invalid_arguments');return 2
            command += ['--job',args.job,'--summary-policy',args.summary_policy]
        result = subprocess.run(
            command,
            env=env, capture_output=True, text=True, timeout=120,
        )
        # Only the fixed error-code / status contract reaches the Agent.
        try:
            reply = json.loads(result.stdout)
        except (ValueError, TypeError):
            emit('isolated_worker_failed')
            return 2
        codes = {'local_ready', 'input_rejected', 'policy_invalid', 'schema_mismatch',
                 'active_content', 'ambiguous_identity', 'duplicate_identity',
                 'missing_identity', 'numeric_invalid', 'category_unknown',
                 'small_group', 'integrity_failed', 'output_exists',
                 'resource_limit', 'isolation_failed', 'processing_failed',
                 'job_mismatch','result_mismatch','unauthorized_change',
                 'summary_review_required','summary_small_cell'}
        if (reply.get('code') not in codes or reply.get('cloud_release') is not False
                or reply.get('status') not in ('local_ready', 'blocked')):
            emit('invalid_worker_receipt')
            return 2
        # Rebuild instead of forwarding any unexpected child keys or text.
        safe = {k: reply[k] for k in ('status', 'code', 'cloud_release')}
        if reply['status'] == 'local_ready' and result.returncode == 0:
            safe['network_denied'] = reply.get('network_denied') is True
            safe['integrity_passed'] = reply.get('integrity_passed') is True
            if not (safe['network_denied'] and safe['integrity_passed']):
                emit('invalid_worker_receipt')
                return 2
            print(json.dumps(safe))
            return 0
        emit(reply['code'])
        return 2
    except Exception:
        emit('launcher_failed')
        return 2


if __name__ == '__main__':
    sys.exit(main())
