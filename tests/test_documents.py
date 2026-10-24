"""Synthetic documents only. Exercise release gates, formats and identity restoration."""
import base64
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1]/'privacy-assistant'
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'skill/scripts'))
sys.path.insert(0,str(ROOT/'runtime/Lib/site-packages'))
import document_engine as d
import task_channel as ch
import mac_workflow as mac
from agent_boundary import profile

TEXT='姓名：林安。学号：2026000001。\n林安参加了活动，得分 42，建议下周交流。\n联系电话：13800138000；邮箱：fiction@example.invalid。\n会议地点为虚构星河学院，记录日期 2026年10月20日。'


def pdf(text='Name: Fictional Person. Score: 42.'):
    from pypdf import PdfWriter
    from pypdf.generic import NameObject, DictionaryObject, DecodedStreamObject
    w=PdfWriter();page=w.add_blank_page(width=600,height=800)
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
    page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):w._add_object(font)})})
    stream=DecodedStreamObject();stream.set_data(('BT /F1 12 Tf 30 700 Td ('+text+') Tj ET').encode())
    page[NameObject('/Contents')]=w._add_object(stream)
    out=io.BytesIO();w.write(out);return out.getvalue()


class Document(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name);self.task=self.base/'Vault/task'
    def tearDown(self):self.temp.cleanup()
    def prepare(self,text=TEXT,ext='.txt'):
        data=d.make_docx(text) if ext=='.docx' else text.encode()
        return d.prepare(self.task,data,ext,['林安','虚构星河学院'])
    def approve(self,draft):return d.approve(self.task,draft,d.sha(draft.encode()))
    def test_preview_has_no_release_before_local_approval(self):
        draft=self.prepare()['draft']
        self.assertNotIn('林安',draft);self.assertNotIn('13800138000',draft);self.assertNotIn('fiction@example.invalid',draft)
        self.assertIn('42',draft)
        self.assertFalse((self.task/'private/approved.txt').exists())
        with self.assertRaises(ValueError):d.preview(self.task,draft,True)
    def test_full_docx_roundtrip_restores_and_removes_metadata(self):
        draft=self.prepare(ext='.docx')['draft'];self.approve(draft)
        result=d.preview(self.task,'摘要：\n'+draft,True)
        self.assertIn('林安',result);self.assertIn('2026000001',result);self.assertIn('42',result)
        docx=d.export(self.task,d.sha(result.encode()),'.docx')
        self.assertEqual(d.docx_text(docx),'摘要：\n'+TEXT)
        with ZipFile(io.BytesIO(docx)) as z:self.assertNotIn('docProps/core.xml',z.namelist())
    def test_keep_pseudonyms_by_default_option(self):
        draft=self.prepare()['draft'];self.approve(draft);result=d.preview(self.task,draft,False)
        self.assertNotIn('林安',result);self.assertIn('⟦PVT_',result)
        self.assertEqual(d.export(self.task,d.sha(result.encode()),'.txt').decode(),draft)
    def test_summary_may_omit_token_but_never_guesses_identity(self):
        draft=self.prepare()['draft'];self.approve(draft)
        result=d.preview(self.task,'得分 42，建议下周交流。',True)
        self.assertEqual(result,'得分 42，建议下周交流。')
    def test_sensitive_terms_cannot_replace_generated_token_digits(self):
        safe,mapping=d.redact('虚构星河学院 编号0001',['虚构星河学院','0001'])
        self.assertEqual(len(d.TOKEN.findall(safe)),2)
        self.assertEqual(d.valid_text(safe,mapping),safe)
    def test_docx_classification_in_header_or_properties_blocks(self):
        for name in ['word/header1.xml','word/footer1.xml','docProps/core.xml']:
            out=io.BytesIO(d.make_docx('普通正文'))
            with ZipFile(out,'a') as z:z.writestr(name,'<root><text>秘密★10年</text></root>')
            with self.assertRaisesRegex(ValueError,'document_classified'):d.extract(out.getvalue(),'.docx')
    def test_pdf_inline_image_blocks(self):
        from pypdf import PdfReader,PdfWriter
        from pypdf.generic import NameObject,DecodedStreamObject
        writer=PdfWriter();writer.append(PdfReader(io.BytesIO(pdf())))
        stream=DecodedStreamObject();stream.set_data(b'BT /F1 12 Tf 30 700 Td (Fictional note) Tj ET\nBI /W 1 /H 1 /CS /RGB /BPC 8 ID '+bytes([0,0,0])+b' EI')
        writer.pages[0][NameObject('/Contents')]=writer._add_object(stream)
        out=io.BytesIO();writer.write(out)
        with self.assertRaisesRegex(ValueError,'document_scan_or_graphics'):d.extract(out.getvalue(),'.pdf')
    def test_same_name_reuses_same_token(self):
        safe,mapping=d.redact('林安与林安',['林安'])
        self.assertEqual(len(mapping),1);self.assertEqual(len(d.TOKEN.findall(safe)),2)
    def test_fullwidth_and_zero_width_phone(self):
        safe,mapping=d.redact(d.normal('电话：１３８００１３８０００；电话：138\u200b00138000'),[])
        self.assertNotIn('13800138000',safe);self.assertEqual(len(mapping),1)
    def test_cannot_approve_changed_review_digest(self):
        draft=self.prepare()['draft']
        with self.assertRaises(ValueError):d.approve(self.task,draft,'0'*64)
        self.assertFalse((self.task/'private/approved.txt').exists())
    def test_local_review_may_remove_identifying_paragraph(self):
        draft=self.prepare()['draft'];approved=self.approve('仅保留数值 42。')
        self.assertEqual(approved,'仅保留数值 42。')
    def test_review_reintroducing_identifier_blocks(self):
        draft=self.prepare()['draft']
        with self.assertRaises(ValueError):self.approve(draft+' 电话：13800138000')
    def test_result_cannot_restore_identity_removed_at_local_review(self):
        prepared=d.prepare(self.task,'人员甲参加了活动。\n人员乙需要保密。'.encode(),'.txt',['人员甲','人员乙'])
        tokens=d.TOKEN.findall(prepared['draft'])
        self.approve(tokens[0]+'参加了活动。')
        with self.assertRaisesRegex(ValueError,'document_token_not_released'):
            d.preview(self.task,tokens[1]+'参加了活动。',True)
        self.assertFalse((self.task/'private/review-result.txt').exists())
    def test_unknown_tokens_block(self):
        draft=self.prepare()['draft'];self.approve(draft)
        with self.assertRaises(ValueError):d.preview(self.task,draft+'⟦PVT_abcdef0123456789_0001⟧',True)
    def test_broken_token_blocks(self):
        draft=self.prepare()['draft'];self.approve(draft)
        with self.assertRaises(ValueError):d.preview(self.task,draft.replace('⟧',']'),True)
    def test_new_raw_identity_blocks(self):
        draft=self.prepare()['draft'];self.approve(draft)
        for extra in ['姓名：杜青。','电话：13900139000','https://example.invalid/upload','fiction@example.invalid']:
            with self.assertRaises(ValueError):d.preview(self.task,draft+'\n'+extra,True)
    def test_original_mutation_blocks(self):
        draft=self.prepare()['draft'];self.approve(draft)
        (self.task/'private/original.bin').write_bytes(b'changed')
        with self.assertRaises(ValueError):d.preview(self.task,draft,True)
    def test_result_mutation_after_review_blocks(self):
        draft=self.prepare()['draft'];self.approve(draft);result=d.preview(self.task,draft,True)
        (self.task/'private/review-result.txt').write_text('changed')
        with self.assertRaises(ValueError):d.export(self.task,d.sha(result.encode()),'.txt')
    def test_duplicate_export_blocks(self):
        draft=self.prepare()['draft'];self.approve(draft);result=d.preview(self.task,draft,False)
        digest=d.sha(result.encode());d.export(self.task,digest,'.txt')
        with self.assertRaises(ValueError):d.export(self.task,digest,'.txt')
    def test_classified_and_wrong_encoding_rejected(self):
        for raw,ext in [('【机密】\n内容'.encode(),'.txt'),('秘密★10年\n内容'.encode(),'.txt'),(b'\xff\xfe\x00','.txt'),(b'abc','.doc')]:
            with self.assertRaises((ValueError,UnicodeDecodeError)):d.extract(raw,ext)
    def test_unknown_name_requires_local_review_not_claimed_automatic(self):
        draft=d.prepare(self.task,'杜青昨天参加活动。'.encode(),'.txt',[])['draft']
        self.assertIn('杜青',draft)
        self.assertFalse((self.task/'private/approved.txt').exists())
    def test_docx_active_and_embedded_content_rejected(self):
        original=d.make_docx('正文')
        for name,value in [('word/comments.xml',b'<comments/>'),('word/media/image.png',b'fake'),('word/embeddings/file.bin',b'fake'),('word/vbaProject.bin',b'fake')]:
            out=io.BytesIO(original)
            with ZipFile(out,'a') as z:z.writestr(name,value)
            with self.assertRaises(ValueError):d.extract(out.getvalue(),'.docx')
    def test_docx_revision_and_external_relationship_rejected(self):
        for change in ['revision','external']:
            out=io.BytesIO()
            with ZipFile(io.BytesIO(d.make_docx('正文'))) as src,ZipFile(out,'w') as dst:
                for name in src.namelist():
                    data=src.read(name)
                    if change=='revision' and name=='word/document.xml':data=data.replace(b'<ns0:t',b'<ns0:ins/><ns0:t',1)
                    if change=='external' and name=='_rels/.rels':data=data.replace(b'</Relationships>',b'<Relationship TargetMode="External" Target="https://example.invalid"/></Relationships>')
                    dst.writestr(name,data)
            with self.assertRaises(ValueError):d.extract(out.getvalue(),'.docx')
    def test_plain_pdf_extraction(self):
        text=d.extract(pdf(),'.pdf');self.assertIn('Score: 42',text)
    def test_empty_encrypted_and_image_pdf_rejected(self):
        from pypdf import PdfReader,PdfWriter
        from pypdf.generic import NameObject,DictionaryObject
        for kind in ['empty','encrypted','image']:
            writer=PdfWriter()
            if kind=='empty':writer.add_blank_page(width=600,height=800)
            else:writer.append(PdfReader(io.BytesIO(pdf())))
            if kind=='encrypted':writer.encrypt('fictional-test-password')
            if kind=='image':writer.pages[0]['/Resources'][NameObject('/XObject')]=DictionaryObject({NameObject('/Im1'):DictionaryObject()})
            out=io.BytesIO();writer.write(out)
            with self.assertRaises(ValueError):d.extract(out.getvalue(),'.pdf')
    def test_document_protocol_rejects_paths_and_guest_approval(self):
        identifier='a'*32;root=self.base/'Queue'
        data=base64.b64encode(b'approved fictional text').decode()
        ch.guest_rpc(root,{'action':'deliver_document','id':identifier,'data':data})
        self.assertEqual((root/identifier/'document.txt').read_text(),'approved fictional text')
        for req in [{'action':'document_approve','id':identifier,'confirmed':True},
                    {'action':'deliver_document','id':identifier,'data':data,'path':'/private/source.txt'}]:
            with self.assertRaises(ValueError):ch.guest_rpc(root,req)
    def test_job_retains_document_kind(self):
        jobs=ch.Jobs(self.base/'Jobs');identifier='b'*32;jobs.create(identifier,'document')
        for event in ['selected','released','result_received','local_confirmed']:
            jobs.advance(identifier,event);self.assertEqual(jobs.kind(identifier),'document')


@unittest.skipUnless(sys.platform=='darwin','macOS OS boundary required')
class DocumentIsolation(unittest.TestCase):
    setUp=Document.setUp
    tearDown=Document.tearDown
    def test_mac_ui_orchestration_reaches_confirmed_export(self):
        import document_mac
        import assistant
        source=self.base/'fictional.docx';source.write_bytes(d.make_docx(TEXT))
        for folder in ['Vault','Exchange','Settings']:(self.base/folder).mkdir(exist_ok=True)
        run=subprocess.run
        def local_only_run(args,**kwargs):
            if args[0]=='/usr/bin/open':return subprocess.CompletedProcess(args,0)
            return run(args,**kwargs)
        def choose(prompt,options):
            if options==['保留代号','本地恢复身份']:return '本地恢复身份'
            return options[0]
        def launch(agent,task,exchange,base,document=False):
            self.assertTrue(document)
            safe=ch.read(exchange/'document.txt');self.assertNotIn('林安',safe.decode())
            ch.write(exchange/'result.txt',safe)
        with patch.object(assistant,'check_package'),patch.object(assistant,'notify'), \
             patch.object(mac,'pick_agent',return_value='codex'), \
             patch.object(mac,'dialog',side_effect=[str(source),'林安\n虚构星河学院']), \
             patch.object(mac,'choose',side_effect=choose), \
             patch.object(mac,'launch_agent',side_effect=launch), \
             patch.object(subprocess,'run',side_effect=local_only_run):
            document_mac.run('codex',self.base)
        output=next((self.base/'Vault/Exports').glob('*.docx'))
        self.assertEqual(d.docx_text(output.read_bytes()),TEXT)
    def test_unisolated_worker_reads_no_document(self):
        p=self.task/'private';p.mkdir(parents=True);source=self.base/'original.txt';source.write_text(TEXT)
        ch.put_json(p/'input.json',{'source':str(source),'terms':['林安']})
        result=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/mac_worker.py'),'document_prepare',str(self.task)],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0);self.assertNotIn('林安',result.stdout+result.stderr)
        self.assertFalse((p/'original.bin').exists())
    def test_offline_document_worker_roundtrip(self):
        p=self.task/'private';p.mkdir(parents=True);source=self.base/'original.docx';source.write_bytes(d.make_docx(TEXT))
        before=source.read_bytes();ch.put_json(p/'input.json',{'source':str(source),'terms':['林安','虚构星河学院']})
        mac.worker('document_prepare',self.task)
        draft=(p/'draft.txt').read_text();ch.put_json(p/'approval.json',{'text':draft,'sha256':d.sha(draft.encode())})
        mac.worker('document_approve',self.task)
        self.assertNotIn('林安',(p/'approved.txt').read_text())
        ch.write(p/'returned.txt',draft.encode());ch.put_json(p/'result-options.json',{'restore':True})
        mac.worker('document_preview',self.task)
        result=(p/'review-result.txt').read_text();ch.put_json(p/'export-options.json',{'sha256':d.sha(result.encode()),'extension':'.docx'})
        mac.worker('document_export',self.task)
        self.assertEqual(d.docx_text((p/'final.docx').read_bytes()),TEXT)
        self.assertEqual(source.read_bytes(),before)
    def test_online_child_cannot_read_document_or_mapping(self):
        p=self.task/'private';p.mkdir(parents=True);source=self.base/'private-original.txt';source.write_text('SYNTHETIC_PRIVATE_ONLY')
        (p/'document-state.json').write_text('SYNTHETIC_MAPPING')
        script='''from pathlib import Path
import sys
for name in sys.argv[1:]:
 try:Path(name).read_bytes()
 except PermissionError:pass
 else:sys.exit(9)
'''
        result=subprocess.run(['/usr/bin/sandbox-exec','-p',profile(self.base/'Vault',protected=[source]),sys.executable,'-I','-c',script,str(source),str(p/'document-state.json')],capture_output=True)
        self.assertEqual(result.returncode,0)

if __name__=='__main__':unittest.main()

class WindowsDocumentAdapter(unittest.TestCase):
    def test_roundtrip_uses_local_confirmation_and_only_releases_approved_text(self):
        import document_windows as win
        class Backend:
            def __init__(self,root):self.root=root;self.delivered=None;self.events=[]
            def start(self,role):self.events.append(('start',role))
            def refresh_network(self):pass
            def rpc(self,role,r):
                self.events.append((role,r['action']))
                action=r['action'];task=self.root/'offline'/r.get('id','none')
                if action=='health':return {'status':role}
                if action=='document_prepare':return d.prepare(task,base64.b64decode(r['data']),r['extension'],r['terms'])
                if action=='document_approve':return {'data':base64.b64encode(d.approve(task,r['text'],r['sha256']).encode()).decode()}
                if action=='deliver_document':self.delivered=base64.b64decode(r['data']).decode();return {'ok':True}
                if action=='document_result':return {'data':base64.b64encode(self.delivered.encode()).decode()}
                if action=='document_preview':return {'text':d.preview(task,base64.b64decode(r['data']).decode(),r['restore'])}
                if action=='document_export':return {'data':base64.b64encode(d.export(task,r['sha256'],r['extension'])).decode()}
                if action=='status':return {'ok':True}
                raise AssertionError(action)
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);source=base/'fictional.txt';source.write_text(TEXT)
            backend=Backend(base);jobs=ch.Jobs(base/'Jobs');identifier='c'*32
            def dialogue(base,req):
                mode=req['mode']
                if mode=='document_file':return {'path':str(source)}
                if mode=='document_terms':return {'confirmed':True,'terms':['林安','虚构星河学院']}
                if mode=='document_review':
                    self.assertIsNone(backend.delivered)
                    self.assertNotIn('林安',req['text'])
                    return {'confirmed':True,'text':req['text']}
                if mode=='document_options':return {'confirmed':True,'restore':True}
                if mode=='document_confirm':
                    self.assertIn('林安',req['text']);return {'confirmed':True,'extension':'.docx'}
                raise AssertionError(mode)
            with patch.object(win.subprocess,'Popen'):
                win.handle(base,backend,jobs,{'id':identifier,'action':'new_document'},dialogue,lambda p,document:ch.read(p))
                self.assertNotIn('林安',backend.delivered)
                win.handle(base,backend,jobs,{'id':identifier,'action':'submit_result'},dialogue,None)
            self.assertEqual(jobs.phase(identifier),'completed')
            output=next((base/'Vault/Exports').glob('*.docx'))
            self.assertEqual(d.docx_text(output.read_bytes()),TEXT)
    def test_fixed_guest_update_payload_contains_no_host_paths_or_profiles(self):
        import bridge_bundle as b
        compile(b.APPLY,'guest-update','exec')
        with ZipFile(io.BytesIO(b.payload(ROOT))) as z:
            names=z.namelist()
            self.assertIn('opt/privacy-bridge/document_engine.py',names)
            self.assertIn('opt/privacy-bridge/pypdf/__init__.py',names)
            self.assertFalse(any('teacher' in n or 'Settings' in n or '..' in n for n in names))
