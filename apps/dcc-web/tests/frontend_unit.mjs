import{groupContainers,primaryNetwork}from'../static/container_data.js';
import assert from 'node:assert/strict';
import{html,t,setLanguage,getLanguage,literal}from'../static/i18n.js';
import{sshFileKind}from'../static/ssh_files.js';
assert.equal(sshFileKind('key.pem','-----BEGIN OPENSSH PRIVATE KEY-----'),'private key');
assert.equal(sshFileKind('no_extension','-----BEGIN ENCRYPTED PRIVATE KEY-----'),'private key');
assert.equal(sshFileKind('renamed.pub','-----BEGIN RSA PRIVATE KEY-----'),'private key');
assert.equal(sshFileKind('public','ssh-ed25519 AAAA test'),'public key');
assert.equal(sshFileKind('config','Host *\n  ProxyCommand anything'),null);
setLanguage('EN');
assert.equal(t('Kontenery'),'Containers');
assert.equal(literal('<button>Szczegóły</button>'),'<button>Details</button>');
const data='Kontenery <script>user data</script>';
assert.equal(html`<h1>Kontenery</h1><p>${data}</p>`,`<h1>Containers</h1><p>${data}</p>`);
assert.equal(html`<select><option>Bez limitu czasowego</option></select>`,'<select><option>No expiry</option></select>');
setLanguage('PL');
assert.equal(getLanguage(),'PL');
assert.equal(t('Profile'),'Profile');
assert.equal(html`<h1>Kontenery</h1>`,'<h1>Kontenery</h1>');
assert.match(t('Configure and enable the AI connection first'),/skonfiguruj/);
console.log('Frontend localization checks passed');

const entries=[
 {ID:'1',Names:'web-2',Labels:'com.docker.compose.project=shop',Networks:'bridge,shop_default,public'},
 {ID:'2',Names:'db',Labels:{'com.docker.compose.project':'shop'},Networks:'shop_default'},
 {ID:'3',Names:'standalone',Networks:'bridge,custom'},
 {ID:'4',Names:'isolated',Networks:''}
];
assert.equal(primaryNetwork(entries[0]),'shop_default');
assert.equal(primaryNetwork(entries[2]),'custom');
assert.deepEqual(groupContainers(entries,'project').map(g=>[g.key,g.values.length]),[['shop',2],['__standalone__',2]]);
const networks=groupContainers(entries,'network');
assert.deepEqual(networks.map(g=>g.key),['custom','shop_default','__no_network__']);
assert.equal(new Set(networks.flatMap(g=>g.values.map(v=>v.ID))).size,entries.length);
assert.equal(networks.flatMap(g=>g.values).length,entries.length);
assert.equal(groupContainers(entries,'none')[0].values,entries);
setLanguage('EN');
assert.equal(t('Kliknij, aby skopiować pełną ścieżkę obrazu'),'Click to copy the full image reference');
assert.equal(t('Projekty'),'Projects');
setLanguage('PL');
assert.match(t('This profile does not permit the operation: containers.write'),/containers\.write/);
console.log('Container grouping and operator captions passed');
