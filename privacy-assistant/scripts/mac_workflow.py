"""Local macOS table workflow. Never returns local file data to its launcher."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import task_channel as ch

OFFLINE = '(version 1)(allow default)(deny network*)'


def worker(mode, task):
    command = ['/usr/bin/sandbox-exec', '-p', OFFLINE, sys.executable, '-B',
               str(ROOT / 'scripts/mac_worker.py'), mode, str(task)]
    result = subprocess.run(command, capture_output=True, timeout=120,
                            env=clean_env(), close_fds=True)
    try:
        reply = json.loads(result.stdout)
    except (ValueError, TypeError):
        raise ValueError('local_processing_failed') from None
    if result.returncode or reply != {'status': 'local_ready'}:
        raise ValueError('local_processing_failed')


def clean_env():
    return {k: os.environ[k] for k in ('PATH', 'HOME', 'TMPDIR', 'LANG', 'LC_ALL', 'TERM')
            if k in os.environ}


def dialog(script, *values):
    # Values are argv, never interpolated AppleScript source or forwarded to AI.
    result = subprocess.run(['/usr/bin/osascript', '-e', script, *values],
                            capture_output=True, text=True, timeout=3600,
                            env=clean_env(), close_fds=True)
    if result.returncode:
        raise ValueError('cancelled')
    return result.stdout.rstrip('\n')


def choose(prompt, options):
    answer = dialog('''on run argv
set picked to choose from list (items 2 thru -1 of argv) with title "隐私保护Skill" with prompt (item 1 of argv) OK button name "继续" cancel button name "取消"
if picked is false then error number -128
return item 1 of picked
end run''', prompt, *options)
    if answer not in options:
        raise ValueError('cancelled')
    return answer


def pick_agent(requested):
    if requested in ('codex', 'claude') and shutil.which(requested):
        return requested
    available = [a for a in ('codex', 'claude') if shutil.which(a)]
    if not available:
        raise ValueError('mac_cli_required')
    if len(available) == 1:
        return available[0]
    return choose('Mac 版在新的命令行窗口处理代号数据。请选择已登录的客户端。', available)


def launch_agent(agent, task, exchange, base):
    import agent_boundary
    # Local metadata stays inside Vault. Deny both the selected original and
    # private copies; prevent the child from modifying worker code/settings.
    source = ch.get_json(task / 'private/input.json')['source']
    protected = [Path(source)]
    profile = agent_boundary.profile(base / 'Vault', protected=protected,
                                     readonly=[ROOT, base / 'Settings', base / 'App'])
    profile_path = task / 'private/agent.sb'
    ch.write(profile_path, profile.encode())
    prompt = ('在当前目录处理 data.csv。先阅读 AGENTS.md 和 columns.json，向用户询问本次任务。'
              '仅处理代号数据；结果保存为 result.csv，完成后请用户回到隐私保护Skill窗口确认。')
    args = ['/usr/bin/sandbox-exec', '-f', str(profile_path), shutil.which(agent)]
    if agent == 'codex':
        args += ['--cd', str(exchange), prompt]
    else:
        args += [prompt]
    import shlex
    command = 'cd ' + shlex.quote(str(exchange)) + ' && ' + shlex.join(args)
    dialog('''on run argv
tell application "Terminal"
activate
do script (item 1 of argv)
end tell
return "opened"
end run''', command)


def export_confirmed(task, destination):
    """Called only by local UI after approval; no Agent request can approve."""
    ch.regular(destination)
    if destination.exists():
        raise ValueError('destination_exists')
    data = ch.read(task / 'export/private/ready-to-import.xlsx')
    ch.write(destination, data, exclusive=True)


def run(agent, base):
    import assistant
    assistant.check_package()
    agent = pick_agent(agent)
    # Probe before asking for a real file. No model call or business data here.
    probe = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/python_entry.py'),
                            str(ROOT / 'skill/scripts/agent_boundary.py'),
                            '--vault', str(base / 'Vault'), '--exchange', str(base / 'Exchange'),
                            '--check'], capture_output=True, timeout=30)
    if probe.returncode:
        raise ValueError('boundary_failed')
    identifier = uuid.uuid4().hex
    task = base / 'Vault' / identifier
    private = task / 'private'
    private.mkdir(parents=True, mode=0o700)
    selected = dialog('''set picked to choose file with prompt "选择需要脱敏的 XLSX 或 CSV 原表；原表不进入聊天。"
return POSIX path of picked''')
    source = Path(selected)
    ch.regular(source)
    if source.suffix.lower() not in ('.csv', '.xlsx'):
        raise ValueError('input_rejected')
    ch.put_json(private / 'input.json', {'source': str(source)})
    worker('ingest', task)
    fields = ch.get_json(private / 'schema.json')['fields']
    headers = [f['header'] for f in fields]
    identity = choose('哪一列是每条记录唯一且不重复的学号或编号？', headers)
    choices = []
    for header in headers:
        if header == identity:
            choices.append('id')
        else:
            label = choose('字段「' + header + '」如何处理？姓名、联系方式和自由文本请选择不提供。',
                           ['不提供给 AI', '允许分析：数值', '允许分析：分类（替换成代号）'])
            choices.append({'不提供给 AI': 'drop', '允许分析：数值': 'number',
                            '允许分析：分类（替换成代号）': 'category'}[label])
    ch.put_json(private / 'choices.json', choices)
    worker('configure', task)
    worker('deidentify', task)
    exchange = base / 'Exchange' / identifier
    exchange.mkdir(mode=0o700)
    for name in ('data.csv', 'columns.json'):
        ch.write(exchange / name, ch.read(private / 'release' / name), exclusive=True)
    ch.write(exchange / 'AGENTS.md', b'''# Privacy table task\n
Only data.csv and columns.json are input. Ask for the task before analyzing.\n
Keep all original column names and values unchanged; you may reorder/filter rows.\n
Save result.csv as UTF-8 CSV. Optional new columns: follow_up (yes/no), priority (0..3).\n
Never add free text, other columns, formulas, duplicate or unknown identities.\n
Do not read files outside this task directory, request identities, or open GUI/IPC bridges.\n
After saving, tell the user to return to the local Skill window for review.\n''')
    launch_agent(agent, task, exchange, base)
    choose('在新开的 Agent 窗口说明任务。等它保存 result.csv 后，回到这里继续。', ['结果已生成，开始本地核验'])
    ch.write(private / 'returned.csv', ch.read(exchange / 'result.csv'), exclusive=True)
    worker('preview', task)
    preview = ch.get_json(private / 'preview.json', limit=ch.MAX_BYTES)
    # The full table is rendered locally, not transmitted to the child Agent.
    worker('review', task)
    subprocess.run(['/usr/bin/open', '-a', 'TextEdit', str(private / 'review.txt')],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    choose('已打开完整实名核对表，共 ' + str(len(preview)) + ' 条。请逐项核对，确认后生成 Excel。',
           ['已核对，生成导入文件'])
    worker('export', task)
    # The online child remains unable to read the final file. Never export to
    # an arbitrary user path that falls outside its existing sandbox boundary.
    destination = base / 'Vault' / 'Exports' / ('待导入结果-' + identifier[:8] + '.xlsx')
    export_confirmed(task, destination)
    subprocess.run(['/usr/bin/open', '-R', str(destination)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    assistant.notify('导入文件已生成，访达已显示文件位置。请自行导入业务系统；不要拖进聊天。')


def main():
    try:
        import assistant
        if sys.platform != 'darwin':
            raise ValueError('mac_required')
        os.umask(0o077)
        run(sys.argv[1] if len(sys.argv) > 1 else 'codex', assistant.initialise())
        return 0
    except Exception as exc:
        import assistant
        if str(exc) != 'cancelled':
            assistant.notify('本次处理未完成，未向 AI 提供新的原表。请检查文件、字段选择或客户端是否可用，再重试。')
        return 2


if __name__ == '__main__':
    sys.exit(main())
