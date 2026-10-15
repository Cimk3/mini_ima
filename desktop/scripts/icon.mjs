import { deflateSync } from 'node:zlib';
import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const size = 128;
const rows = Buffer.alloc((size * 4 + 1) * size);
for (let y=0; y<size; y++) for (let x=0; x<size; x++) {
  const offset=y*(size*4+1)+1+x*4;
  const inside=x>=8 && x<120 && y>=8 && y<120 &&
    (x>=28 && x<100 || y>=28 && y<100 || (x-(x<64?28:99))**2+(y-(y<64?28:99))**2<400);
  const mark=inside && y>=35 && y<94 && ((x>=32&&x<44)||(x>=84&&x<96)||
    (x>=43&&x<65&&Math.abs(y-(35+(x-43)*1.3))<8)||
    (x>=63&&x<85&&Math.abs(y-(63-(x-63)*1.3))<8));
  rows.set(mark?[255,255,255,255]:inside?[53,92,231,255]:[0,0,0,0],offset);
}
function crc(data) { let value=0xffffffff; for (const byte of data) { value^=byte; for(let i=0;i<8;i++) value=(value>>>1)^((value&1)?0xedb88320:0); } return (value^0xffffffff)>>>0; }
function chunk(name,data) { const type=Buffer.from(name); const out=Buffer.alloc(data.length+12); out.writeUInt32BE(data.length); type.copy(out,4); data.copy(out,8); out.writeUInt32BE(crc(Buffer.concat([type,data])),data.length+8); return out; }
const header=Buffer.alloc(13); header.writeUInt32BE(size); header.writeUInt32BE(size,4); header[8]=8; header[9]=6;
const png=Buffer.concat([Buffer.from([137,80,78,71,13,10,26,10]),chunk('IHDR',header),chunk('IDAT',deflateSync(rows)),chunk('IEND',Buffer.alloc(0))]);
const ico=Buffer.alloc(22); ico.writeUInt16LE(1,2); ico.writeUInt16LE(1,4); ico[6]=size; ico[7]=size; ico.writeUInt16LE(1,10); ico.writeUInt16LE(32,12); ico.writeUInt32LE(png.length,14); ico.writeUInt32LE(22,18);
const folder=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../src-tauri/icons');
mkdirSync(folder,{recursive:true}); writeFileSync(path.join(folder,'icon.ico'),Buffer.concat([ico,png])); writeFileSync(path.join(folder,'icon.png'),png);
