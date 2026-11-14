// Dependency-free ZIP packaging for the local demo. Explicit source-only allowlist.
import { readdir, readFile, mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const source = path.join(root, 'desktop');
const output = path.join(process.env.SIGNALSPEAK_DATA_DIR || path.join(root, 'data'), 'releases');
await mkdir(output, { recursive: true });
const table = Array.from({ length: 256 }, (_, i) => { let n = i; for (let j = 0; j < 8; j++) n = (n >>> 1) ^ ((n & 1) ? 0xedb88320 : 0); return n >>> 0; });
function crc32(bytes) { let crc = 0xffffffff; for (const b of bytes) crc = (crc >>> 8) ^ table[(crc ^ b) & 255]; return (crc ^ 0xffffffff) >>> 0; }
const names = (await readdir(source)).filter(name => name !== 'stub_server.py' && (name.endsWith('.py') || name.endsWith('.pyw') || name === 'Start SignalSpeak.vbs' || ['requirements.txt', 'README.md'].includes(name))).sort();
const local = [], central = []; let offset = 0;
for (const name of names) {
  const data = await readFile(path.join(source, name)), filename = Buffer.from(name), crc = crc32(data);
  const header = Buffer.alloc(30);
  header.writeUInt32LE(0x04034b50, 0); header.writeUInt16LE(20, 4); header.writeUInt16LE(0x800, 6); header.writeUInt16LE(33, 12);
  header.writeUInt32LE(crc, 14); header.writeUInt32LE(data.length, 18); header.writeUInt32LE(data.length, 22); header.writeUInt16LE(filename.length, 26);
  local.push(header, filename, data);
  const entry = Buffer.alloc(46);
  entry.writeUInt32LE(0x02014b50, 0); entry.writeUInt16LE(20, 4); entry.writeUInt16LE(20, 6); entry.writeUInt16LE(0x800, 8); entry.writeUInt16LE(33, 14);
  entry.writeUInt32LE(crc, 16); entry.writeUInt32LE(data.length, 20); entry.writeUInt32LE(data.length, 24); entry.writeUInt16LE(filename.length, 28); entry.writeUInt32LE(offset, 42);
  central.push(entry, filename); offset += header.length + filename.length + data.length;
}
const directory = Buffer.concat(central), end = Buffer.alloc(22);
end.writeUInt32LE(0x06054b50, 0); end.writeUInt16LE(names.length, 8); end.writeUInt16LE(names.length, 10); end.writeUInt32LE(directory.length, 12); end.writeUInt32LE(offset, 16);
await writeFile(path.join(output, 'SignalSpeak-desktop-source.zip'), Buffer.concat([...local, directory, end]));
console.log(`Packaged ${names.length} source files. No device credentials, logs, model or settings included.`);
