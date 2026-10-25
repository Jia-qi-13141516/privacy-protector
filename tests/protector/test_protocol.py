import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'privacy-assistant/protector'))
import protocol

class Protocol(unittest.TestCase):
    def test_public_cannot_supply_a_path_or_claim_a_role(self):
        for obj in [dict(action='submit',task='统计记录',path='/private/student.xlsx'),
                    dict(action='submit',task='统计记录',uid=0),dict(action='select',id='a'*32,path='/tmp/source.xlsx'),
                    dict(action='restore',id='a'*32),dict(action='confirm',id='a'*32,destination='/tmp/out.xlsx'),
                    dict(action='read',id='a'*32),dict(action='exec',command='cat original.xlsx')]:
            with self.subTest(obj=obj),self.assertRaises(ValueError):protocol.public_request(obj)
    def test_duplicate_keys_and_non_objects_are_not_ambiguous(self):
        for blob in [b'{"action":"health","action":"restore"}',b'[]',b'null',b'"status"',b'{',b'\xff']:
            with self.subTest(blob=blob),self.assertRaises(ValueError):protocol.decode(blob)
    def test_status_does_not_copy_private_fields(self):
        record={'id':'b'*32,'phase':'waiting_for_confirmation','sealed':True,'task':'sensitive task',
                'source':'/private/NAME.xlsx','preview':'SYNTHETIC_CANARY','identity_map':{'1':'NAME'},'output':'/secret/out.xlsx'}
        result=protocol.status(record)
        self.assertEqual(set(result),{'id','phase','original_access'})
        self.assertEqual(result['original_access'],'os_denied')
    def test_failed_sealing_is_not_reported_as_verified(self):
        r=protocol.status({'id':'b'*32,'phase':'blocked','sealed':False,'code':'source_busy'})
        self.assertEqual(r['original_access'],'not_verified')
    def test_unknown_exceptions_do_not_leak_paths(self):
        self.assertEqual(protocol.failure(PermissionError('/home/SECRET/student.xlsx')),{'error':'worker_failed'})
    def test_private_operations_validate_ids_and_keys(self):
        for obj in [dict(action='select',id='../escape',path='/tmp/x'),dict(action='select',id='a'*32,path='/x',extra=True),dict(action='confirm',id='a'*32,destination='\0')]:
            with self.assertRaises(ValueError):protocol.private_request(obj)
if __name__=='__main__':unittest.main()
