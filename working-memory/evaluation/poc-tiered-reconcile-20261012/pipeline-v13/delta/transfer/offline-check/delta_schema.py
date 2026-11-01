"""Derive a strict-compatible delta contract from the actual full call schema."""
from copy import deepcopy

PROMPT_ADDENDUM = '''AUSGABEFORMAT DELTA v2: Prüfe weiterhin jede Beobachtung und jeden Arbeitsplatz vollständig. Gib observations in gewünschter Reihenfolge mit genau einem {source_index, changes} pro Quelle aus. changes ist eine Liste von Einzelfeldobjekten, z.B. [{"update_target":"W0"},{"matter_id":"M0"}]. Nur gegenüber den Vorläufigen Beobachtungen geänderte Felder ausgeben; changes=[] bedeutet unverändert. Nicht genannte Felder werden exakt aus der Extraktion übernommen. Explizites null ersetzt den alten Wert; Listen vollständig ersetzen. Alle fachlichen Entscheidungen, Korrekturen und Belege unverändert sorgfältig prüfen. work_results ist eine Liste nur geänderter Arbeitsplätze: [{"work_index":"0","result":{...}}]; result enthält alle bisherigen Änderungsfelder. Nicht genannte Arbeitsplätze werden als unchanged rekonstruiert. Auch direkt über eine Beobachtung behandelte Zustandswechsel dort auslassen, um Doppeländerungen zu vermeiden. Zum Öffnen weiter open_ids mit H-IDs, observations=[], work_results=null und coverage_notes; endgültig open_ids=[], alle source_index genau einmal, work_results darf [] sein. coverage_notes unverändert im bisherigen Format.'''

# These are output representation instructions, never factual decision rules.
_REPLACEMENTS = (
    ('Genau ein work_results-Eintrag pro Arbeitsplatz, auch bei unveränderten Aufgaben.',
     'Prüfe weiterhin jeden Arbeitsplatz; unveränderte Ergebnisse werden implizit rekonstruiert.'),
    ('work_results enthält genau jeden nummerierten Arbeitsplatz.',
     'work_results enthält nur Änderungen nummerierter Arbeitsplätze im Delta-Format.'),
    ('wird in work_results als unchanged markiert (nicht doppelt ändern)',
     'wird in work_results ausgelassen (nicht doppelt ändern)'),
    ('Für jede ID genau ein Ergebnis:', 'Für jede ID intern genau ein Ergebnis:'),
)


def delta_prompt(prompt):
    marker = '\nVorläufige Beobachtungen:\n'
    if marker not in prompt:
        raise ValueError('Compact extraction section missing')
    # Place instructions before untrusted data, without changing source content.
    head, tail = prompt.split(marker, 1)
    for old, new in _REPLACEMENTS:
        head = head.replace(old, new)
    return head + '\n' + PROMPT_ADDENDUM + marker + tail


def delta_schema(full_schema):
    value = deepcopy(full_schema)
    original = value['properties']['observations']['items']
    fields = original['properties']
    branches = [{'type': 'object', 'additionalProperties': False,
                 'properties': {name: deepcopy(spec)}, 'required': [name]}
                for name, spec in fields.items() if name != 'source_index']
    value['properties']['observations']['items'] = {
        'type': 'object', 'additionalProperties': False,
        'properties': {'source_index': deepcopy(fields['source_index']),
                       'changes': {'type': 'array', 'items': {'anyOf': branches}}},
        'required': ['source_index', 'changes']}
    index_spec = value['properties']['observations']['items']['properties']['source_index']
    if index_spec.get('enum') == []:
        # Empty extraction means no item is legal, not an invalid empty enum.
        # maxItems=0 preserves that exact empty-array contract for strict APIs.
        del index_spec['enum']
        value['properties']['observations']['maxItems'] = 0
    life = value['properties']['work_results']['anyOf'][0]
    slots = list(life['properties'])
    change = deepcopy(value['$defs']['lifecycle_result']['anyOf'][1])
    value['$defs']['lifecycle_result'] = change
    slot_schema = {'type': 'string', **({'enum': slots} if slots else {})}
    value['properties']['work_results'] = {'anyOf': [
        {'type': 'array', **({'maxItems': 0} if not slots else {}), 'items': {
            'type': 'object', 'additionalProperties': False,
            'properties': {'work_index': slot_schema,
                           'result': {'$ref': '#/$defs/lifecycle_result'}},
            'required': ['work_index', 'result']}}, {'type': 'null'}]}
    return value


def full_schema_for_validation(full_schema):
    """Equivalent valid schema for zero-observation archived requests only."""
    value = deepcopy(full_schema)
    index_spec = value['properties']['observations']['items']['properties']['source_index']
    if index_spec.get('enum') == []:
        del index_spec['enum']
        value['properties']['observations']['maxItems'] = 0
    return value
