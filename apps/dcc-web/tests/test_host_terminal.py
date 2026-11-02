"""PTY session boundaries without opening host shells or remote connections."""
import base64
from pathlib import Path
import queue
import sys
import threading
import time
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from host_terminal import HostTerminals

class FakePTY:
    def __init__(self,profile,cols,rows):
        self.input=[];self.dimensions=(cols,rows);self.queue=queue.Queue();self.stopped=False
    def read(self):return self.queue.get()
    def write(self,value):self.input.append(value)
    def resize(self,cols,rows):self.dimensions=(cols,rows)
    def close(self):
        if not self.stopped:self.stopped=True;self.queue.put(b'')

class TerminalTests(unittest.TestCase):
    def setUp(self):
        self.manager=HostTerminals(FakePTY)
        self.addCleanup(self.cleanup)
    def cleanup(self):
        for session in list(self.manager.sessions.values()):session.close()
    def open(self,owner='user',login='login',profile='local',limit=16):
        return self.manager.open({'id':profile,'kind':'local'},owner,login,120,32,limit=limit)

    def test_close_deleted_profiles_preserves_other_hosts_and_owners(self):
        selected = self.open(profile='deleted')
        other_owner = self.open(owner='another', profile='deleted')
        retained = self.open(profile='retained')
        self.manager.close_profiles({'deleted'})
        self.assertTrue(selected.closed)
        self.assertTrue(other_owner.closed)
        self.assertNotIn(selected.id, self.manager.sessions)
        self.assertIn(retained.id, self.manager.sessions)
        self.assertFalse(retained.closed)

    def test_sixteen_sessions_and_configurable_limit(self):
        sessions=[self.open() for _ in range(16)]
        with self.assertRaisesRegex(ValueError,r'limit \(16\)'):self.open()
        self.manager.close(sessions[0].id,'user','login')
        self.assertIsNotNone(self.open())
        self.assertIsNotNone(self.open(owner='other'))
        with self.assertRaises(ValueError):self.open(limit=2)

    def test_owner_login_and_profile_are_independent(self):
        first=self.open(profile='first');second=self.open(profile='second')
        with self.assertRaises(KeyError):self.manager.get(first.id,'other','login')
        with self.assertRaises(KeyError):self.manager.get(first.id,'user','other-login')
        self.assertEqual(self.manager.get(first.id,'user','login').profile,'first')
        first.connection.write(b'first command\r')
        self.assertEqual(second.connection.input,[])
        self.manager.close(first.id,'user','login')
        self.assertFalse(second.closed)

    def test_completed_shell_does_not_consume_session_limit(self):
        first=self.open(limit=1);first.connection.close()
        for _ in range(100):
            if first.closed:break
            time.sleep(.001)
        self.assertTrue(first.closed)
        self.assertIsNotNone(self.open(limit=1))

    def test_output_is_bounded_and_reports_truncation(self):
        session=self.open();session.connection.queue.put(b'x'*1_000_020)
        for _ in range(100):
            with session.condition:ready=session.offset>0
            if ready:break
            time.sleep(.001)
        output=session.output(0,wait=0)
        self.assertTrue(output['truncated'])
        self.assertEqual(len(base64.b64decode(output['data'])),1_000_000)
        self.assertEqual(output['offset'],1_000_020)
        with self.assertRaises(ValueError):session.output(2_000_000,wait=0)

if __name__=='__main__':unittest.main()
