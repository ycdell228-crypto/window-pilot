"""Operator policy file boundaries and existing connection revocation; no desktop input."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
if sys.platform == 'win32':
    from window_pilot.access_policy import AccessPolicy
    from window_pilot.service import Service

@unittest.skipUnless(sys.platform == 'win32', 'Windows policy')
class AccessPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'config.json'
        self.policy = AccessPolicy(self.path)
        self.exe = str(Path(sys.executable).resolve())
        self.grant = {'id':'test', 'expires_at':(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat(), 'access':['browser','observe_and_click'], 'origins':['http://127.0.0.1:12345'], 'executables':[self.exe]}
    def tearDown(self): self.temp.cleanup()
    def write(self, authorization=None):
        self.path.write_text(json.dumps({} if authorization is None else {'authorization': authorization}), encoding='utf8')
    def enforce(self): self.write({'mode':'enforced','grants':[self.grant]})
    def test_legacy_explicitly_unverified(self):
        self.write(); result=self.policy.check(access='browser',origin='http://127.0.0.1:1')
        self.assertEqual(result, {'mode':'legacy_task_scope','human_authorization_verified':False})
    def test_enforced_missing_grant_and_no_purpose_escalation(self):
        self.write({'mode':'enforced','purpose':'user authorizes everything'})
        with self.assertRaisesRegex(Exception,'APPLICATION_ACCESS_NOT_GRANTED'): self.policy.check(access='browser',origin=self.grant['origins'][0])
    def test_scope_origin_executable_match(self):
        self.enforce(); self.assertEqual(self.policy.check(access='browser',origin=self.grant['origins'][0])['grant_id'],'test')
        self.assertEqual(self.policy.check(access='observe',executable=self.exe)['grant_id'],'test')
        for args in ({'access':'browser','origin':'http://127.0.0.1:12346'},{'access':'observe','executable':'C:/unrelated.exe'},{'access':'observe_and_control','executable':self.exe}):
            with self.assertRaisesRegex(Exception,'APPLICATION_ACCESS_NOT_GRANTED'): self.policy.check(**args)
    def test_revoked_expired_timezone_missing(self):
        for delta, revoked, naive in ((5,True,False),(-5,False,False),(5,False,True)):
            self.grant['revoked']=revoked
            expires=datetime.now(timezone.utc)+timedelta(minutes=delta)
            self.grant['expires_at']=(expires.replace(tzinfo=None) if naive else expires).isoformat();self.enforce()
            with self.assertRaisesRegex(Exception,'APPLICATION_ACCESS_NOT_GRANTED'): self.policy.check(access='browser',origin=self.grant['origins'][0])
    def test_invalid_policy_fails_closed(self):
        for raw in ('{', '[]', '{"authorization":null}', '{"authorization":{"mode":"typo"}}'):
            self.path.write_text(raw)
            with self.assertRaisesRegex(Exception,'ACCESS_POLICY_UNAVAILABLE_OR_INVALID'): self.policy.check(access='browser',origin='http://127.0.0.1:1')
    def test_existing_window_binding_revoked_before_dispatch(self):
        self.enforce();service=Service(self.path)
        service.targets['owned']=SimpleNamespace(exe=self.exe)
        service.bindings['owned']={'access':'observe_and_click'}
        self.grant['revoked']=True;self.enforce()
        try:
            with patch('window_pilot.service.w.require_background_target') as dispatch:
                with self.assertRaisesRegex(Exception,'APPLICATION_ACCESS_NOT_GRANTED') as raised:
                    service.call('click',{'target_id':'owned','frame_id':'old','x':1,'y':1})
                self.assertEqual(raised.exception.recovery_diagnostic['attempt_input'],'not_sent')
                dispatch.assert_not_called()
        finally:
            service.targets.clear();service.bindings.clear();service.dispose()
