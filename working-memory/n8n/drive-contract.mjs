// Pure intake contracts shared by the n8n Code nodes and local tests.
// No model calls, no writes to Drive, no credentials in these functions.
export function prepareInventory(pages, { folderIds, selectedIds = null, maxFiles = 5000 }) {
  if (!Array.isArray(pages) || !pages.length) throw new Error('Keine vollständige Drive-Antwort');
  if (!Array.isArray(folderIds) || !folderIds.length) throw new Error('Zielordner fehlen');
  const ids = new Set(); const tokens = new Set(); const all = [];
  for (let i = 0; i < pages.length; i++) {
    const page = pages[i];
    if (!page || !Array.isArray(page.files) || page.incompleteSearch === true) throw new Error('Unvollständige Drive-Suche');
    const next = page.nextPageToken;
    if (next !== undefined && (typeof next !== 'string' || !next)) throw new Error('Ungültiger Seitencursor');
    if (i < pages.length - 1 && !next) throw new Error('Seitenkette unterbrochen');
    if (next && tokens.has(next)) throw new Error('Wiederholter Seitencursor');
    if (next) tokens.add(next);
    if (i === pages.length - 1 && next) throw new Error('Weitere Drive-Seite fehlt; kein Teilimport');
    for (const file of page.files) {
      if (!file || typeof file.id !== 'string' || !/^[A-Za-z0-9_-]+$/.test(file.id)) throw new Error('Ungültige Drive-ID');
      if (ids.has(file.id)) throw new Error('Doppelte Datei in wechselnder Seitenliste; Inventur wiederholen');
      ids.add(file.id);
      if (file.trashed !== false || !Array.isArray(file.parents) || !file.parents.some(id => folderIds.includes(id))) throw new Error('Datei außerhalb des geprüften Ordners');
      all.push({ ...file, intake_page_index: i });
    }
  }
  if (all.length > maxFiles) throw new Error('Inventur überschreitet das geprüfte Limit; kein Teilimport');
  if (selectedIds !== null && (!Array.isArray(selectedIds) || !selectedIds.length)) throw new Error('Keine konkrete Testauswahl');
  if (selectedIds && selectedIds.some(id => !ids.has(id))) throw new Error('Ausgewählte Originalquelle fehlt');
  const selected = all.filter(file => selectedIds === null || selectedIds.includes(file.id));
  const result = selected.map(file => {
    if (file.mimeType !== 'application/vnd.openxmlformats-officedocument.wordprocessingml.document') throw new Error('Nicht unterstütztes Originalformat: '+file.mimeType);
    if (typeof file.name !== 'string' || file.name.length > 1000) throw new Error('Dateiname fehlt oder ist zu lang');
    // Observed source convention, never substitute createdTime for the meeting date.
    const match = /^(\d{4}-\d{2}-\d{2})\s*(.+)$/.exec(file.name);
    if (!match) throw new Error('Meetingdatum im Dateinamen fehlt');
    const parsed = new Date(match[1]+'T12:00:00Z');
    if (Number.isNaN(parsed.valueOf()) || !parsed.toISOString().startsWith(match[1])) throw new Error('Ungültiges Meetingdatum');
    if (typeof file.version !== 'string' || !/^\d+$/.test(file.version) || typeof file.modifiedTime !== 'string' || Number.isNaN(Date.parse(file.modifiedTime))) throw new Error('Drive-Version oder Änderungszeit fehlt');
    const title = match[2].replace(/\.docx$/i, '');
    if (!title.trim()) throw new Error('Meetingtitel fehlt');
    return { ...file, source_id: 'drive:'+file.id, event_date: match[1], title };
  });
  return result.sort((a,b) => a.event_date.localeCompare(b.event_date) || a.id.localeCompare(b.id));
}

export function assembleOriginal(before, after, transcript, { maxCharacters = 140000 } = {}) {
  if (!Number.isSafeInteger(maxCharacters) || maxCharacters < 1 || maxCharacters > 4000000) throw new Error('Ungültiges Originallimit');
  for (const key of ['id','name','mimeType','version','modifiedTime']) {
    if (typeof before?.[key] !== 'string' || before[key] !== after?.[key]) throw new Error('Quelle wurde beim Lesen verändert: '+key);
  }
  if (after.trashed !== false || !Array.isArray(after.parents) || !after.parents.some(id => before.parents.includes(id))) throw new Error('Quelle wurde beim Lesen verschoben oder entfernt');
  if (typeof transcript !== 'string' || !transcript.trim()) throw new Error('Vollständiges Original fehlt');
  if (transcript.includes('\uFFFD') || /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(transcript)) throw new Error('Textdecodierung nicht verlustfrei bestätigt');
  if (transcript.length > maxCharacters) throw new Error('Original überschreitet das gewählte Leselimit; nicht gekürzt');
  if (!before.source_id || !before.event_date || !before.title) throw new Error('Geprüfte Quellenzuordnung fehlt');
  return {
    source_id: before.source_id, event_date: before.event_date, title: before.title, transcript,
    intake_status: 'read_verified_not_imported',
    drive_metadata: { id: before.id, name: before.name, mime_type: before.mimeType, version: before.version, modified_time: before.modifiedTime, parents: before.parents, md5_checksum: before.md5Checksum || null },
  };
}

// The server includes only originals safely archived and queued (or historical
// archive-only originals). A missing queue receipt must never be skipped.
export function selectUnarchived(files, manifest) {
  if (!Array.isArray(files) || !manifest || !Array.isArray(manifest.documents)) throw new Error('Geprüfter Archivstand fehlt; kein Import auf Verdacht');
  const known = new Map();
  for (const row of manifest.documents) {
    const m = row?.drive_metadata;
    if (!m || typeof row.source_id !== 'string' || row.source_id !== 'drive:'+m.id || typeof m.version !== 'string' || !Array.isArray(m.parents)) throw new Error('Archiv enthält unvollständige Quellenmetadaten');
    if (row.intake_blocked !== undefined && typeof row.intake_blocked !== 'boolean') throw new Error('Archiv enthält einen ungültigen Intake-Status');
    if (known.has(row.source_id)) throw new Error('Archiv liefert mehrere aktuelle Versionen');
    known.set(row.source_id,{metadata:m,intakeBlocked:row.intake_blocked === true});
  }
  return files.filter(file => {
    const prior = known.get(file.source_id);
    if (!prior) return true;
    if (prior.intakeBlocked) return false;
    const m=prior.metadata;
    return m.id !== file.id || m.name !== file.name || m.version !== file.version || m.modified_time !== file.modifiedTime || m.mime_type !== file.mimeType || (m.md5_checksum || null) !== (file.md5Checksum || null) || JSON.stringify([...m.parents].sort()) !== JSON.stringify([...file.parents].sort());
  });
}
