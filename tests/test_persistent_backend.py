import base64,hashlib,io,json,os,sys,tempfile,unittest,uuid
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]/'privacy-assistant'
sys.path.insert(0,str(ROOT/'scripts'));sys.path.insert(0,str(ROOT/'runtime/Lib/site-packages'))
import component_download as dl,vm_backend as vm,vm_seed,network_policy

class Download(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.cache=Path(self.tmp.name)/'Cache'
 def tearDown(self):self.tmp.cleanup()
 def asset(self,data=b'SYNTHETIC'):
  return dict(url='https://download.codebuddy.cn/workbuddy/test.deb',sha256=hashlib.sha256(data).hexdigest(),max_bytes=20)
 def test_source_allowlist(self):
  for url in ('http://download.codebuddy.cn/x','https://evil.example/x','https://download.codebuddy.cn.evil.example/x','https://user@download.codebuddy.cn/x','https://download.codebuddy.cn:444/x'):
   with self.assertRaises(ValueError):dl.checked_url(url)
 def test_redirect_rejected_before_request(self):
  with self.assertRaises(ValueError):dl.Redirect().redirect_request(None,None,302,'',{},'https://evil.example/x')
 def test_verified_cache_never_connects(self):
  self.cache.mkdir();asset=self.asset();file=self.cache/(asset['sha256']+'.deb');file.write_bytes(b'SYNTHETIC')
  with patch.object(dl.urllib.request,'build_opener') as network:self.assertEqual(dl.fetch(asset,self.cache),file)
  network.assert_not_called()
 def test_corrupt_cache_stops(self):
  self.cache.mkdir();asset=self.asset();(self.cache/(asset['sha256']+'.deb')).write_bytes(b'ALTERED')
  with self.assertRaisesRegex(ValueError,'cache_integrity'):dl.fetch(asset,self.cache)
 def test_limit_validated(self):
  for n in (-1,0,True,2*1024**3+1):
   asset=self.asset();asset['max_bytes']=n
   with self.assertRaises(ValueError):dl.fetch(asset,self.cache)
 def test_stream_tamper_not_promoted(self):
  class Reply(io.BytesIO):
   status=200;headers={'Content-Length':'9'}
   def geturl(self):return 'https://download.codebuddy.cn/workbuddy/test.deb'
  class Opener:
   def open(self,*args,**kwargs):return Reply(b'CORRUPTED')
  with patch.object(dl.urllib.request,'build_opener',return_value=Opener()):
   with self.assertRaisesRegex(ValueError,'integrity'):dl.fetch(self.asset(),self.cache)
  self.assertEqual(list(self.cache.iterdir()),[])

class Backend(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name);(self.base/'Settings').mkdir();self.backend=vm.Backend(self.base,Path('/fake/vbox'))
  self.backend.state['machines']={r:{'id':str(uuid.uuid4()),'ready':True} for r in ('online','offline')}
 def tearDown(self):self.tmp.cleanup()
 def info(self,role):return {'VMState':'poweroff','clipboard':'disabled','draganddrop':'disabled','nic1':'nat' if role=='online' else 'none','localhostReachable':'0','vrde':'off','usb':'off'}
 def test_actual_boundary_dimensions(self):
  for role in ('online','offline'):
   with patch.object(self.backend,'info',side_effect=self.info):self.backend.boundary(role)
  for key,value in (('nic2','nat'),('nic1','bridged'),('clipboard','bidirectional'),('draganddrop','hosttoguest'),('localhostReachable','1'),('SharedFolderNameMachineMapping1','x'),('Forwarding(0)','x'),('usb','on'),('vrde','on')):
   info=self.info('online');info[key]=value
   with patch.object(self.backend,'info',return_value=info):
    with self.assertRaises(ValueError,msg=key):self.backend.boundary('online')
 def test_offline_nic_never_accepted_after_install(self):
  info=self.info('offline');info['nic1']='nat'
  with patch.object(self.backend,'info',return_value=info):
   with self.assertRaises(ValueError):self.backend.boundary('offline')
 def test_reuse_no_download_no_recreation(self):
  with patch.object(self.backend,'info',side_effect=self.info),patch.object(vm,'fetch') as fetch,patch.object(self.backend,'cli') as cli:
   self.backend.provision()
  fetch.assert_not_called();self.assertEqual(cli.call_args.args[0],"modifyvm");self.assertNotIn("createvm",cli.call_args.args)
 def test_guest_argv_uses_implicit_arg0(self):
  with patch.object(self.backend,'cli',return_value='') as cli:self.backend.guest('online','/usr/bin/python3',['-I','/opt/privacy-bridge/guest_rpc.py','a'*32])
  args=cli.call_args.args;self.assertEqual(args[args.index('--')+1:],('-I','/opt/privacy-bridge/guest_rpc.py','a'*32))
 def test_uuid_invalid_rejected_before_command(self):
  self.backend.state['machines']['online']['id']='../../host'
  with patch.object(self.backend,'cli') as cli:
   with self.assertRaises(ValueError):self.backend.info('online')
  cli.assert_not_called()
 def test_window_attach_does_not_reset_running_vm(self):
  info=self.info('online');info['VMState']='running'
  with patch.object(self.backend,'info',return_value=info),patch.object(self.backend,'refresh_network'),patch.object(self.backend,'cli',side_effect=ValueError('already_gui')) as cli:self.backend.start('online',True)
  self.assertEqual(cli.call_count,1)

class Seed(unittest.TestCase):
 def test_seed_roundtrip_and_no_host_mount(self):
  import pycdlib
  with tempfile.TemporaryDirectory() as temp:
   iso_path=Path(temp)/'seed.iso';vm_seed.create(ROOT,'online','FAKE_PASSWORD','fake-instance',iso_path)
   iso=pycdlib.PyCdlib();iso.open(str(iso_path));out=io.BytesIO();iso.get_file_from_iso_fp(out,joliet_path='/user-data');iso.close()
   cfg=json.loads(out.getvalue().decode().split('\n',1)[1]);self.assertEqual(cfg['users'][0]['groups'],['users']);self.assertNotIn('mounts',cfg)
   paths={x['path'] for x in cfg['write_files']};self.assertIn('/opt/privacy-bridge/guest_rpc.py',paths)
   self.assertFalse(any('/Users/' in x['path'] for x in cfg['write_files']))
 def test_wrong_role_rejected(self):
  with self.assertRaises(ValueError):vm_seed.config(ROOT,'host','fake','fake')
 def test_firewall_rejects_injection(self):
  for address in ('1.2.3.4; accept','::1','1.2.3.4\nflush ruleset'):
   with self.assertRaises(ValueError):network_policy.firewall([address])
 def test_firewall_covers_host_and_private_ranges(self):
  rules=network_policy.firewall(['203.0.113.42']);self.assertIn('203.0.113.42',rules)
  for token in ('10.0.0.0/8','100.64.0.0/10','192.168.0.0/16','169.254.0.0/16','meta nfproto ipv6 drop'):self.assertIn(token,rules)
 def test_column_metadata_cannot_carry_identity(self):
  import task_channel as channel
  with tempfile.TemporaryDirectory() as temp:
   with self.assertRaisesRegex(ValueError,'invalid_columns'):
    channel.guest_rpc(Path(temp),{'action':'deliver','id':'a'*32,'data':base64.b64encode(b'person\np_fake\n').decode(),'columns':[{'output':'person','kind':'id','meaning':'SYNTHETIC_NAME'}]})
   self.assertEqual(list(Path(temp).iterdir()),[])
 def test_all_release_assets_pinned(self):
  assets=json.loads((ROOT/'backend/assets.json').read_text())['assets']
  self.assertEqual(set(assets),{'virtualbox_windows','ubuntu_disk','workbuddy','vc_redist'})
  for asset in assets.values():dl.checked_url(asset['url']);self.assertEqual(len(asset['sha256']),64)
 def test_live_health_precedes_file_selection(self):
  import windows_service
  from unittest.mock import Mock
  backend=Mock();backend.rpc.return_value={'status':'bad'}
  with patch.object(windows_service,'dialogue') as dialogue:
   with self.assertRaises(ValueError):windows_service.handle(Path('/fake'),backend,Mock(),{'action':'new_table','id':'a'*32})
  dialogue.assert_not_called()

if __name__=='__main__':unittest.main(verbosity=2)
