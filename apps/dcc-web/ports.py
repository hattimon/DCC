"""Published Docker endpoints and advisory conflict checks, without scanning panels."""
import ipaddress
import hashlib
import json
import re
from urllib.parse import urlsplit
from dcc_catalog import image_repository

WEB_PORTS={80,443,3000,3001,5000,5001,5006,8000,8001,8080,8081,8082,8086,8090,8096,8100,8123,8443,8788,8789,8888,9000,9001,9090,9443}


def container_revision(containers):
    fields=("ID", "Names", "Image", "State", "Ports", "Networks", "Labels", "CreatedAt")
    values=sorted(({key:entry.get(key) for key in fields} for entry in containers), key=lambda value:str(value.get("ID") or ""))
    payload=json.dumps(values,sort_keys=True,ensure_ascii=False,separators=(",",":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def parse_bindings(lines):
    if not isinstance(lines,str) or len(lines)>10000:raise ValueError('Invalid port configuration')
    result={}
    for line in lines.splitlines():
        if not line.strip():continue
        match=re.fullmatch(r'(?:(\[[^]]+\]|[\d.]+):)?(\d{1,5}):(\d{1,5})(/(tcp|udp))?',line.strip())
        if not match or not 1<=int(match[2])<=65535 or not 1<=int(match[3])<=65535:raise ValueError('Use [IP:]HOST:CONTAINER[/tcp|/udp] per line')
        host=(match[1] or '').strip('[]')
        if host:ipaddress.ip_address(host)
        key=match[3]+'/'+(match[5] or 'tcp')
        result.setdefault(key,[]).append({'HostIp':host,'HostPort':match[2]})
    return result


def published_ports(text):
    result=[]
    pattern=r'(?P<ip>\[[^]]+\]|[\w.*:]+):(?P<host>\d+)(?:-(?P<end>\d+))?->(?P<container>\d+)(?:-\d+)?/(?P<protocol>tcp|udp)'
    for match in re.finditer(pattern,str(text or '')):
        start,end=int(match['host']),int(match['end'] or match['host'])
        for offset,port in enumerate(range(start,min(end,start+255)+1)):
            value={'host_ip':match['ip'].strip('[]'),'host_port':port,'container_port':int(match['container'])+offset,'protocol':match['protocol']}
            if value not in result:result.append(value)
    return result


def profile_host(profile,fallback='localhost'):
    if profile.get('panel_host'):return profile['panel_host']
    if profile.get('kind') in {'ssh','balena'}:return profile['host']
    endpoint=profile.get('endpoint','')
    return urlsplit(endpoint).hostname or fallback


def enrich_containers(containers,profile,fallback='localhost',host_panels=None):
    host=profile_host(profile,fallback)
    for entry in containers:
        ports=published_ports(entry.get('Ports'))
        inferred=[]
        networks=entry.get('Networks') or []
        if isinstance(networks,str):networks=networks.split(',')
        native=(host_panels or {}).get(image_repository(entry.get('Image')))
        if 'host' in networks and native:
            inferred=[{'host_ip':'0.0.0.0','host_port':int(native),'container_port':int(native),'protocol':'tcp'}]
        entry['HostNetworkPorts']=[v['host_port'] for v in inferred]
        links={}
        for port in [*ports,*inferred]:
            address=port['host_ip']
            remote=profile.get('kind') in {'ssh','balena','tcp'}
            loopback=address in {'127.0.0.1','::1','localhost'}
            if port['protocol']!='tcp' or (remote and loopback):continue
            target=host if address in {'0.0.0.0','::','*','127.0.0.1','::1','localhost'} else address
            if not re.fullmatch(r'[A-Za-z0-9.\-:_]+',target):continue
            try:
                if ipaddress.ip_address(target).version==6:target='['+target+']'
            except ValueError:pass
            scheme='https' if port['container_port'] in {443,8443,9443} or port['host_port'] in {443,8443,9443} else 'http'
            # TCP links are inferred from published ports; no claim that the service is HTTP.
            url=f'{scheme}://{target}:{port["host_port"]}'
            likely=port['container_port'] in WEB_PORTS or port['host_port'] in WEB_PORTS
            if url in links:
                links[url]['likely_panel'] |= likely
            else:
                links[url]={'url':url,'label':f'{target}:{port["host_port"]}','likely_panel':likely}
        entry['PublishedPorts']=ports
        entry['PanelLinks']=list(links.values())
    return containers


def inventory(engine,requested=(),start=8000):
    occupied={}
    for entry in engine.containers():
        for port in published_ports(entry.get('Ports')):
            occupied[(port['host_port'],port['protocol'])]=entry.get('Names','Docker')
    requested=[int(value) for value in requested if str(value).isdigit() and 1<=int(value)<=65535]
    proposed={}
    reserved=set(occupied)
    for requested_port in requested or [start]:
        candidate=requested_port
        while (candidate,'tcp') in reserved and candidate<65535:candidate+=1
        if (candidate,'tcp') in reserved:raise ValueError('No free port in the selected range')
        proposed[str(requested_port)]=candidate
        reserved.add((candidate,'tcp'))
    return {'occupied':[{'port':port,'protocol':protocol,'container':owner} for (port,protocol),owner in sorted(occupied.items())], 'suggested':proposed,'advisory':True}
