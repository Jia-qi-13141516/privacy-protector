"""Offline document operations. No model, network, shell, or user-supplied code.

Only a locally reviewed text copy can cross the boundary. Replacement is
pseudonymisation, not a guarantee that the remaining narrative is anonymous.
"""
import hashlib
import io
import json
import re
import secrets
import unicodedata
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

import task_channel as ch

ERROR_MESSAGES = {
    'document_classified': '检测到密级标记，已停止处理。标密材料不能进入联网 Agent 流程。',
    'document_scan_or_graphics': '此 PDF 含图片、图形或无法提取的页面。当前只支持纯文字 PDF，请在本地准备可用的文字材料。',
    'document_encrypted': '当前不处理加密 PDF；没有向 Agent 提供正文。',
    'document_active_content': '文档含表单、外链或活动内容，当前不能处理。请在本地另存为干净正文后重试。',
    'document_external_link': '文档含外部链接，当前不能处理。请在本地另存为干净正文后重试。',
    'document_unsupported_content': '文档含图片、修订、批注、脚注或嵌入内容，当前不能完整处理。请在本地准备干净正文后重试。',
    'document_identifier_remaining': '预览或结果中仍有可识别信息。请在本地检查脱敏内容，不要直接上传原文。',
    'document_token_invalid': '结果中的代号被改写或损坏，未生成导出文件。请让 Agent 保留原代号后重新处理。',
    'document_token_unknown': '结果出现未知代号，未恢复身份或导出。',
    'document_token_not_released': '结果引用了未获准提供的人物代号，已拒绝回填。',
    'document_size': '文件或正文超过当前大小限制，已停止处理。',
    'document_format': '格式不在支持范围。请使用 UTF-8 TXT/MD、基础 DOCX 或纯文字 PDF。',
}

MAX_INPUT = 5 * 1024 * 1024
MAX_TEXT = 200_000
FORMATS = ('.txt', '.md', '.docx', '.pdf')
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
TOKEN = re.compile(r'⟦PVT_[a-f0-9]{16}_[0-9]{4}⟧')
# Deliberately conservative direct-identifier rules; local review is mandatory.
PATTERNS = [
    re.compile(r'(?i)[\w.+-]+@[\w.-]+\.[a-z]{2,}'),
    re.compile(r'(?i)(?:https?://|www\.)[^\s<>，。；]+'),
    re.compile(r'(?<!\d)(?:\+?86[- ]?)?1[3-9]\d(?:[- ]?\d){8}(?!\d)'),
    re.compile(r'(?<!\d)\d{17}[\dXx](?!\w)'),
    re.compile(r'(?<!\d)(?:\d[- ]?){7,}(?!\d)'),
    re.compile(r'(?<!\d)(?:19|20)\d{2}[年./-]\d{1,2}(?:[月./-]\d{1,2}日?)?'),
    re.compile(r'(?<=姓名[:：])[ \t]*[^\s,，。；;、]{2,12}'),
    re.compile(r'(?:姓名|联系人|谈话对象|学生|老师|住址|地址|学校|学院|班级|宿舍|学号|工号|身份证号|微信号|QQ号)[ \t]*[:：][ \t]*([^\n,，。；;]{1,80})'),
]
CLASSIFIED = re.compile(r'(?:^|\n)\s*(?:[【\[]\s*)?(?:绝\s*密|机\s*密|秘\s*密)(?:[】\]★☆\s]|$)|(?:绝\s*密|机\s*密|秘\s*密)\s*[★☆]|国家\s*秘密')


def require(value, code):
    if not value:
        raise ValueError(code)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def normal(text):
    require(isinstance(text, str) and len(text) <= MAX_TEXT, 'document_size')
    # Full-width and invisible characters must not hide a direct identifier.
    text = ''.join(c if c in '，：；！？。、“”‘’（）' else unicodedata.normalize('NFKC', c) for c in text)
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    require(not any(unicodedata.category(c) == 'Cc' and c not in '\n\t' for c in text), 'document_control_character')
    text = ''.join(c for c in text if unicodedata.category(c) != 'Cf')
    require(bool(text.strip()), 'document_empty')
    return text


def xml(data):
    require(len(data) <= 10 * 1024 * 1024 and not re.search(br'<!\s*(DOCTYPE|ENTITY)', data, re.I), 'document_active_content')
    return ET.fromstring(data)


def docx_text(data):
    with ZipFile(io.BytesIO(data)) as z:
        items = z.infolist(); names = [i.filename for i in items]
        require(len(items) <= 1000 and len(names) == len(set(names)), 'document_archive')
        require(sum(i.file_size for i in items) <= 40 * 1024 * 1024, 'document_size')
        require(all(not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts and '\\' not in n for n in names), 'document_archive')
        forbidden = ('vbaproject', 'embeddings/', 'activex/', 'word/media/', 'comments', 'footnotes', 'endnotes')
        require(not any(any(f in n.lower() for f in forbidden) for n in names), 'document_unsupported_content')
        for name in names:
            if name.endswith('.rels'):
                relations = xml(z.read(name))
                require(not any(x.attrib.get('TargetMode') == 'External' for x in relations), 'document_external_link')
        # A classification marking may be in a header/footer or properties.
        # Inspect it locally before discarding that content from the release.
        for name in names:
            if name.endswith('.xml'):
                marking='\n'.join(t for t in xml(z.read(name)).itertext() if t.strip())
                require(not CLASSIFIED.search(marking), 'document_classified')
        require('word/document.xml' in names, 'document_format')
        body = xml(z.read('word/document.xml'))
        forbidden_tags = {'ins','del','moveFrom','moveTo','fldSimple','instrText','altChunk','object','drawing','pict','vanish','webHidden','sdt'}
        require(not any(x.tag.rsplit('}',1)[-1] in forbidden_tags for x in body.iter()), 'document_unsupported_content')
        paragraphs = []
        for p in body.iter(W+'p'):
            words = []
            for e in p.iter():
                if e.tag == W+'t': words.append(e.text or '')
                elif e.tag == W+'tab': words.append('\t')
                elif e.tag in (W+'br', W+'cr'): words.append('\n')
            paragraphs.append(''.join(words))
        # Headers, footers, properties and author metadata are never copied out.
        return '\n'.join(paragraphs)


def pdf_text(data):
    from pypdf import PdfReader
    r = PdfReader(io.BytesIO(data), strict=True)
    require(not r.is_encrypted, 'document_encrypted')
    require(0 < len(r.pages) <= 100, 'document_size')
    root = r.trailer['/Root']
    require(not any(k in root for k in ('/OpenAction','/AA','/AcroForm','/Names','/Collection')), 'document_active_content')
    result = []
    for page in r.pages:
        require(not any(k in page for k in ('/AA','/Annots')), 'document_active_content')
        resources = page.get('/Resources', {})
        if hasattr(resources, 'get_object'): resources = resources.get_object()
        # This version rejects image/form XObjects rather than claiming OCR coverage.
        require(not resources.get('/XObject'), 'document_scan_or_graphics')
        contents = page.get_contents()
        if contents is not None:
            require(len(contents.get_data()) <= 5*1024*1024, 'document_size')
            require(not any(op in (b'INLINE IMAGE',b'BI',b'ID',b'EI') for _,op in contents.operations), 'document_scan_or_graphics')
        text = page.extract_text() or ''
        require(bool(text.strip()), 'document_scan_or_graphics')
        result.append(text)
        require(sum(map(len, result)) <= MAX_TEXT, 'document_size')
    return '\n\n'.join(result)


def extract(data, extension):
    require(extension in FORMATS and len(data) <= MAX_INPUT, 'document_format')
    if extension in ('.txt', '.md'):
        text = data.decode('utf-8-sig', errors='strict')
    elif extension == '.docx': text = docx_text(data)
    else: text = pdf_text(data)
    text = normal(text)
    require(not CLASSIFIED.search(text), 'document_classified')
    require('PVT_' not in text and '⟦' not in text and '⟧' not in text, 'document_reserved_token')
    return text


def identifiers(text):
    found = set()
    for pattern in PATTERNS:
        for m in pattern.finditer(text):
            value = (m.group(1) if m.lastindex else m.group()).strip()
            if value: found.add(value)
    return found


def redact(text, terms):
    require(isinstance(terms, list) and len(terms) <= 500, 'document_terms')
    chosen = set(identifiers(text))
    for term in terms:
        require(isinstance(term, str), 'document_terms')
        term = normal(term).strip()
        require(2 <= len(term) <= 200 and '\n' not in term, 'document_terms')
        if term in text: chosen.add(term)
    # Longest first prevents shorter names from hiding a longer sensitive phrase.
    values = sorted(chosen, key=lambda s: (-len(s), s))
    nonce = secrets.token_hex(8)
    mapping = {}; assigned = {}
    def replace(match):
        value=match.group()
        if value not in assigned:
            code=f'⟦PVT_{nonce}_{len(mapping)+1:04}⟧'
            assigned[value]=code;mapping[code]=value
        return assigned[value]
    # Single pass on original text: a sensitive term must never re-enter tokens.
    safe=re.sub('|'.join(re.escape(v) for v in values),replace,text) if values else text
    return safe, mapping


def valid_text(text, mapping):
    text = normal(text)
    found = TOKEN.findall(text)
    residue = TOKEN.sub('', text)
    require('PVT_' not in residue and '⟦' not in residue and '⟧' not in residue, 'document_token_invalid')
    require(set(found) <= set(mapping), 'document_token_unknown')
    require(not identifiers(residue), 'document_identifier_remaining')
    require(not CLASSIFIED.search(residue), 'document_classified')
    # A short name can be part of ordinary words; conservative rejection is safer.
    require(not any(v in residue for v in mapping.values()), 'document_identifier_remaining')
    return text


def private(task):
    ch.regular(task)
    return task / 'private'


def state(task):
    p = private(task); s = ch.get_json(p/'document-state.json', MAX_INPUT)
    require(sha(ch.read(p/'original.bin', MAX_INPUT)) == s['source_sha256'], 'document_source_changed')
    return p, s


def prepare(task, data, extension, terms):
    p = private(task); p.mkdir(parents=True, exist_ok=True, mode=0o700)
    require(not (p/'document-state.json').exists(), 'document_existing_task')
    text = extract(data, extension); safe, mapping = redact(text, terms)
    ch.write(p/'original.bin', data, True)
    ch.write(p/'draft.txt', safe.encode(), True)
    ch.put_json(p/'document-state.json', {'version':1,'source_sha256':sha(data),
                 'mapping':mapping,'phase':'needs_local_review'}, True)
    # Only a local UI may read this draft. Nothing is released here.
    return {'draft':safe,'replacements':len(mapping)}


def approve(task, reviewed, expected_sha256):
    p, s = state(task)
    require(s['phase']=='needs_local_review', 'document_phase')
    require(sha(reviewed.encode())==expected_sha256, 'document_review_changed')
    checked = valid_text(reviewed, s['mapping'])
    # It is legitimate for the person to remove whole identifying paragraphs.
    ch.write(p/'approved.txt', checked.encode(), True)
    s.update(phase='released', approved_sha256=sha(checked.encode()))
    ch.put_json(p/'document-state.json', s)
    return checked


def preview(task, returned, restore):
    p, s = state(task)
    require(s['phase']=='released' and type(restore) is bool, 'document_phase')
    require(sha(ch.read(p/'approved.txt'))==s['approved_sha256'], 'document_review_changed')
    checked = valid_text(returned, s['mapping'])
    # A person may remove an entire identity during local review. Never let a
    # guessed token revive an identity that was not in the approved release.
    allowed=set(TOKEN.findall(ch.read(p/'approved.txt').decode()))
    require(set(TOKEN.findall(checked)) <= allowed, 'document_token_not_released')
    require(len(checked) <= min(MAX_TEXT, len(ch.read(p/'approved.txt').decode())*4+5000), 'document_size')
    if restore:
        checked = TOKEN.sub(lambda m:s['mapping'][m.group()], checked)
    # Snapshot is immutable to the online Agent and the later export checks it.
    ch.write(p/'review-result.txt', checked.encode(), True)
    s.update(phase='waiting_confirmation', result_sha256=sha(checked.encode()), restore=restore)
    ch.put_json(p/'document-state.json', s)
    return checked


def make_docx(text):
    document = ET.Element(W+'document'); body = ET.SubElement(document,W+'body')
    for line in text.split('\n'):
        p=ET.SubElement(body,W+'p'); r=ET.SubElement(p,W+'r'); t=ET.SubElement(r,W+'t')
        t.set('{http://www.w3.org/XML/1998/namespace}space','preserve'); t.text=line
    result=io.BytesIO()
    with ZipFile(result,'w',ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        z.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr('word/document.xml',ET.tostring(document,encoding='utf-8',xml_declaration=True))
    return result.getvalue()


def export(task, reviewed_sha256, extension):
    p,s=state(task)
    require(s['phase']=='waiting_confirmation', 'document_phase')
    text=ch.read(p/'review-result.txt').decode()
    require(sha(text.encode())==s['result_sha256']==reviewed_sha256, 'document_result_changed')
    require(extension in ('.txt','.docx'), 'document_format')
    result = make_docx(text) if extension=='.docx' else text.encode()
    s['phase']='completed'; ch.put_json(p/'document-state.json',s)
    return result
