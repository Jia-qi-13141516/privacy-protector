"""Run a synthetic macOS roundtrip, then render a README walkthrough (not UI footage).

Requires macOS sandbox-exec, package table dependencies, and Pillow.
Usage: python3 tools/build_readme_demo.py
"""
import csv
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'privacy-assistant/scripts'))
import mac_workflow as workflow
import task_channel as ch
import openpyxl
from PIL import Image, ImageDraw, ImageFont

OUT = ROOT / 'docs/assets'


def verify_case():
    with tempfile.TemporaryDirectory(prefix='privacy-readme-synthetic-') as tmp:
        base = Path(tmp)
        task = base / 'Vault/task'
        private = task / 'private'
        private.mkdir(parents=True)
        source = base / 'original.csv'
        rows = [[f'{i:06}', f'虚构学生{i}', 20 + i % 17, '虚构备注（不提供）'] for i in range(60)]
        with source.open('w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['学号', '姓名', '分数', '备注'])
            writer.writerows(rows)
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        ch.put_json(private / 'input.json', {'source': str(source)})
        workflow.worker('ingest', task)
        ch.put_json(private / 'choices.json', ['id', 'drop', 'number', 'drop'])
        workflow.worker('configure', task)
        workflow.worker('deidentify', task)
        with (private / 'release/data.csv').open() as f:
            reader = csv.DictReader(f)
            fields = reader.fieldnames
            safe = list(reader)
        for file in (private / 'release').iterdir():
            content = file.read_text()
            assert '虚构学生' not in content and '虚构备注' not in content
            assert str(source) not in content
        expected = [r for r in rows if r[2] >= 30]
        selected = [dict(r, follow_up='yes', priority='2') for r in safe if int(r['measure_3']) >= 30]
        # Deterministic rule simulates an Agent output, without contacting a model.
        with (private / 'returned.csv').open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fields + ['follow_up', 'priority'])
            writer.writeheader()
            writer.writerows(selected)
        workflow.worker('preview', task)
        workflow.worker('review', task)
        workflow.worker('export', task)
        destination = base / 'Vault/Exports/result.xlsx'
        workflow.export_confirmed(task, destination)
        book = openpyxl.load_workbook(destination)
        actual = list(book.active.values)[1:]
        book.close()
        assert actual == [(r[0], r[1], str(r[2]), '需跟进', 2) for r in expected]
        assert len(selected) == 21
        assert sum(int(r['measure_3']) for r in safe) == sum(r[2] for r in rows)
        assert before == hashlib.sha256(source.read_bytes()).hexdigest()
        return {
            'input_records': len(rows), 'selected_records': len(selected),
            'raw_score_sum': sum(r[2] for r in rows),
            'deidentified_score_sum': sum(int(r['measure_3']) for r in safe),
            'identity_and_result_match': True, 'original_unchanged': True,
            'model_called': False, 'method': 'macOS offline worker; deterministic rule simulates Agent output',
            'rule': 'score >= 30; follow_up = yes; priority = 2',
            'raw_sample': expected[:3],
            'safe_sample': [{k: r[k] for k in fields} for r in selected[:3]],
            'result_sample': [list(r) for r in actual[:3]],
        }


W, H = 1200, 720
BG = '#F6F8FA'
NAVY = '#183C4D'
MUTED = '#5C7381'
TEAL = '#087F8C'
LINE = '#D8E3E8'
WHITE = '#FFFFFF'
FONT = '/System/Library/Fonts/Hiragino Sans GB.ttc'


def font(size):
    return ImageFont.truetype(FONT, size)


def text(d, xy, value, size=24, color=NAVY):
    d.text(xy, str(value), font=font(size), fill=color)


def base(step, title, subtitle):
    im = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(im)
    text(d, (50, 28), '隐私保护Skill', 22, TEAL)
    text(d, (870, 30), '虚构案例 · 流程演示', 20, MUTED)
    text(d, (50, 84), title, 39)
    text(d, (50, 146), subtitle, 22, MUTED)
    labels = ['本地选表', '离线脱敏', '处理代号', '核验回填', '确认导出']
    for i, label in enumerate(labels):
        x = 50 + i * 230
        active = step == i or step == 5
        d.rounded_rectangle((x, 204, x + 214, 252), radius=12,
                            fill=TEAL if active else '#E7EEF2')
        text(d, (x + 24, 214), f'{i+1}  {label}', 21, WHITE if active else MUTED)
    d.line((50, 656, 1150, 656), fill=LINE, width=1)
    text(d, (50, 674), '本地流程实测 · Agent 结果由固定规则模拟 · 非产品界面录屏', 19, MUTED)
    text(d, (1080, 674), f'{step+1} / 6', 19, MUTED)
    return im, d


def table(d, headers, rows, widths, x=70, y=326):
    total = sum(widths)
    d.rounded_rectangle((x, y, x + total, y + 54 + len(rows)*58), radius=10, fill=WHITE, outline=LINE, width=2)
    xx = x
    for head, width in zip(headers, widths):
        text(d, (xx + 16, y + 14), head, 21, TEAL)
        xx += width
    d.line((x, y+54, x+total, y+54), fill=LINE, width=2)
    for i, row in enumerate(rows):
        xx = x
        for value, width in zip(row, widths):
            text(d, (xx + 16, y + 69 + i*58), value, 23)
            xx += width


def render(report):
    frames = []
    raw = report['raw_sample']
    safe = report['safe_sample']
    # Shortened for legibility; the worker used complete random identifiers.
    codes = [r['person'][:10] + '…' for r in safe]
    im, d = base(0, '想让 AI 帮忙，又不想交出实名原表', '示例任务：从 60 条虚构记录中筛选分数 ≥ 30 的记录，并新增跟进标记。')
    text(d, (70, 280), '仅在本地选择原表；以下为其中 3 条', 22, TEAL)
    table(d, ['学号', '姓名', '分数', '备注'], raw, [190, 240, 140, 490])
    text(d, (70, 592), '姓名、学号、备注留在本地，不拖入聊天。', 25)
    frames.append(im)

    im, d = base(1, '先脱敏，再让模型接触数据', '只允许分数进入分析；学号替换为随机任务代号，姓名与备注不提供。')
    text(d, (70, 280), '允许提供给 Agent 的表格', 22, TEAL)
    table(d, ['任务代号（略写）', '分数'], [[c, r['measure_3']] for c, r in zip(codes, safe)], [650, 410])
    text(d, (70, 592), '身份对应表留在本地，供后续回填。', 25)
    frames.append(im)

    im, d = base(2, '用代号也能筛选、增加结果列', '按规则筛出 21 条，标记“需跟进”，并将优先级设为 2。')
    text(d, (70, 280), '本演示以固定规则模拟 Agent 输出；不调用云端模型', 22, TEAL)
    table(d, ['任务代号（略写）', '分数', '是否跟进', '优先级'],
          [[c, r['measure_3'], 'yes', '2'] for c, r in zip(codes, safe)], [440, 160, 250, 210])
    text(d, (70, 592), '云端模型仍可能接收获准提供的代号数据。', 25)
    frames.append(im)

    im, d = base(3, '结果回来后，先检查，再恢复身份', '检查代号、原值、重复记录与新增列规则；实名核对表只在本地打开。')
    text(d, (70, 280), '本地身份回填后的结果', 22, TEAL)
    table(d, ['学号', '姓名', '分数', '是否跟进', '优先级'], report['result_sample'], [180, 260, 140, 270, 210])
    text(d, (70, 592), '身份与结果逐条匹配；原表保持不变。', 25)
    frames.append(im)

    im, d = base(4, '确认之后，得到可用的 Excel', '本地核对 21 条结果，再生成实名文件；业务系统的导入由本人完成。')
    for i, (number, caption) in enumerate([('60 条', '原始虚构记录'), ('21 条', '符合筛选规则'), ('21 / 21', '身份与结果一致')]):
        x = 50 + i*375
        d.rounded_rectangle((x, 308, x+350, 514), radius=18, fill=WHITE, outline=LINE, width=2)
        text(d, (x+34, 345), number, 46, TEAL)
        text(d, (x+34, 432), caption, 24)
    text(d, (70, 575), '不用在 AI 输出后手工逐条找回姓名。', 28)
    frames.append(im)

    im, d = base(5, '让隐私保护成为表格工作的一部分', '保留有用的数据，减少身份暴露；在本地完成核验与交付。')
    for y, title, subtitle in [(304, '数值一致', f"脱敏前后分数总和均为 {report['raw_score_sum']}"),
                               (404, '回填一致', '21 条导出记录的身份、分数与新增列符合预期'),
                               (504, '边界清楚', '验证本地处理链路，不代表 AI 判断必然正确')]:
        d.rounded_rectangle((50, y, 1150, y+82), radius=14, fill=WHITE, outline=LINE)
        text(d, (76, y+22), title, 28, TEAL)
        text(d, (270, y+26), subtitle, 23)
    frames.append(im)
    # A fixed result card is available for readers who prefer no animation.
    frames[-1].save(OUT / 'demo-summary.png', optimize=True)
    frames[0].save(OUT / 'privacy-workflow.gif', save_all=True, append_images=frames[1:],
                   duration=[4500, 4500, 5000, 5000, 4500, 6000], loop=0, optimize=True)


if __name__ == '__main__':
    if sys.platform != 'darwin':
        raise SystemExit('Reproduction requires macOS sandbox-exec.')
    OUT.mkdir(parents=True, exist_ok=True)
    report = verify_case()
    (OUT / 'demo-verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    render(report)
    print(json.dumps({k: v for k, v in report.items() if not k.endswith('_sample')}, ensure_ascii=False, indent=2))
