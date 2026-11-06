#!/usr/bin/env python3
"""Small source tests; hardware checks are recorded separately in docs."""
import importlib.machinery, importlib.util, pathlib, unittest, sys
sys.dont_write_bytecode = True
from unittest.mock import patch
root=pathlib.Path(__file__).resolve().parents[2]
path=root/'package/custom/router-audit/files/router-audit'
loader=importlib.machinery.SourceFileLoader('router_audit',str(path));spec=importlib.util.spec_from_loader(loader.name,loader);A=importlib.util.module_from_spec(spec);loader.exec_module(A)
class Tests(unittest.TestCase):
    def test_duration_bounds(self):
        self.assertEqual(A.parse_since('15m'),900)
        for value in ['0m','31d','15m;id','../../../etc/shadow']:
            with self.assertRaises(Exception):A.parse_since(value)
    def test_independent_failure(self):
        def fail():raise OSError('secret should not appear')
        with patch.dict(A.MODULES,{'fixture':fail,'healthy':lambda:{'value':1}}):
            r=A.envelope('fixture',0,10);self.assertEqual(r['status'],'error');self.assertNotIn('secret',str(r));self.assertEqual(A.envelope('healthy',0,10)['status'],'ok')
    def test_internal_queries_separate(self):
        rows=[{'source':'dnsmasq','client':'127.0.0.1','qname':'x.example','qtype':1,'rcode':0},{'source':'daed','client':'192.0.2.1:123','qname':'x.example.','qtype':1,'rcode':3}]
        out=A.dns_summary(rows)['clients'];self.assertEqual(len(out),2);self.assertTrue(out[0]['internal']);self.assertFalse(out[1]['internal']);self.assertEqual(out[1]['rcodes']['3'],1)
    def test_missing_source(self):
        self.assertIsNone(A.command(['/nonexistent/router-audit-fixture']));self.assertTrue(A.ERR)
if __name__=='__main__':unittest.main()
