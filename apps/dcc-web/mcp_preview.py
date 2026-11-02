"""Provider-neutral MCP Preview. Read-only stdio is implemented; HTTP is not exposed."""
import hashlib
import json
import os
import re
from pathlib import Path
import secrets
import sys
import time

from flask import abort, g, jsonify, request

from engine import DockerBackend
from client_adapters import export_client
from security import admin, authorize, redact

CLIENTS = ["OpenAI Codex","Claude Desktop","Claude Code","Cursor","Windsurf","VS Code / GitHub Copilot","Generic MCP"]
TOOLS = {
    "list_containers": "List containers in an authorized Docker profile",
    "inspect_container": "Inspect a container, with secret values redacted",
    "container_logs": "Read a bounded range of container logs",
    "container_stats": "Read current CPU, memory, network and I/O",
    "list_images": "List Docker images",
    "list_volumes": "List Docker volumes",
    "list_networks": "List Docker networks",
}


class MCPService:
    def __init__(self,state,token,backend_factory=DockerBackend):
        self.state,self.digest,self.factory=state,hashlib.sha256(token.encode()).hexdigest(),backend_factory
        self.negotiated = False
        self.initialized = False

    def grant(self):
        rows=self.state.rows("SELECT * FROM grants WHERE token=? AND revoked=0",(self.digest,))
        if not rows:
            raise PermissionError("MCP access is invalid or revoked")
        value=json.loads(rows[0]["data"])
        if value.get("expires") is not None and value["expires"]<time.time():
            raise PermissionError("MCP access has expired")
        return value

    def call(self,name,arguments):
        grant=self.grant()
        if name not in TOOLS or name not in grant["tools"] or arguments.get("profile") not in grant["profiles"]:
            raise PermissionError("Tool or profile is outside this grant")
        profile=self.state.profile(arguments["profile"],private=True)
        if "read" not in profile.get("permissions",["read"]):
            raise PermissionError("Profile permission was revoked")
        engine=self.factory(profile)
        target=str(arguments.get("container", ""))
        if name in {"inspect_container","container_logs"} and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,200}",target):
            raise ValueError("Invalid container identifier")
        if name=="list_containers":
            result=engine.containers()
        elif name=="inspect_container":
            result=engine.inspect(target)
        elif name=="container_logs":
            result=engine.logs(target,max(1,min(int(arguments.get("tail",200)),2000)))
        elif name=="container_stats":
            result=engine.stats()
        else:
            result=engine.resources(name.removeprefix("list_"))
        self.state.audit("mcp:"+grant["name"],name,profile["id"],200)
        return {"content":[{"type":"text","text":json.dumps(redact(result),ensure_ascii=False)}],"isError":False}

    def handle(self,message):
        method=message.get("method")
        if "id" not in message:
            if method=="notifications/initialized" and self.negotiated:
                self.grant()
                self.initialized = True
            return None
        self.grant()
        params=message.get("params",{})
        if method=="initialize":
            if self.negotiated:
                raise ValueError("Already initialized")
            version=params.get("protocolVersion")
            if version not in {"2024-11-05","2025-03-26","2025-06-18","2025-11-25"}:
                version="2025-11-25"
            result={"protocolVersion":version,"capabilities":{"tools":{"listChanged":False}},"serverInfo":{"name":"dcc-web-readonly-preview","version":"0.1.4"},"instructions":"Read-only Preview. Writes and HTTP transport are not available."}
            self.negotiated = True
        elif method=="ping":
            result={}
        elif not self.initialized:
            return {"jsonrpc":"2.0","id":message["id"],"error":{"code":-32002,"message":"Complete initialize and notifications/initialized first"}}
        elif method=="tools/list":
            allowed=self.grant()["tools"]
            result={"tools":[{"name":name,"description":TOOLS[name],"inputSchema":{"type":"object","properties":{"profile":{"type":"string"},"container":{"type":"string"},"tail":{"type":"integer","minimum":1,"maximum":2000}},"required":["profile",*(["container"] if name in {"inspect_container","container_logs"} else [])],"additionalProperties":False},"annotations":{"readOnlyHint":True,"destructiveHint":False}} for name in allowed if name in TOOLS]}
        elif method=="tools/call":
            result=self.call(params.get("name"),params.get("arguments",{}))
        else:
            return {"jsonrpc":"2.0","id":message["id"],"error":{"code":-32601,"message":"Method is not implemented in this Preview"}}
        return {"jsonrpc":"2.0","id":message["id"],"result":result}


def register_mcp(app,state,profile_lookup):
    @app.route("/api/mcp/grants",methods=["GET","POST"])
    def grants():
        admin()
        if request.method=="GET":
            return jsonify(clients=CLIENTS,tools=TOOLS,grants=[dict(id=row["id"],revoked=bool(row["revoked"]),**json.loads(row["data"])) for row in state.rows("SELECT id,data,revoked FROM grants")],transports={"stdio":"read-only preview","streamable_http":"planned, disabled"})
        data=request.get_json()
        profiles=data.get("profiles",[])
        tools=data.get("tools",list(TOOLS))
        if not isinstance(profiles,list) or not profiles or len(profiles)>100 or not isinstance(tools,list) or set(tools)-set(TOOLS):
            abort(400,"Choose existing profiles and read-only tools")
        for profile_id in profiles:
            profile_lookup(profile_id)
        token=secrets.token_urlsafe(40)
        ident=secrets.token_hex(12)
        unlimited=data.get('unlimited') is True
        days=int(data.get('days',30))
        if not unlimited and not 1<=days<=1_000_000:
            abort(400,'Validity must be between 1 and 1000000 days, or select No expiry')
        metadata={"name":str(data.get("name","MCP client"))[:80],"client":data.get("client","Generic MCP"),"profiles":profiles,"tools":tools,"permissions":["read"],"created":time.time(),"expires":None if unlimited else time.time()+86400*days}
        state.execute("INSERT INTO grants(id,token,data) VALUES(?,?,?)",(ident,hashlib.sha256(token.encode()).hexdigest(),json.dumps(metadata)))
        return jsonify(id=ident,token=token,notice="Shown once. Store this token in the client's environment, not its configuration file."),201

    @app.delete("/api/mcp/grants/<grant_id>")
    def revoke(grant_id):
        admin()
        state.execute("UPDATE grants SET revoked=1 WHERE id=?",(grant_id,))
        return jsonify(ok=True)

    @app.get("/api/mcp/config/<grant_id>")
    def export(grant_id):
        admin()
        rows=state.rows("SELECT data FROM grants WHERE id=? AND revoked=0",(grant_id,))
        if not rows:
            abort(404)
        metadata=json.loads(rows[0]["data"])
        return jsonify(export_client(metadata["client"],sys.executable,[str(Path(__file__).with_name("web.py")),"--data",str(state.directory),"--mcp-stdio"]))


def stdio(state,input_stream=None,output_stream=None):
    service=MCPService(state,os.environ.get("DCC_MCP_TOKEN",""))
    input_stream,output_stream=input_stream or sys.stdin,output_stream or sys.stdout
    for stream in (input_stream,output_stream):
        if hasattr(stream,"reconfigure"):
            stream.reconfigure(encoding="utf-8")
    while True:
        line=input_stream.readline(1_000_001)
        if not line:
            break
        message={}
        try:
            if len(line)>1_000_000:
                raise ValueError("Request too large")
            message=json.loads(line)
            if not isinstance(message,dict) or message.get("jsonrpc")!="2.0":
                raise ValueError("Invalid JSON-RPC request")
            response=service.handle(message)
        except PermissionError:
            response={"jsonrpc":"2.0","id":message.get("id") if isinstance(message,dict) else None,"error":{"code":-32001,"message":"MCP access denied"}}
        except Exception:
            response={"jsonrpc":"2.0","id":message.get("id") if isinstance(message,dict) else None,"error":{"code":-32602,"message":"Invalid request or unavailable Docker resource"}}
        if response is not None:
            output_stream.write(json.dumps(response,ensure_ascii=False)+"\n")
            output_stream.flush()
