"""Synthetic engine for isolated tests. Production never selects this adapter."""
import copy
import json

from engine import EngineError
from ports import container_revision


class FakeBackend:
    commands=[]
    unavailable=False
    entries=[
        {"RestartPolicy":"unless-stopped","ID":"a"*64,"Names":"dcc-container-updater","Image":"ghcr.io/hattimon/dcc-container-updater:latest","State":"running","Status":"Up 3 days (healthy)","Ports":"0.0.0.0:8788->8788/tcp, [::]:8788->8788/tcp","Labels":"com.hattimon.dcc-updater=true,com.docker.compose.project=review","Networks":"bridge,review_default"},
        {"RestartPolicy":"no","ID":"b"*64,"Names":"jellyfin","Image":"linuxserver/jellyfin:latest","State":"running","Status":"Up 3 days","Ports":"0.0.0.0:8096->8096/tcp"},
        {"RestartPolicy":"always","ID":"c"*64,"Names":"redis","Image":"redis:7","State":"running","Status":"Up 2 days","Ports":"0.0.0.0:6379->6379/tcp"},
    ]
    def __init__(self,profile,**kwargs):
        self.profile=profile
    def info(self):
        if self.unavailable:raise EngineError("Docker unavailable")
        return {"Name":"local-review","Architecture":"x86_64","NCPU":8,"MemTotal":16*1024**3,"ServerVersion":"29.6.1","OperatingSystem":"Linux (isolated test fixture)","Driver":"overlay2","Images":12}
    def containers(self):
        if self.unavailable:raise EngineError("Docker unavailable")
        return copy.deepcopy(self.entries)
    def container_revision(self):
        return container_revision(self.containers())
    def inspect(self,target):
        entry=next((c for c in self.entries if c["ID"]==target or c["Names"]==target),self.entries[0])
        return {"Id":entry["ID"],"Name":"/"+entry["Names"],"Config":{"Image":entry["Image"],"Env":["APP_PASSWORD=fixture-secret","TZ=Europe/Warsaw"],"Labels":{}},"State":{"Running":entry["State"]=="running","Health":{"Status":"healthy"}},"Mounts":[{"Type":"volume","Name":"protected-data","Destination":"/data"}],"HostConfig":{"RestartPolicy":{"Name":"unless-stopped"}}}
    def logs(self,target,tail=200,since=None):
        return "2026-11-01T12:00:00Z INFO Server ready\n2026-11-01T12:00:01Z WARN Retry request\n2026-11-01T12:00:02Z ERROR Example failure\n2026-11-01T12:00:03Z password=fixture-secret\n"
    def stats(self):
        return [{"ID":v["ID"],"Name":v["Names"],"CPUPerc":str([.6,2.1,.3][i%3])+"%","MemUsage":str([72,892,48][i%3])+"MiB / 16GiB","MemPerc":str([.4,5.4,.3][i%3])+"%","NetIO":"12.4MB / 4.2MB","BlockIO":"8MB / 2MB","PIDs":"12"} for i,v in enumerate(self.entries)]
    def resources(self,kind):
        values={"images":[{"Repository":"alpine","Tag":"3.22","ID":"sha256:"+"d"*64,"CreatedSince":"2 days ago","Size":"8MB"}],"volumes":[{"Name":"protected-data","Driver":"local","Scope":"local"}],"networks":[{"Name":"bridge","Driver":"bridge","Scope":"local","ID":"1"*12}]}
        return values[kind]
    def action(self,target,action):
        self.commands.append([action,target])
        return target
    def run(self,args,**kwargs):
        self.commands.append(list(args))
        return "fixture-result"
    def stream(self,args,on_output,**kwargs):
        self.commands.append(list(args))
        on_output('Pulling test image: 1/1 layers complete\n')
    def json(self,args,**kwargs):
        self.commands.append(list(args))
        if args[:2]==["compose","ls"]:
            return [{"Name":"review-project","Status":"running(1)","ConfigFiles":"/srv/review/compose.yaml"}]
        if args[:2]==["image","inspect"]:
            raise EngineError("Build first")
        if len(args)>1 and args[1]=="inspect":
            return [{"Name":args[-1],"Driver":"local"}]
        return []
    def compose(self,project,action="ps"):
        self.commands.append(["compose",action,project["name"]])
        return json.dumps({"services":{"web":{"image":"alpine:3.22"}}}) if action=="config" else "review-project: operation completed"
