// Browser-side suggestions only; the server validates every selected file again.
export function sshFileKind(name,text){
 const value=String(text).trimStart();
 if(name==='known_hosts'&&/\S+\s+(ssh-|ecdsa-|sk-)/m.test(value))return 'known_hosts';
 if(/^-----BEGIN (OPENSSH |RSA |EC |ENCRYPTED )?PRIVATE KEY-----/.test(value))return 'private key';
 if(/^(ssh-|ecdsa-|sk-)\S+\s+[A-Za-z0-9+/=]+/.test(value))return 'public key';
 return null;
}
