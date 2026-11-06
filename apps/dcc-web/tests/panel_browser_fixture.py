"""Manual browser smoke fixture. Never connects to Docker or real profiles.

Run two processes with --updater and without it. All persisted state lives in
temporary directories; passwords below are intentionally public test material.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading

APP=Path(__file__).resolve().parents[1]
ROOT=APP.parents[1]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--updater',action='store_true')
    parser.add_argument('--port',type=int,default=18879);parser.add_argument('--updater-port',type=int,default=18878)
    args=parser.parse_args()
    output=ROOT/'output/playwright';output.mkdir(parents=True,exist_ok=True)
    from werkzeug.serving import make_server
    with tempfile.TemporaryDirectory(prefix='dcc-panel-fixture-',dir=output) as directory:
        if args.updater:
            sys.path.insert(0,str(ROOT/'apps/container-updater'))
            os.environ['DCC_UPDATER_DATA']=directory
            spec=importlib.util.spec_from_file_location('dcc_updater_fixture_web',ROOT/'apps/container-updater/web.py')
            module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
            class Service:
                def infrastructure(self):return {'name':'Synthetic updater host','operating_system':'Test Linux','architecture':'amd64','docker_version':'fixture'}
                def scan(self,*args,**kwargs):return []
                def check_self_update(self,*args,**kwargs):return {'checked':True,'update_available':False,'supported':True,'message':'Synthetic fixture'}
            app=module.create_app(directory,service_factory=Service,print_credentials=False)
            from werkzeug.security import generate_password_hash
            (Path(directory)/'admin_password_hash').write_text(generate_password_hash('Fixture-updater-4433'),encoding='utf-8')
            server=make_server('127.0.0.1',args.updater_port,app,threaded=True)
        else:
            sys.path.insert(0,str(APP));sys.path.insert(0,str(APP/'tests'))
            from web import create_app
            from test_panel_proxy import PanelFixture,PanelBackend
            from http.server import ThreadingHTTPServer
            fixture=ThreadingHTTPServer(('127.0.0.1',0),PanelFixture)
            threading.Thread(target=fixture.serve_forever,daemon=True).start()
            PanelBackend.panel_entries=[
                {'ID':'a'*64,'State':'running','Names':'Live fixture','Image':'fixture/live','Ports':f'0.0.0.0:{fixture.server_port}->80/tcp'},
                {'ID':'b'*64,'State':'running','Names':'Updater fixture','Image':'fixture/updater','Ports':f'0.0.0.0:{args.updater_port}->8788/tcp'}]
            app=create_app({'DATA_DIR':directory,'ALLOWED_HOSTS':{'127.0.0.1','localhost'}},backend_factory=PanelBackend)
            state=app.extensions['dcc_state']
            state.save_profile('local',{'name':'Fixture Docker','kind':'local','panel_host':'127.0.0.1','permissions':['read']})
            app.extensions['dcc_domains'].save({'panel_proxy_enabled':True})
            client=app.test_client();client.get('/login')
            with client.session_transaction() as s:csrf=s['csrf']
            client.post('/setup',data={'username':'fixture-admin','password':'Fixture-pass-4433','csrf':csrf})
            links=client.get('/api/containers').json['containers']
            (output/'panel-fixture.json').write_text(json.dumps({'port':args.port,'panels':[f'/panels/view/local/{c["ID"]}/{c["PanelLinks"][0]["panel_id"]}' for c in links]}),encoding='utf-8')
            server=make_server('127.0.0.1',args.port,app,threaded=True)
        print('Synthetic panel fixture ready',flush=True)
        server.serve_forever()


if __name__=='__main__':main()
