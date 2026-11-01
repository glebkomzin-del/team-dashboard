// Guard a published receipt against freshly read Drive metadata before PATCH.
export function driveV2Metadata(body) {
  if (!body || typeof body.labels?.trashed !== 'boolean' ||
      !Array.isArray(body.parents) || body.parents.some(p => typeof p.id !== 'string')) {
    throw new Error('Incomplete Drive v2 metadata');
  }
  return {...body, parents:body.parents.map(p=>p.id), trashed:body.labels.trashed};
}

export function plannedMove(receipt, current, etag) {
  if (receipt?.ready_to_move !== true) return null;
  if (!current || current.id !== receipt.file_id || current.trashed) throw new Error('File identity changed');
  if (!Array.isArray(current.parents)) throw new Error('Missing current parents');
  if (typeof current.md5Checksum !== 'string' || current.md5Checksum.toLowerCase() !== receipt.md5_checksum) {
    throw new Error('File content changed after processing');
  }
  if (current.parents.includes(receipt.destination_folder)) return null;
  // Drive also increments version for metadata-only edits. The published binary
  // checksum identifies the processed content; the fresh ETag protects the PATCH.
  if (!/^\d+$/.test(String(current.version)) || !/^\d+$/.test(String(receipt.version)) ||
      BigInt(current.version) < BigInt(receipt.version)) throw new Error('Invalid or older file version');
  const remove = receipt.source_folders.filter(id => current.parents.includes(id));
  if (!remove.length) throw new Error('File left the managed Inbox');
  if (typeof etag !== 'string' || !etag.trim()) throw new Error('Missing conditional-write ETag');
  return {file_id: current.id, addParents: receipt.destination_folder,
    removeParents: remove.join(','), ifMatch: etag, md5_checksum:receipt.md5_checksum};
}

export function verifyMove(plan, body) {
  if (body?.error) throw new Error('Google hat das Verschieben abgelehnt (HTTP '+(body.error.status || body.error.httpCode || 'unbekannt')+'). Datei bleibt zur erneuten Prüfung erhalten.');
  const current=driveV2Metadata(body);
  if (current.id!==plan.file_id || current.trashed ||
      current.md5Checksum?.toLowerCase()!==plan.md5_checksum ||
      !current.parents.includes(plan.addParents) ||
      plan.removeParents.split(',').some(p=>current.parents.includes(p))) {
    throw new Error('Drive move result did not confirm the unchanged file in Processed');
  }
  return {file_id:current.id,moved:true,version:String(current.version)};
}
