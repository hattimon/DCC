import copy
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reports import ReportStore, guidance_codes
from notifications import DEFAULTS, NotificationService, NoRedirect, redact


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'reports.json'
        self.store = ReportStore(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_bounded_history_has_ten_entries_per_page_and_compact_successes(self):
        for index in range(205):
            self.store.append('update','success',updated=index)
        first=self.store.snapshot()
        self.assertEqual((first['total'], first['pages'], len(first['entries'])), (200,20,10))
        self.assertEqual(first['entries'][0]['updated'],204)
        self.assertEqual(first['entries'][0]['details'],[])
        self.assertEqual(self.store.snapshot(20)['entries'][-1]['updated'],5)
        self.assertEqual(ReportStore(self.path).snapshot()['total'],200)

    def test_job_errors_and_blocked_updates_are_saved_without_success_details(self):
        self.store.record_job({'kind':'update','status':'done','results':{'updates':[
            {'name':'first','ok':True,'result':'updated'},
            {'name':'second','ok':False,'result':'port conflict'},
        ],'containers':[]}})
        event=self.store.snapshot(issues_only=True)['entries'][0]
        self.assertEqual((event['status'],event['updated']),('error',1))
        self.assertEqual(event['details'],[{'name':'second','result':'port conflict'}])

    def test_successful_panel_checks_and_restart_wait_polls_do_not_flood_reports(self):
        self.store.record_job({'kind':'self_update_check','status':'done','results':{'checked':True}})
        for _ in range(10):
            self.store.record_job({'kind':'schedule','status':'done','results':{'waiting':True}})
        self.assertEqual(self.store.snapshot()['total'],0)

    def test_unselected_scan_errors_do_not_turn_successful_updates_into_error_alerts(self):
        self.store.record_job({'kind':'schedule','status':'done','results':{
            'action':'update','ok':True,'updates':[{'name':'selected','ok':True}],
            'containers':[{'name':'unselected','check_error':True,'message':'Registry unavailable'}]}})
        self.assertEqual(self.store.snapshot()['entries'][0]['status'],'success')

    def test_panel_report_requires_the_exact_installed_image(self):
        self.store.panel_started('sha256:new')
        self.store.resolve_panel('sha256:old')
        self.assertEqual(self.store.snapshot()['entries'][0]['status'],'running')
        self.store.resolve_panel('sha256:new')
        self.assertEqual(ReportStore(self.path).snapshot()['entries'][0]['status'],'success')

    def test_corrupt_history_is_preserved(self):
        self.path.write_text('{invalid',encoding='utf-8')
        store=ReportStore(self.path)
        self.assertTrue(store.snapshot()['storage_error'])
        store.append('scan','error')
        self.assertEqual(self.path.read_text(),'{invalid')

    def test_existing_report_history_receives_deduplicated_repair_guidance(self):
        self.store.append('scan','warning',details=[
            {'name':'first','result':'Plik Compose nie jest dostępny (PermissionError). Rejestr wymaga logowania.'},
            {'name':'second','result':'Konflikt portu hosta. Rejestr wymaga logowania.'},
            {'name':'third','result':'Automatyczna aktualizacja zablokowana: trwałe dane współdzieli usługa first.'},
        ])
        entry=ReportStore(self.path).snapshot()['entries'][0]
        self.assertEqual(entry['help_codes'],['compose_file','ports','shared_data','registry_auth'])
        self.assertNotIn('help_codes',json.loads(self.path.read_text())[0])

    def test_guidance_recognises_network_architecture_and_unknown_errors(self):
        self.assertEqual(guidance_codes(['TLS handshake timeout']),['network'])
        self.assertEqual(guidance_codes(['No matching manifest for architecture linux/arm64']),['architecture'])
        self.assertEqual(guidance_codes(['Unexpected APIError']),['general'])


class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.reports=ReportStore(self.root/'reports.json')
        self.calls=[]
        def transport(url,payload,headers=None):
            self.calls.append((url,payload,headers))
            return {'ok':True,'messages':[{'id':'test'}]}
        self.service=NotificationService(self.root/'notifications.json',self.reports,transport)

    def tearDown(self):
        self.service.stop.set()
        self.temp.cleanup()

    def telegram(self):
        config=copy.deepcopy(DEFAULTS)
        config.update(enabled=True)
        config['telegram'].update(enabled=True,bot_token='12345:TEST_TOKEN',chat_id='-100123456')
        return config

    def event(self,kind='update',status='error'):
        identifier=self.reports.append(kind,status,message='A service update failed.',details=[{'name':'generic','result':'TLS timeout'}])
        return next(item for item in self.reports.snapshot()['entries'] if item['id']==identifier)

    def test_defaults_never_send_and_successes_never_alert(self):
        self.service.enqueue(self.event())
        self.assertTrue(self.service.events.empty())
        self.service.save(self.telegram())
        self.service.enqueue(self.event(status='success'))
        self.assertTrue(self.service.events.empty())
        self.assertEqual(self.calls,[])

    def test_tokens_are_write_only_and_blank_fields_keep_existing_secret(self):
        result=self.service.save(self.telegram())
        self.assertNotIn('TEST_TOKEN',json.dumps(result))
        result['telegram']['bot_token']=''
        self.service.save(result)
        self.assertEqual(self.service.config['telegram']['bot_token'],'12345:TEST_TOKEN')
        restarted=NotificationService(self.root/'notifications.json',self.reports)
        self.assertNotIn('TEST_TOKEN',json.dumps(restarted.public()))

    def test_telegram_payload_is_plain_text_and_duplicate_errors_are_muted(self):
        self.service.save(self.telegram())
        first=self.event()
        self.service.deliver(first)
        self.service.deliver(self.event())
        self.assertEqual(len(self.calls),1)
        self.assertEqual(self.calls[0][1]['chat_id'],'-100123456')
        self.assertNotIn('parse_mode',self.calls[0][1])
        statuses=[item['delivery']['telegram']['status'] for item in self.reports.snapshot()['entries']]
        self.assertEqual(statuses,['suppressed','sent'])

    def test_scan_issues_are_optin_and_failed_delivery_never_leaks_secret_url(self):
        self.service.save(self.telegram())
        self.service.enqueue(self.event(kind='scan'))
        self.assertTrue(self.service.events.empty())
        def broken(*_args):
            raise RuntimeError('https://api.telegram.org/bot12345:TEST_TOKEN/sendMessage')
        self.service.transport=broken
        self.service.deliver(self.event())
        serialized=json.dumps(self.reports.snapshot())
        self.assertNotIn('TEST_TOKEN',serialized)
        self.assertIn('failed',serialized)

    def test_signal_and_whatsapp_use_documented_shapes(self):
        config=copy.deepcopy(DEFAULTS)
        config['enabled']=True
        config['signal'].update(enabled=True,url='http://signal-api:8080',number='+48111111111',recipients='+48222222222')
        config['whatsapp'].update(enabled=True,access_token='WA_SECRET',phone_id='123456',recipients='+48333333333',template='dcc_alert')
        self.service.save(config)
        self.service.deliver(self.event())
        self.assertEqual(self.calls[0][0],'http://signal-api:8080/v2/send')
        self.assertEqual(self.calls[0][1]['recipients'],['+48222222222'])
        body=self.calls[1][1]
        self.assertEqual(body['type'],'template')
        self.assertEqual(body['template']['name'],'dcc_alert')
        self.assertEqual(len(body['template']['components'][0]['parameters']),1)
        self.assertNotIn('\n',body['template']['components'][0]['parameters'][0]['text'])
        self.assertNotIn('WA_SECRET',json.dumps(self.reports.snapshot()))

    def test_invalid_gateway_credentials_and_header_injection_are_rejected(self):
        config=copy.deepcopy(DEFAULTS)
        config['enabled']=True
        config['signal'].update(enabled=True,url='http://user:secret@signal-api',number='+48111111111',recipients='+48222222222')
        with self.assertRaises(ValueError):self.service.save(config)
        config['signal']['url']='http://signal-api'
        config['signal']['bearer_token']='token\nInjected: value'
        with self.assertRaises(ValueError):self.service.save(config)
        self.assertIsNone(NoRedirect().redirect_request(None,None,None,None,None,None))

    def test_test_message_requires_saved_enabled_channel_and_redaction_covers_tokens(self):
        with self.assertRaises(ValueError):self.service.test('telegram')
        self.service.save(self.telegram())
        self.service.test('telegram')
        self.assertEqual(len(self.calls),1)
        self.assertNotIn('sensitive',redact('token=sensitive https://user:sensitive@example.invalid/path'))

    def email(self):
        config=copy.deepcopy(DEFAULTS)
        config['enabled']=True
        config['email'].update(enabled=True,host='smtp.example.invalid',username='dcc',password=' SMTP_SECRET ',
                               sender='dcc@example.invalid',recipients='admin@example.invalid')
        return config

    def test_email_requires_verified_tls_before_authentication_and_hides_password(self):
        public=self.service.save(self.email())
        self.assertNotIn('SMTP_SECRET',json.dumps(public))
        smtp=MagicMock()
        smtp.send_message.return_value={}
        with patch('notifications.smtplib.SMTP') as factory:
            factory.return_value.__enter__.return_value=smtp
            self.service.test('email')
        factory.assert_called_once_with('smtp.example.invalid',587,timeout=10)
        self.assertEqual([call[0] for call in smtp.method_calls],['ehlo','starttls','ehlo','login','send_message'])
        self.assertTrue(smtp.starttls.call_args.kwargs['context'].check_hostname)
        smtp.login.assert_called_once_with('dcc',' SMTP_SECRET ')
        mail=smtp.send_message.call_args.args[0]
        self.assertEqual(mail['To'],'admin@example.invalid')
        self.assertIn('notification test',mail.get_content())
        self.assertEqual(self.calls,[])

    def test_email_implicit_tls_and_validation_rejects_plaintext_and_header_injection(self):
        config=self.email()
        config['email'].update(security='tls',port='465')
        self.service.save(config)
        with patch('notifications.smtplib.SMTP_SSL') as factory:
            factory.return_value.__enter__.return_value.send_message.return_value={}
            self.service.test('email')
            self.assertTrue(factory.call_args.kwargs['context'].check_hostname)
        for field,value in [('security','none'),('port','0'),('sender','a@example.invalid\nBcc: other@example.invalid')]:
            invalid=copy.deepcopy(config)
            invalid['email'][field]=value
            with self.assertRaises(ValueError):self.service.save(invalid)
        with self.assertRaises(ValueError):self.service.test([])


if __name__=='__main__':unittest.main()
