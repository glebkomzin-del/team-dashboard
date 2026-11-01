"""Archive a successful n8n read execution without calling models or altering sources."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile


def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def execution_from_output(text):
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != '{':
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and 'status' in value and 'data' in value:
            return value
    raise ValueError('No execution result found')


def node_items(execution, name):
    runs = execution['data']['resultData']['runData'][name]
    return [item['json'] for run in runs for branch in run['data']['main']
            if branch for item in branch]


def body_offset(text):
    # Only the actually observed Tactiq envelope is recognized. Unknown exports
    # remain complete text; do not strip whitespace or guess speaker boundaries.
    prefix = 'Transcript delivered by Tactiq.io - get it for your Google Meet today!\r\n'
    marker = '\r\nTranskript:\r\n'
    if text.startswith(prefix):
        index = text.find(marker, 0, 8192)
        if index >= 0:
            return index + len(marker), 'tactiq-de-envelope-v1'
    return 0, 'unmodified-export'


def archive(execution, destination):
    if execution.get('status') != 'success' or execution.get('finished') is not True:
        raise ValueError('Incomplete execution cannot become an archive')
    pages = node_items(execution, 'Alle Dateiseiten lesen')
    if not pages or pages[-1].get('nextPageToken') or any(p.get('incompleteSearch') for p in pages):
        raise ValueError('Incomplete inventory')
    inventory = [file for page in pages for file in page['files']]
    originals = node_items(execution, 'Geprüftes Original ausgeben')
    expected = {file['id'] for file in inventory}
    actual = {source['drive_metadata']['id'] for source in originals}
    if expected != actual or len(expected) != len(inventory) or len(actual) != len(originals):
        raise ValueError('Archive must cover every inventory ID exactly once')
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError('Existing archives are never overwritten')
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.archive-', dir=destination.parent))
    records = []
    try:
        for source in originals:
            text = source['transcript']
            if source['intake_status'] != 'read_verified_not_imported' or not text.strip():
                raise ValueError('Unverified or empty original')
            raw_hash = sha(text)
            offset, transform = body_offset(text)
            body = text[offset:]
            if not body.strip():
                raise ValueError('Empty transcript body')
            body_hash = sha(body)
            for digest, content in [(raw_hash, text), (body_hash, body)]:
                path = temporary / (digest + '.txt')
                path.write_bytes(content.encode('utf-8'))
                path.chmod(0o600)
            records.append({
                'source_id': source['source_id'], 'event_date': source['event_date'],
                'title': source['title'], 'drive_metadata': source['drive_metadata'],
                'export_sha256': raw_hash, 'export_characters': len(text),
                'body_sha256': body_hash, 'body_characters': len(body),
                'body_offset_characters': offset, 'body_transform': transform,
            })
        manifest = {'format_version': 1, 'started_at': execution['startedAt'],
                    'stopped_at': execution['stoppedAt'], 'inventory_pages': len(pages),
                    'inventory_files': len(inventory), 'sources': records,
                    'model_calls': 0, 'imported_into_working_memory': False}
        path = temporary / 'manifest.json'
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
        path.chmod(0o600)
        # Verify serialized bytes and every derived body before publishing the directory.
        for record in records:
            raw = (temporary / (record['export_sha256'] + '.txt')).read_bytes()
            body = (temporary / (record['body_sha256'] + '.txt')).read_bytes()
            if hashlib.sha256(raw).hexdigest() != record['export_sha256'] or hashlib.sha256(body).hexdigest() != record['body_sha256']:
                raise ValueError('Stored checksum mismatch')
            if raw.decode('utf-8')[record['body_offset_characters']:].encode('utf-8') != body:
                raise ValueError('Derived body does not match its complete export')
        os.rename(temporary, destination)
        return manifest
    except BaseException:
        shutil.rmtree(temporary)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('execution', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    # read_bytes preserves the original CRLF characters inside JSON strings.
    result = archive(execution_from_output(args.execution.read_bytes().decode('utf-8')), args.destination)
    print(json.dumps({'archived_sources': len(result['sources']),
                      'inventory_files': result['inventory_files'],
                      'model_calls': 0, 'imported': False}))
