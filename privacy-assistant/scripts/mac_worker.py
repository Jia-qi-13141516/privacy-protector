"""Fixed offline operations; all raw-file processing is network denied."""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import table_wizard as w
import task_channel as ch


def execute(mode, task):
    # Confirm the OS boundary before any file read. Core operations install
    # their own audit hook; do not install it twice before their socket probe.
    import socket
    probe = socket.socket()
    try:
        probe.connect(('127.0.0.1', 9))
    except PermissionError:
        pass
    except OSError:
        raise ValueError('isolation_failed') from None
    else:
        raise ValueError('isolation_failed')
    finally:
        probe.close()
    if mode not in ('deidentify', 'export'):
        w.d.isolation_check()
    w.d.safe_path(task)
    private = task / 'private'
    if mode.startswith('document_'):
        import document_engine as doc
        if mode == 'document_prepare':
            request=ch.get_json(private/'input.json',1024*1024)
            source=Path(request['source'])
            doc.prepare(task,ch.read(source,doc.MAX_INPUT),source.suffix.lower(),request['terms'])
        elif mode == 'document_approve':
            request=ch.get_json(private/'approval.json',2*1024*1024)
            doc.approve(task,request['text'],request['sha256'])
        elif mode == 'document_preview':
            request=ch.get_json(private/'result-options.json')
            doc.preview(task,ch.read(private/'returned.txt',1024*1024).decode('utf-8-sig'),request['restore'])
        elif mode == 'document_export':
            request=ch.get_json(private/'export-options.json')
            data=doc.export(task,request['sha256'],request['extension'])
            ch.write(private/('final'+request['extension']),data,True)
        else:raise ValueError('mode_invalid')
    elif mode == 'ingest':
        source = Path(ch.get_json(private / 'input.json')['source'])
        w.d.require(source.suffix.lower() in ('.csv', '.xlsx'), 'input_rejected')
        ch.write(private / ('original' + source.suffix.lower()), ch.read(source), exclusive=True)
        w.inspect(task)
    elif mode == 'configure':
        w.configure(task)
    elif mode == 'deidentify':
        w.d.process(w.source_path(task), private / 'policy.json', task / 'job')
        release = private / 'release'
        release.mkdir(mode=0o700)
        ch.write(release / 'data.csv', ch.read(task / 'job/private/students.csv'), exclusive=True)
        ch.put_json(release / 'columns.json', w.column_guide(task), exclusive=True)
    elif mode == 'preview':
        w.preview(task)
    elif mode == 'review':
        rows = ch.get_json(private / 'preview.json', limit=ch.MAX_BYTES)
        lines = ['实名结果核对表', '共 ' + str(len(rows)) + ' 条；请核对身份、原值和新增结果。', '']
        for number, row in enumerate(rows, 1):
            lines.append(str(number) + '. ' + '；'.join(str(k) + '：' + str(v) for k, v in row.items()))
        ch.write(private / 'review.txt', '\n'.join(lines).encode())
    elif mode == 'export':
        w.d.prepare_import(w.source_path(task), private / 'policy.json', task / 'export', task / 'job',
                           private / 'reviewed.csv', private / 'import-policy.json')
    else:
        raise ValueError('mode_invalid')


def main():
    try:
        os.umask(0o077)
        execute(sys.argv[1], Path(sys.argv[2]))
        print('{"status":"local_ready"}')
        return 0
    except Exception as exc:
        from document_engine import ERROR_MESSAGES
        reply={'status':'blocked'}
        if str(exc) in ERROR_MESSAGES:reply['code']=str(exc)
        print(json.dumps(reply))
        return 2


if __name__ == '__main__':
    sys.exit(main())
