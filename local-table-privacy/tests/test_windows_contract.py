"""Platform-independent contract tests; not a substitute for a Windows device run."""
import importlib.util
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('host',ROOT/'scripts/windows_host.py');host=importlib.util.module_from_spec(spec);spec.loader.exec_module(host)

class WindowsContract(unittest.TestCase):
    def setUp(self):
        self.maps=[('C:\\资料 & 教学','C:\\PrivacyRuntime',True),('C:\\only-output','C:\\PrivacyOutput',False)]
        self.xml=ET.fromstring(host.configuration(self.maps))
    def test_network_disabled(self):self.assertEqual(self.xml.findtext('Networking'),'Disable')
    def test_clipboard_disabled(self):self.assertEqual(self.xml.findtext('ClipboardRedirection'),'Disable')
    def test_capture_disabled(self):
        for n in ['AudioInput','VideoInput','PrinterRedirection']:self.assertEqual(self.xml.findtext(n),'Disable')
    def test_only_output_writable(self):self.assertEqual([x.findtext('SandboxFolder') for x in self.xml.findall('MappedFolders/MappedFolder') if x.findtext('ReadOnly')=='false'],[r'C:\PrivacyOutput'])
    def test_xml_paths_escaped(self):self.assertEqual(self.xml.findtext('MappedFolders/MappedFolder/HostFolder'),self.maps[0][0])
    def test_no_raw_path_in_command(self):
        command=self.xml.findtext('LogonCommand/Command');self.assertNotIn('资料',command);self.assertIn('-I -B',command)
    def test_no_bypass_network_fallback(self):
        text=(ROOT/'scripts/windows_host.py').read_text();self.assertNotIn('ExecutionPolicy',text);self.assertNotIn('Invoke-WebRequest',text)

if __name__=='__main__':unittest.main()
