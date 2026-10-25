// Runs only against a read-only source or an isolated application test copy.
import { DatabaseSync, backup } from 'node:sqlite';
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync, lstatSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';

const [mode, source, destination] = process.argv.slice(2);
const hash = value => createHash('sha256').update(value).digest('hex');
const quote = value => '"' + value.replaceAll('"', '""') + '"';
const regular = path => { if (!lstatSync(path).isFile() || lstatSync(path).isSymbolicLink()) throw Error('unsafe_data_file'); return path; };
function fingerprint(root) {
  const key = readFileSync(regular(resolve(root, 'credentials.key')));
  if (key.length !== 32) throw Error('invalid_credentials_key');
  const db = new DatabaseSync(regular(resolve(root, 'cinema.sqlite')), { readOnly: true });
  try {
    const integrity = Object.values(db.prepare('PRAGMA integrity_check').get());
    if (integrity.length !== 1 || integrity[0] !== 'ok' || db.prepare('PRAGMA foreign_key_check').all().length) throw Error('invalid_sqlite_backup');
    const schema = db.prepare("SELECT type,name,tbl_name,sql FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name").all();
    const tables = {};
    for (const table of schema.filter(row => row.type === 'table')) {
      const columns = db.prepare('PRAGMA table_info(' + quote(table.name) + ')').all();
      const order = columns.filter(c => c.pk).sort((a,b)=>a.pk-b.pk).map(c=>quote(c.name));
      const sum = createHash('sha256'); let count=0;
      const statement = db.prepare('SELECT * FROM '+quote(table.name)+' ORDER BY '+(order.length?order:columns.map(c=>quote(c.name))).join(','));
      for (const row of statement.iterate()) { sum.update(JSON.stringify(row, (_key,value)=>typeof value==='bigint'?String(value):value)+'\n'); count++; }
      tables[table.name] = { count, sha256: sum.digest('hex') };
    }
    if (!tables.users || !tables.sources || !tables.settings) throw Error('cinema_schema_missing');
    return { schema_sha256: hash(JSON.stringify(schema)), key_sha256: hash(key), tables, verified: true };
  } finally { db.close(); }
}
try {
  if (mode === 'snapshot') {
    const dbPath = regular(resolve(source, 'cinema.sqlite'));
    const keyPath = regular(resolve(source, 'credentials.key'));
    const beforeKey = readFileSync(keyPath);
    if (beforeKey.length !== 32 || existsSync(resolve(destination, 'cinema.sqlite'))) throw Error('backup_destination_not_empty');
    const db = new DatabaseSync(dbPath, { readOnly: true });
    const deadline = Date.now()+60000;
    try { await backup(db, resolve(destination, 'cinema.sqlite'), {rate:128,progress:()=>{if(Date.now()>deadline)throw Error('backup_timeout');}}); }
    finally { db.close(); }
    const afterKey = readFileSync(regular(keyPath));
    if (!beforeKey.equals(afterKey)) throw Error('credentials_key_changed');
    writeFileSync(resolve(destination, 'credentials.key'), beforeKey, {mode:0o600,flag:'wx'});
    const result = fingerprint(destination);
    writeFileSync(resolve(destination, 'metadata.json'), JSON.stringify(result,null,2), {mode:0o600,flag:'wx'});
    console.log(JSON.stringify(result));
  } else if (mode === 'inspect') {
    console.log(JSON.stringify(fingerprint(source)));
  } else throw Error('unsupported_mode');
} catch (_error) {
  // SQLite errors can include private records. Publish only a stable code.
  console.error('cinema_data_verification_failed'); process.exitCode=1;
}
