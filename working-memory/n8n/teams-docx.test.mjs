import test from 'node:test';
import assert from 'node:assert/strict';
import { deflateRawSync } from 'node:zlib';
import { extractDocxText, normalizeTeamsTranscript } from './teams-docx.mjs';

function minimalDocx(xml) {
  const name = Buffer.from('word/document.xml');
  const raw = Buffer.from(xml);
  const data = deflateRawSync(raw);
  const local = Buffer.alloc(30);
  local.writeUInt32LE(0x04034b50, 0); local.writeUInt16LE(20, 4); local.writeUInt16LE(8, 8);
  local.writeUInt32LE(data.length, 18); local.writeUInt32LE(raw.length, 22); local.writeUInt16LE(name.length, 26);
  const central = Buffer.alloc(46);
  central.writeUInt32LE(0x02014b50, 0); central.writeUInt16LE(20, 4); central.writeUInt16LE(20, 6); central.writeUInt16LE(8, 10);
  central.writeUInt32LE(data.length, 20); central.writeUInt32LE(raw.length, 24); central.writeUInt16LE(name.length, 28);
  const eocd = Buffer.alloc(22);
  eocd.writeUInt32LE(0x06054b50, 0); eocd.writeUInt16LE(1, 8); eocd.writeUInt16LE(1, 10);
  eocd.writeUInt32LE(central.length + name.length, 12); eocd.writeUInt32LE(local.length + name.length + data.length, 16);
  return Buffer.concat([local, name, data, central, name, eocd]);
}

test('extracts Word paragraphs, tabs, breaks and XML entities', () => {
  const xml = '<?xml version="1.0"?><w:document xmlns:w="x"><w:body>' +
    '<w:p><w:r><w:t>Meeting &amp; Titel</w:t></w:r></w:p>' +
    '<w:p><w:r><w:t>A</w:t><w:tab/><w:t>B</w:t><w:br/><w:t>C</w:t></w:r></w:p>' +
    '</w:body></w:document>';
  assert.equal(extractDocxText(minimalDocx(xml)), 'Meeting & Titel\nA\tB\nC');
});

test('normalizes speakers and removes only duplicated Unknown echoes', () => {
  const input = [
    'Meeting Titel: Test',
    'Teilnehmer: Untertitel werden in, Komzin, Gleb, Haferkorn, Florian',
    'Datum: 08.09.2026',
    '[11:00:00] Untertitel werden in', 'angezeigt.',
    '[11:00:10] Komzin, Gleb', 'Ich aktualisiere den Bericht.',
    '[11:00:30] Unknown', 'Ich aktualisiere den Bericht.',
    '[11:00:40] Unknown', 'Unklare eigenständige Aussage.',
  ].join('\n');
  assert.equal(normalizeTeamsTranscript(input), [
    'Meeting Titel: Test',
    'Teilnehmer: Gleb Komzin; Florian Haferkorn',
    'Datum: 08.09.2026',
    '[11:00:10] Gleb Komzin: Ich aktualisiere den Bericht.',
    '[11:00:40] Unknown: Unklare eigenständige Aussage.', ''
  ].join('\n'));
});
