#!/usr/bin/env python3
"""Prepare an unexecuted, private two-scope option; never changes n8n metadata."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

KEY = Path("/opt/dashboard-supabase-20261003/n8n-pause-access-1/existing-api-key-private.json")
ADD = ("workflow:activate", "workflow:deactivate")


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def guarded_sql(key, current, replacement):
    return ("BEGIN;\nDO $option$\nDECLARE k user_api_keys%ROWTYPE;\nBEGIN\n"
            " SELECT * INTO STRICT k FROM user_api_keys WHERE id=" + literal(key["id"]) + " FOR UPDATE;\n"
            " IF k.\"userId\"<>" + literal(key["userId"]) + "::uuid"
            " OR md5(k.\"apiKey\")<>" + literal(hashlib.md5(key["apiKey"].encode()).hexdigest())
            + " OR k.scopes::jsonb<>" + literal(json.dumps(current)) + "::jsonb THEN\n"
            "  RAISE EXCEPTION 'n8n key identity or scopes changed';\n END IF;\n"
            " UPDATE user_api_keys SET scopes=" + literal(json.dumps(replacement)) + "::json WHERE id=k.id;\n"
            "END $option$;\nCOMMIT;\n")


def main(out):
    os.umask(0o077)
    out = Path(out).resolve()
    assert str(out).startswith("/root/dashboard-intake-transition-scope-option-")
    assert not out.exists()
    key = json.loads(KEY.read_text())
    query = 'SELECT row_to_json(t) FROM (SELECT id,"userId",scopes,md5("apiKey") AS md5 FROM user_api_keys) t'
    rows = subprocess.check_output(["docker", "exec", "n8n_postgres", "psql", "-U", "n8n", "-d", "n8n",
                                    "-XqAt", "-v", "ON_ERROR_STOP=1", "-c", query], timeout=20).decode().splitlines()
    assert len(rows) == 1
    live = json.loads(rows[0])
    assert key["id"] == live["id"] and key["userId"] == live["userId"]
    assert hashlib.md5(key["apiKey"].encode()).hexdigest() == live["md5"]
    assert key["scopes"] == live["scopes"] and all(scope not in live["scopes"] for scope in ADD)
    old = live["scopes"]
    new = old + list(ADD)
    out.mkdir(mode=0o700)
    for name, before, after in (("add-scopes.sql", old, new), ("restore-scopes.sql", new, old)):
        path = out / name
        path.write_text(guarded_sql(key, before, after))
        path.chmod(0o600)
    receipt = {"executed": False, "added_scopes": list(ADD),
               "private_key_file_sha256": hashlib.sha256(KEY.read_bytes()).hexdigest(),
               "original_scope_sha256": hashlib.sha256(json.dumps(old, separators=(",", ":")).encode()).hexdigest(),
               "expanded_scope_sha256": hashlib.sha256(json.dumps(new, separators=(",", ":")).encode()).hexdigest(),
               "file_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir()}}
    (out / "option-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    (out / "option-receipt.json").chmod(0o600)
    print(json.dumps({"result": "PREPARED_ONLY", "directory": str(out), "receipt": receipt}))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: prepare_scope_option.py /root/dashboard-intake-transition-scope-option-<id>")
    main(sys.argv[1])
