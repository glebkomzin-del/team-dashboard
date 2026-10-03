"""Pure decoding and archive binding for pg_restore's Vault COPY text output."""
import datetime
import hashlib
import re


def copy_value(value):
    # NULL recognition precedes unescaping; escaped literal \\N is text.
    if value == r'\N':
        return None
    raw = value.encode('utf-8')
    decoded = bytearray()
    escapes = {ord(k): ord(v) for k, v in
               {'b': '\b', 'f': '\f', 'n': '\n', 'r': '\r', 't': '\t', 'v': '\v'}.items()}
    i = 0
    while i < len(raw):
        char = raw[i]
        i += 1
        if char != 92:
            decoded.append(char)
            continue
        if i == len(raw):
            raise ValueError('Incomplete COPY escape')
        char = raw[i]
        i += 1
        if 48 <= char <= 55:
            digits = bytes([char])
            while i < len(raw) and len(digits) < 3 and 48 <= raw[i] <= 55:
                digits += bytes([raw[i]])
                i += 1
            decoded.append(int(digits, 8) & 255)
        elif char == ord('x') and i < len(raw) and chr(raw[i]) in '0123456789abcdefABCDEF':
            digits = bytes([raw[i]])
            i += 1
            if i < len(raw) and chr(raw[i]) in '0123456789abcdefABCDEF':
                digits += bytes([raw[i]])
                i += 1
            decoded.append(int(digits, 16))
        else:
            # COPY treats any other backslashed character as itself.
            decoded.append(escapes.get(char, char))
    return decoded.decode('utf-8')


def vault_copy_rows(copy_sql):
    # Split only on physical newlines, never on other COPY text characters.
    lines = copy_sql.split('\n')
    headers = [i for i, line in enumerate(lines) if line.startswith('COPY vault.secrets ')]
    if len(headers) != 1:
        raise ValueError('Expected one Vault COPY block')
    start = headers[0]
    match = re.fullmatch(r'COPY vault\.secrets \(([^)]+)\) FROM stdin;', lines[start])
    if not match:
        raise ValueError('Unexpected Vault COPY header')
    columns = match[1].split(', ')
    if len(columns) != len(set(columns)):
        raise ValueError('Duplicate Vault COPY columns')
    rows = []
    for line in lines[start + 1:]:
        if line == r'\.':
            return rows
        fields = line.split('\t')
        if len(fields) != len(columns):
            raise ValueError('Vault COPY field count differs')
        rows.append(dict(zip(columns, map(copy_value, fields))))
    raise ValueError('Missing Vault COPY terminator')


def verify_vault_copy(copy_sql, metadata_rows):
    rows = vault_copy_rows(copy_sql)
    assert len(rows) == len(metadata_rows) == 1, 'Vault row count differs'
    actual, expected = rows[0], metadata_rows[0]
    required = {'id', 'name', 'description', 'secret', 'key_id', 'nonce', 'created_at', 'updated_at'}
    assert set(actual) == required, 'Vault COPY columns differ'
    for key in ['id', 'name', 'description']:
        assert actual[key] == expected[key], 'Vault identity metadata differs'
    # Historical sidecars omitted key_id; they can prove only the observed NULL case.
    assert actual['key_id'] == expected.get('key_id'), 'Vault key identity differs'
    assert isinstance(actual['secret'], str), 'Vault cipher missing'
    assert hashlib.sha256(actual['secret'].encode('utf-8')).hexdigest() == expected['cipher_sha256'], 'Vault cipher differs'
    assert actual['nonce'] == '\\x' + expected['nonce_hex'], 'Vault nonce differs'
    for key in ['created_at', 'updated_at']:
        assert datetime.datetime.fromisoformat(actual[key]) == datetime.datetime.fromisoformat(expected[key]), 'Vault timestamp differs'
    return True
