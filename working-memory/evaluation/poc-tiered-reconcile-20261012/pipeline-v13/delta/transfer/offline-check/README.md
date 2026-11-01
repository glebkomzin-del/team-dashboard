# Compact Delta v2 – Offline-Patch und Replay

Stand: 2026-10-13. Paketversion: `v13:compact-delta2:gate1`.
Ziel ist ausschließlich die verkürzte Ausgabe des bestehenden Compact-Abgleichs.
Dieses Paket wurde offline entwickelt; kein Modellaufruf, Deployment oder
Produktionsfluss wurde ausgeführt. Die Live-Entscheidungsqualität bleibt offen.

## Protokoll

`to_delta(full_response, obs_in, work_list)` erzeugt die Ausgabe;
`from_delta(delta, obs_in, work_list)` rekonstruiert den vollständigen Vertrag.
Die Rekonstruktion erfolgt vor Aliasauflösung, Archivöffnung, `resolve_v10`,
Lifecycle-Prüfung und Confidence-Prüfung. Die bestehenden fachlichen Prüfungen
in `check()` bleiben unverändert.

```json
{
  "observations": [
    {"source_index": 0, "changes": []},
    {"source_index": 1, "changes": [{"update_target": "W0"}, {"owner": null}]}
  ],
  "work_results": [
    {"work_index": "0", "result": {"action": "progress"}}
  ],
  "open_ids": [],
  "coverage_notes": []
}
```

Das Beispiel verkürzt `result` nur zur Lesbarkeit; tatsächlich enthält eine
Lifecycle-Änderung sämtliche bisherigen Pflichtfelder. Änderungen sind typisierte
Einzelfeldobjekte. Das vermeidet optionale Objektfelder, die zum vorhandenen
`strict=True`-Transport nicht passen. Alle Quellen erscheinen ausdrücklich mit
`source_index` und `changes`, auch bei leerer Änderungsliste. Nicht genannte
Beobachtungsfelder bleiben exakt erhalten; `null` ersetzt einen alten Wert.
Listen werden vollständig ersetzt, nicht zusammengeführt. Die Antwortreihenfolge
bleibt erhalten. Der bestehende Check prüft weiterhin vollständige Quellenabdeckung.

Nicht genannte Arbeitsplätze werden mit `unchanged` ergänzt. Fremde oder doppelte
Slots, doppelte Quellen und doppelte Feldänderungen werden verworfen. Eine fehlende
vollständige Quellenantwort wird nicht automatisch ergänzt. Feldlöschung ist im
bisherigen Vollvertrag nicht erlaubt und wird verworfen. Falls ein Feld in der
Extraktion fehlt, kann eine ausdrücklich ausgegebene Änderung es hinzufügen.

Archivöffnungen bleiben `observations=[]`, `work_results=null` und nichtleere
`open_ids`; sie sind keine finale fachliche Antwort. Originalschemata mit leerem
`source_index.enum` werden äquivalent als `observations.maxItems=0` dargestellt,
damit keine ungültige leere Enum an den strikten Transport geht.

## Patch-Vorschlag

`backend/` enthält Kopien von `compact_reconcile.py`, `hybrid_schema.py` und
`hybrid_pipeline.py` sowie die drei Delta-Helfer. Sie sind als gemeinsamer Overlay
auf einen vollständigen bestehenden Backend-Checkout gedacht. Hier wurden keine
Release-Dateien verändert oder installiert.

Nur `DASHBOARD_DELTA_OUTPUT == '1'` aktiviert das Protokoll. Andere Werte behalten
den bisherigen Prompt, das bisherige Schema, Ausgabelimit und fachliche Ergebnis.
Aktiv erhält Compact eine eigene Pipelinekennung. Die zusätzliche Pipelinekopie
ist notwendig, weil die Kennung vor dem Compact-Aufruf erzeugt wird.

Die bestehende Versionsfunktion berücksichtigt Quelltexte. Damit der ausgeschaltete
Schalter auch ihre bisherige Identität bewahrt, entfernt `delta_version.legacy_source`
ausschließlich die bekannten Delta-Patchanteile aus den Eingaben dieser Funktion.
Es werden keine Release-Snapshots oder neuen Baseline-Dateien gespeichert. Der
Test vergleicht die Eingaben des bestehenden Algorithmus mit erfasster Ersatzfunktion;
er berechnet keine Quellhashes. Unveränderte Abhängigkeiten sind dabei synthetische
Texte. Die aktive Kennung berücksichtigt zusätzlich sämtliche Delta-Helfer.

Rückweg nach späterer Installation: `DASHBOARD_DELTA_OUTPUT` entfernen oder auf `0`
setzen. Das ist ein lokal geprüfter Schalter, kein Nachweis eines durchgeführten
Produktions-Rollbacks.

## Offline-Nachweise und Messung

Zuerst wurde der vorab extrahierte Datensatz gelesen. Seine 41 Zeilen enthalten
40 Antwortdatensätze und eine Fehlerzeile; `coverage_notes` fehlen darin. Das
benannte Archiv wurde deshalb einmal im Modus `r|gz` gestreamt. `canonical/queue.jsonl`
enthält 41 Compact-Aufrufe: 40 parsebare vollständige JSON-Antworten und eine
unparsebare Antwort. Alle 41 Identitäten passen zum vorab extrahierten Datensatz.
Die unparsebare Antwort hat keinen JSON-Rundreise-Fall und wird nicht als Treffer
gezählt. Vier parsebare Antworten sind Archivöffnungen, 36 sind finale Formen.

`data/all_calls.jsonl` enthält die vollständigen 40 Offline-Fälle. Typstrenge
Rundreise: 40/40; abgeleitete Delta-Schemata: 40/40. Bool und Zahl werden nicht
gleichgesetzt. Wiederholung der Messung nutzt diese gespeicherten Daten und
öffnet das große Archiv nicht erneut:

```sh
python3 -I -B build_dataset.py
python3 -I -B test_delta.py
python3 -I -B test_replay_delta.py
python3 -I -B replay_delta.py --max-usd 1.00
```

`test_delta.py` verwendet das benannte Release-Backend ausschließlich als
read-only Importquelle für bestehende Validatoren und Vergleichsfunktionen.
Es benötigt den ursprünglichen Workspace; die eigenständigen Replaytests und
der Dry-Run benötigen ihn nicht. Python erstellt mit `-B` keine Bytecode-Dateien.

Die Größenmessung verwendet für beide Formate denselben kompakten JSON-Serializer,
Unicode-Zeichen und die Heuristik `ceil(Zeichen / 3.6)` je Antwort. Das ist kein
Tokenizer-Nachweis. Es werden weder Reasoning-Tokens noch Modellzuverlässigkeit
aus der Rekonstruktion geschätzt.

| Größe | Vollausgabe | Delta |
| --- | ---: | ---: |
| Zeichen, Summe | 1.041.623 | 473.978 |
| Zeichen, Median | 27.546 | 11.820,5 |
| Zeichen, größter Fall | 67.833 | 37.513 |
| Tokenschätzung, Summe | 289.355 | 131.680 |
| Tokenschätzung, Median | 7.652 | 3.284 |
| Tokenschätzung, größter Fall | 18.843 | 10.421 |

Erwartete sichtbare Ausgabeersparnis: 54,4919 %, entsprechend 157.675 geschätzten
Tokens bzw. 1,57675 USD bei den vorgegebenen 10 USD/Mio. Ausgabetokens über alle
40 Fälle. Dies beschreibt die Ausgabe bei korrekter Delta-Erzeugung durch das
Modell, keine bereits realisierte Kostenersparnis und keine gesamte Kostenquote.
Die tatsächlichen gespeicherten Output-Tokens einschließlich Reasoning werden in
`measurements.json` getrennt angegeben. JSON-Neuserialisierung und Originaltext
des Providers haben unterschiedliche Leerzeichen; die Messung hält den Serializer
zwischen beiden Formaten konstant.

## Replay und Transfer

Sechs verschiedene finale Aufrufe: zwei kleine unter 2.000 Zeichen, zwei mittlere
mit 4.500 bis 12.000 Zeichen, zwei große über 20.000 Zeichen der Vollausgabe.
Je Fenster wurden die zwei kostengünstigsten geeigneten Fälle gewählt. Diese
plausible Größenannahme erfüllt den Budgettest; sie deckt weder das globale obere
Tertil noch die größten Antworten mit rund 20.000 Ausgabetokens ab. Eine Auswahl
aus den globalen Tertilen wäre mit diesem Kostendeckel nicht ausführbar.

Die Requests verwenden `gpt-6.1-sol`, Reasoning `medium`, striktes Delta-Schema und
`prompt_cache_options: {"mode": "explicit"}`. Die Ausgabecaps betragen mindestens
4.096 Tokens und reservieren auch Reasoning. Es gibt keine automatische Wiederholung.

Kostenparameter stammen aus dem vorhandenen Offline-Harness: Input 2,00,
Cache-Read 0,10, Cache-Write 2,50 und Output 10,00 USD/Mio. Sie wurden hier wegen
des Netzwerkverbots nicht live aktualisiert. Die Reservierung nimmt für alle
Input-Tokens die höchste Inputrate von 2,50 an und nimmt keine Cachetreffer an.
Der Inputproxy verwendet echte Referenz-Inputtokens, nur positive UTF-8-Zuwächse
von Prompt und Schema sowie 4.096 Tokens Framingreserve. Er ist keine garantierte
Tokenizer-Obergrenze. Der harte lokale Deckel ist höchstens 1,00 USD; die tatsächliche
Ausgabe des Dry-Runs ist für die Reservierung maßgeblich. Dessen kleine Abweichung
vom ursprünglichen Auswahlproxy entsteht durch Schema-Serialisierung mit Leerzeichen.

Reservierungen werden vor dem Transport dauerhaft geschrieben. Rohstreams werden
fortlaufend vollständig gespeichert und synchronisiert. `replay_ledger.jsonl`
enthält Rohantworten, Usage und Versuchsergebnisse. Bereits versuchte Identitäten
werden beim Neustart nicht erneut aufgerufen; bisherige Kosten werden mitgezählt.
Unbekannte Usage oder unterbrochene Reservierungen sperren weitere Ausführung.
Ein vorhandener `replay.lock` verhindert parallele Ausführung; ihn nach einem
Abbruch nicht ohne Prüfung des Ledgers entfernen. API-Fehler führen zu keinem
automatischen Retry. Credential-Dateien werden nie gelesen.

`compare_delta.py` rekonstruiert die Antwort und prüft beide Schemata, finale Form,
Beobachtungsabdeckung, `update_target`/`update`/`matter_id` und vollständige
Lifecycle-Änderungsobjekte. Es berichtet reale Output-Tokens einschließlich
Reasoning gegen die gespeicherte Referenz. Nichtfinale Antworten zählen nicht als
Qualitätsnachweis. Ein bestandener Vergleich bewertet genau diese sechs Fälle,
keine allgemeine Serienzuverlässigkeit.

`transfer/delta-bundle.tar` ist ein unkomprimiertes, eigenständiges Replay-Paket.
Auf dem später autorisierten Server in ein neues Verzeichnis entpacken; dort:

```sh
sh run_delta_on_server.sh
```

Der Wrapper führt zuerst den Offline-Dry-Run aus, verlangt dann ein bereits in
der Umgebung exportiertes `OPENAI_API_KEY` und führt anschließend
`--execute --max-usd 1.00` sowie den Vergleich aus. Hier wurde der Wrapper nie
ausgeführt. Reine Offline-Nutzung: `python3 -I -B replay_delta.py --max-usd 1.00`.
Vor einem späteren bezahlten Lauf sind die angegebenen Preise bei Änderung im
Replay-Harness anzupassen; bei unsicherem Preisstand nicht ausführen.

Die Umsetzung und Nachweise bleiben ausschließlich im freigegebenen Delta-Paket.
Es gibt keinen Commit, Push, Deploy oder Beleg über unveränderte Außenverzeichnisse.
