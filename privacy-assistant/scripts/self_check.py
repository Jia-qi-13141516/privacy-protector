"""A real, offline, synthetic first-run check. No fixture answers are passed to the model."""
import hashlib
import io
import json
import time
from pathlib import Path
import task_channel as ch
import performance

MAX_SECONDS = 180
WARN_SECONDS = 60
CHECKS = ('table_values', 'table_sort', 'table_new_columns', 'zero_match',
          'document_selection', 'document_exact_text', 'originals_unchanged', 'os_isolation', 'real_inference')


def fingerprint(root):
    spec = ch.get_json(root/'backend/local-model.json')
    manifest = ch.read(root/'release.json', 1024*1024)
    return hashlib.sha256(manifest + json.dumps(performance.PROFILE, sort_keys=True).encode() + spec['model']['sha256'].encode()).hexdigest()


def cache_valid(receipt, key):
    return (isinstance(receipt, dict) and receipt.get('phase') == 'ready'
            and receipt.get('fingerprint') == key and receipt.get('profile') == 'compact'
            and receipt.get('local_model_calls', 0) >= 2
            and type(receipt.get('peak_rss_bytes')) is int and 0 < receipt['peak_rss_bytes'] <= performance.PROFILE['max_rss_bytes']
            and type(receipt.get('elapsed_seconds')) in (int, float) and 0 < receipt['elapsed_seconds'] <= MAX_SECONDS
            and receipt.get('checks') == dict.fromkeys(CHECKS, True))


def run_offline(task, config, verify_boundary=None):
    from background_worker import require_offline, install_execution_guard
    (verify_boundary or require_offline)()  # Boundary is enforced before fixture creation.
    import document_engine as doc
    import table_wizard  # Load the bundled pure-Python spreadsheet dependency path.
    import openpyxl
    import background_engine as engine
    import local_runtime
    start = time.monotonic()
    rows = [['编号', '姓名', '待补材料数', '已核对份数'],
            ['T001', '虚构甲', 2, 4], ['T002', '虚构乙', 3, 2], ['T003', '虚构丙', 0, 1],
            ['T004', '虚构丁', 5, 1], ['T005', '虚构戊', 4, 7], ['T006', '虚构己', 1, 0],
            ['T007', '虚构庚', 3, 6], ['T008', '虚构辛', 6, 3]]
    book = openpyxl.Workbook()
    for row in rows: book.active.append(row)
    stream = io.BytesIO(); book.save(stream); book.close()
    source = task/'synthetic.xlsx'; ch.write(source, stream.getvalue(), True)
    paragraphs = [
        '顾衡是宋岚的项目联络人，宋岚负责社区读书活动的物料。',
        '顾衡尚未将报名核对表交给宋岚，需要在下周一之前完成交接。',
        '陶芷负责场地安排，仍需确认周三下午的教室，再把结果告知顾衡。',
        '宋岚已经核对完本周物料数量并把清单发给陶芷，该事项已结束，无需再次跟进。',
        '韩舟负责海报，海报已发布并归档，本周不再安排相关工作。',
        '顾衡收到陶芷的场地结果后，还需要通知宋岚准备物料。']
    document = task/'synthetic.docx'; ch.write(document, doc.make_docx('\n\n'.join(paragraphs)), True)
    original_hashes = {p: hashlib.sha256(ch.read(p)).hexdigest() for p in (source, document)}
    table_dir = task/'table'; zero_dir = task/'zero'; doc_dir = task/'document'
    for folder in (table_dir, zero_dir, doc_dir): folder.mkdir(mode=0o700)
    model = local_runtime.LocalModel(config, doc_dir)
    install_execution_guard(str(model.binary))
    engine.table_job(source, table_dir, '筛选待补材料数不低于3，按待补材料数从大到小排列，新增是否跟进为需跟进、优先级统一为1，统计记录数。', model)
    engine.table_job(source, zero_dir, '筛选待补材料数大于99，统计记录数。', model)
    result = engine.document_job(document, doc_dir, '整理未完成待办，保留负责人、交接对象和期限，排除已结束事项与纯分工。', model)
    def read_table(path):
        workbook = openpyxl.load_workbook(io.BytesIO(ch.read(path)), data_only=False)
        values = list(workbook['处理结果'].values); stats = dict(list(workbook['统计'].values)[1:]); workbook.close()
        return values, stats
    actual, stats = read_table(table_dir/'result.xlsx')
    selected = sorted([r for r in rows[1:] if r[2] >= 3], key=lambda r: r[2], reverse=True)
    expected = [tuple(rows[0] + ['是否跟进', '优先级'])] + [tuple(r + ['需跟进', 1]) for r in selected]
    empty, empty_stats = read_table(zero_dir/'result.xlsx')
    indices = ch.get_json(doc_dir/'source-index.json')['selected_ids']
    expected_text = '待办事项摘录\n\n' + '\n\n'.join(str(i)+'. '+paragraphs[j-1] for i,j in enumerate((2,3,6),1))
    checks = {
        'table_values': actual == expected and stats.get('符合条件记录数') == 5 and stats.get('待补材料数：合计') == 21,
        'table_sort': [r[2] for r in actual[1:]] == [6,5,4,3,3],
        'table_new_columns': all(r[-2:] == ('需跟进', 1) for r in actual[1:]),
        'zero_match': empty == [tuple(rows[0])] and empty_stats.get('符合条件记录数') == 0,
        'document_selection': indices == [2,3,6],
        'document_exact_text': doc.docx_text(ch.read(doc_dir/'result.docx')) == expected_text,
        'originals_unchanged': all(hashlib.sha256(ch.read(p)).hexdigest() == h for p,h in original_hashes.items()),
        'os_isolation': True,
        'real_inference': result['local_model_calls'] >= 2 and len(list(doc_dir.glob('response-*.json'))) >= 2,
    }
    elapsed = round(time.monotonic()-start, 3)
    if not all(checks.values()): raise ValueError('self_test_result_mismatch')
    if elapsed > MAX_SECONDS: raise ValueError('self_test_slow')
    receipt = {'checks': checks, 'elapsed_seconds': elapsed, 'profile': 'compact',
               'peak_rss_bytes': max(m['peak_rss_bytes'] for m in model.metrics),
               'local_model_calls': result['local_model_calls'], 'slow': elapsed > WARN_SECONDS,
               'cloud_data_sent': False, 'network': 'os_blocked', 'human_confirmation': False}
    ch.put_json(task/'self-test.json', receipt, True)
    return receipt
