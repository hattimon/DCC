"""Docker SDK over the same verified SSH identity as the CLI profile."""
import shlex
import paramiko
import docker
from profile_ssh import configure_client, connection_options
from docker.transport.sshconn import SSHHTTPAdapter,SSHConnection,SSHConnectionPool


class ProfileConnection(SSHConnection):
    def __init__(self,*args,cli='docker',**kwargs):
        super().__init__(*args,**kwargs)
        self.cli=cli

    def connect(self):
        channel=self.ssh_transport.open_session(timeout=self.timeout)
        channel.settimeout(self.timeout)
        channel.exec_command(shlex.join([self.cli,'system','dial-stdio']))
        self.sock=channel


class ProfilePool(SSHConnectionPool):
    def __init__(self,*args,cli='docker',**kwargs):
        self.cli=cli
        super().__init__(*args,**kwargs)

    def _new_conn(self):
        return ProfileConnection(self.ssh_transport,self.timeout,self.ssh_host,cli=self.cli)


class VerifiedProfileAdapter(SSHHTTPAdapter):
    def __init__(self,profile):
        self.profile=profile
        super().__init__('ssh://profile',timeout=30,max_pool_size=4)

    def _create_paramiko_client(self,base_url):
        p=self.profile;secret=p.get('credentials',{})
        self.ssh_client=paramiko.SSHClient()
        configure_client(self.ssh_client,p)
        self.ssh_params=connection_options(p)

    def get_connection(self,url,proxies=None):
        with self.pools.lock:
            pool=self.pools.get(url)
            if pool:return pool
            if not self.ssh_client.get_transport():self._connect()
            cli=self.profile.get('cli') or ('balena' if self.profile['kind']=='balena' else 'docker')
            if cli not in {'docker','balena','balena-engine'}:raise ValueError('Unsupported engine CLI')
            pool=ProfilePool(ssh_client=self.ssh_client,timeout=self.timeout,maxsize=self.max_pool_size,host=self.ssh_host,cli=cli)
            self.pools[url]=pool
            return pool


def ssh_docker_client(profile):
    # An explicit initial version avoids contacting the placeholder HTTP address.
    # Server negotiation occurs only after installing the verified SSH adapter.
    client=docker.DockerClient(base_url='http://127.0.0.1',version='1.44',timeout=30)
    try:
        adapter=VerifiedProfileAdapter(profile)
        api=client.api
        api._custom_adapter=adapter
        api.mount('http+docker://ssh',adapter)
        api._unmount('http://','https://')
        api.base_url='http+docker://ssh'
        api._version=api._retrieve_server_version()
        return client
    except Exception:
        client.close()
        raise
