import { inflateRawSync } from 'node:zlib';

const DOC_XML = 'word/document.xml';

function decodeXml(value) {
  return value.replace(/&#(x[0-9a-f]+|\d+);|&(amp|lt|gt|quot|apos);/gi, (match, numeric, named) => {
    if (numeric) return String.fromCodePoint(Number.parseInt(numeric[0].toLowerCase() === 'x' ? numeric.slice(1) : numeric, numeric[0].toLowerCase() === 'x' ? 16 : 10));
    return { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'" }[named.toLowerCase()];
  });
}

function zipEntry(buffer, wanted) {
  let eocd = -1;
  for (let offset = buffer.length - 22; offset >= Math.max(0, buffer.length - 65557); offset--) {
    if (buffer.readUInt32LE(offset) === 0x06054b50) { eocd = offset; break; }
  }
  if (eocd < 0) throw new Error('DOCX-Zentralverzeichnis fehlt');
  const entries = buffer.readUInt16LE(eocd + 10);
  let offset = buffer.readUInt32LE(eocd + 16);
  for (let index = 0; index < entries; index++) {
    if (buffer.readUInt32LE(offset) !== 0x02014b50) throw new Error('Ungültiger DOCX-ZIP-Eintrag');
    const method = buffer.readUInt16LE(offset + 10);
    const compressedSize = buffer.readUInt32LE(offset + 20);
    const nameLength = buffer.readUInt16LE(offset + 28);
    const extraLength = buffer.readUInt16LE(offset + 30);
    const commentLength = buffer.readUInt16LE(offset + 32);
    const localOffset = buffer.readUInt32LE(offset + 42);
    const name = buffer.subarray(offset + 46, offset + 46 + nameLength).toString('utf8');
    if (name === wanted) {
      if (buffer.readUInt32LE(localOffset) !== 0x04034b50) throw new Error('Ungültiger lokaler DOCX-ZIP-Eintrag');
      const localNameLength = buffer.readUInt16LE(localOffset + 26);
      const localExtraLength = buffer.readUInt16LE(localOffset + 28);
      const start = localOffset + 30 + localNameLength + localExtraLength;
      const compressed = buffer.subarray(start, start + compressedSize);
      if (method === 0) return compressed;
      if (method === 8) return inflateRawSync(compressed);
      throw new Error('Nicht unterstützte DOCX-Kompression: ' + method);
    }
    offset += 46 + nameLength + extraLength + commentLength;
  }
  throw new Error('DOCX enthält kein ' + wanted);
}

export function extractDocxText(buffer) {
  if (!Buffer.isBuffer(buffer) || buffer.length < 22) throw new Error('Vollständige DOCX-Binärdatei fehlt');
  const xml = zipEntry(buffer, DOC_XML).toString('utf8');
  if (!xml.includes('<w:document')) throw new Error('Ungültiges Word-Dokument');
  const paragraphs = [];
  for (const match of xml.matchAll(/<w:p(?:\s[^>]*)?>([\s\S]*?)<\/w:p>/g)) {
    const body = match[1];
    let text = '';
    for (const run of body.matchAll(/<w:t(?:\s[^>]*)?>([\s\S]*?)<\/w:t>|<w:tab\b[^>]*\/>|<w:(?:br|cr)\b[^>]*\/>/g)) {
      if (run[1] !== undefined) text += decodeXml(run[1]);
      else if (run[0].startsWith('<w:tab')) text += '\t';
      else text += '\n';
    }
    text = text.replace(/\r\n?/g, '\n').trim();
    if (text) paragraphs.push(text);
  }
  if (!paragraphs.length) throw new Error('DOCX enthält keinen Transkripttext');
  return paragraphs.join('\n');
}

function speakerName(value) {
  const parts = value.split(',').map(part => part.trim()).filter(Boolean);
  return parts.length === 2 ? parts[1] + ' ' + parts[0] : value.trim();
}

function comparable(value) {
  return value.toLocaleLowerCase('de-DE').replace(/[^\p{L}\p{N}]+/gu, ' ').trim();
}

function normalizeParticipants(line) {
  const values = line.replace(/^Teilnehmer:\s*/i, '').split(',').map(value => value.trim()).filter(Boolean);
  const filtered = values.filter(value => !/^Untertitel werden in$/i.test(value));
  const names = [];
  for (let index = 0; index < filtered.length; index += 2) {
    const last = filtered[index];
    const first = filtered[index + 1];
    names.push(first ? first + ' ' + last : last);
  }
  return 'Teilnehmer: ' + names.join('; ');
}

export function normalizeTeamsTranscript(text) {
  if (typeof text !== 'string' || !text.trim()) throw new Error('Teams-Transkripttext fehlt');
  const lines = text.split(/\n+/).map(line => line.replace(/\u00a0/g, ' ').trim()).filter(Boolean);
  const output = [];
  const recentNamed = [];
  for (let index = 0; index < lines.length; index++) {
    const header = /^\[(\d{2}:\d{2}:\d{2})\]\s+(.+)$/.exec(lines[index]);
    if (!header) {
      output.push(/^Teilnehmer:/i.test(lines[index]) ? normalizeParticipants(lines[index]) : lines[index]);
      continue;
    }
    const statement = lines[index + 1] && !/^\[\d{2}:\d{2}:\d{2}\]\s+/.test(lines[index + 1]) ? lines[++index] : '';
    const speaker = speakerName(header[2]);
    if (/^Untertitel werden in$/i.test(speaker) && /^angezeigt\.?$/i.test(statement)) continue;
    const key = comparable(statement);
    if (/^Unknown$/i.test(speaker) && key && recentNamed.includes(key)) continue;
    if (!/^Unknown$/i.test(speaker) && key) {
      recentNamed.push(key);
      if (recentNamed.length > 24) recentNamed.shift();
    }
    output.push('[' + header[1] + '] ' + speaker + (statement ? ': ' + statement : ''));
  }
  const normalized = output.join('\n').trim();
  if (!normalized) throw new Error('Teams-Transkript ist nach Normalisierung leer');
  return normalized + '\n';
}
