"""Keep legacy version inputs identical when the delta wire switch is disabled.

This is a narrow inverse of the supplied patch, not a stored release snapshot.
No hash calculation or filesystem access occurs here. The existing version()
algorithm remains responsible for its normal source revision identity.
"""

_CHECK = '''        if delta_enabled:
            from delta_codec import from_delta
            try:
                value = from_delta(value, raw['observations'], catalog.work)
            except (ValueError, TypeError, KeyError) as error:
                raise ValidationError('Invalid compact delta') from error
'''
_PROMPT = '''        if delta_enabled:
            from delta_schema import delta_prompt
            prompt = delta_prompt(prompt)
'''
_SCHEMA_HELPER = '''

def compact_delta_schema(full_schema):
    """Environment-gated wire contract; all other stage schemas stay unchanged."""
    import os
    if os.environ.get('DASHBOARD_DELTA_OUTPUT') != '1':
        return full_schema
    from delta_schema import delta_schema
    return delta_schema(full_schema)
'''
_VERSION = '''    prefix = ('v13:compact-delta2:gate1:' if compact and os.environ.get('DASHBOARD_DELTA_OUTPUT') == '1' else ('v11:compact1:gate1:' if compact else 'v10:hybrid1:gate1:'))
    if compact and os.environ.get('DASHBOARD_DELTA_OUTPUT') == '1':
        names += ('delta_codec.py', 'delta_schema.py', 'delta_version.py')
    def source_text(name):
        text = (ROOT/name).read_text()
        if os.environ.get('DASHBOARD_DELTA_OUTPUT') != '1' or not compact:
            from delta_version import legacy_source
            return legacy_source(name, text)
        return text
    return prefix+model+':'+fingerprint(''.join(source_text(n) for n in names))[:16]
'''
_LEGACY_RETURN = "    return ('v11:compact1:gate1:' if compact else 'v10:hybrid1:gate1:')+model+':'+fingerprint(''.join((ROOT/n).read_text() for n in names))[:16]\n"


def legacy_source(name, text):
    if name == 'compact_reconcile.py':
        text = text.replace('import copy\nimport os\n', 'import copy\n', 1)
        text = text.replace('from hybrid_schema import alignment_schema, lifecycle_schema, compact_delta_schema',
                            'from hybrid_schema import alignment_schema, lifecycle_schema', 1)
        text = text.replace('    return compact_delta_schema(value)\n\n\ndef _packed_candidates',
                            '    return value\n\n\ndef _packed_candidates', 1)
        text = text.replace("    delta_enabled = os.environ.get('DASHBOARD_DELTA_OUTPUT') == '1'\n", '', 1)
        text = text.replace(_CHECK, '', 1).replace(_PROMPT, '', 1)
    elif name == 'hybrid_schema.py':
        text = text.replace(_SCHEMA_HELPER, '', 1)
    elif name == 'hybrid_pipeline.py':
        text = text.replace('import json\nimport os\n', 'import json\n', 1)
        text = text.replace(_VERSION, _LEGACY_RETURN, 1)
    return text
