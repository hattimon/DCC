"""Explicit localhost-only synthetic server for browser QA; never a production entry point."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from web import create_app
from security import CAPABILITIES
from fixtures import FakeBackend
from werkzeug.security import generate_password_hash
from waitress import serve
from flask import request,jsonify
from security import admin

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8790)
    parser.add_argument('--data',required=True)
    parser.add_argument('--remote-access-fixture', action='store_true')
    args=parser.parse_args()
    app=create_app({'TESTING':True,'DATA_DIR':args.data},backend_factory=FakeBackend)
    app.extensions['dcc_remote_access'].available = args.remote_access_fixture
    state=app.extensions['dcc_state']
    state.execute('INSERT OR IGNORE INTO users VALUES(?,?,?,?)',('fixture-admin','review-admin',generate_password_hash('Review-only-password-4488'),'admin'))
    state.save_profile('local',{'name':'Local Docker · TEST FIXTURE','kind':'local','permissions':sorted(CAPABILITIES)})
    state.save_profile('mcp-ssh-qa',{'name':'SSH · MCP TEST FIXTURE','kind':'ssh','host':'192.0.2.99','username':'fixture','permissions':sorted(CAPABILITIES)})
    originals=list(FakeBackend.entries)
    # Explicit synthetic AI transport for browser QA; never installed in create_app.
    import ai_assistant,json
    def fixture_ai(connection,path,payload=None):
        if path=='/models':return {'data':[{'id':'fixture-coder'}]}
        answer={'configuration':{'name':'fixture-ai-app','image':'alpine:3.22','host_port':'8788','container_port':'80','extra':'--restart unless-stopped','command':'sleep 60','environment':{}},'explanation':'Synthetic AI proposal — test only'}
        if payload and payload.get('messages'):
            current=json.loads(payload['messages'][-1]['content']).get('current_configuration',{})
            for key in ('name','image'):
                if current.get(key):answer['configuration'][key]=current[key]
        return {'choices':[{'message':{'content':json.dumps(answer)}}]}
    ai_assistant.request_json=fixture_ai
    state.execute("INSERT OR REPLACE INTO ai_connections VALUES('default',?,?)",(json.dumps({'provider':'compatible','endpoint':'https://fixture.invalid/v1','model':'fixture-coder','enabled':True,'allow_local':False}),state.vault.encrypt(json.dumps({'api_key':''}).encode())))
    @app.post('/api/qa/scale')
    def scale():
        admin()
        count=max(3,min(1000,int(request.get_json().get('count',3))))
        FakeBackend.entries=originals if count==3 else [dict(originals[i%3],ID=format(i+1,'064x'),Names='fixture-container-'+str(i+1)) for i in range(count)]
        return jsonify(count=len(FakeBackend.entries))
    print('DCC Web QA fixture: localhost only, no real Docker mutations',flush=True)
    serve(app,host='127.0.0.1',port=args.port,threads=4)

if __name__=='__main__':main()
