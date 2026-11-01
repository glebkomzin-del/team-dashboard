# Pipeline-v12: isolierter deterministischer Hot-Set-PoC

Stand: 2026-10-13. Default auf A=30,k=5 angepasst; aktuelle Nachweise unter
`evidence/age30-validation.json` (siehe Änderungsstand am Ende). Der folgende
ursprüngliche PoC-Abschluss ist historisch: Hot-Set lokal validiert; vollständige Abnahme bleibt wegen
zehn bereits vorhandenen Vollsuite-Fehlern und drei beobachteten Änderungen
außerhalb des Zielverzeichnisses offen. Auftrag: ausschließlich lokale Backend-Kopie ändern und mit
synthetischen Fixtures prüfen. Kein Git, Deployment, Netzwerk/API/Serverzugriff,
Secretzugriff oder Installation. Python-Stdlib; Ausführung mit `python3 -I -B`.
`-B` verhindert Bytecode-Schreibzugriffe zusätzlich zum isolierten Modus.
Diese Notiz ist der einzige Status-/Betriebseinstieg dieses PoC.

## Herkunft, Änderungen und Nachweise

Quelle: `../../sol-operational-release-20261006/backend/` relativ zu diesem
Verzeichnis. 62 unmittelbare Python-Module wurden unverändert kopiert, ohne
den Quell-Unterordner `evaluation/` rekursiv zu übernehmen. Genau fünf benötigte
Ressourcen liegen in `backend/evaluation/`: `prompt-v9.txt`, `schema-v9.json`,
`work-gate-prompt-v9.txt`, `work-gate-schema-v9.json`, `source-corrections.json`.
Die ersten vier stammen aus der Release-Kopie. Dort fehlt `source-corrections.json`;
daher stammt diese Hilfsdatei aus `working-memory/evaluation/`.
`evidence/copy-manifest.json` bindet Pfade und SHA-256 des Ausgangsstands.

Eigene Dateien und Diff-Zusammenfassung:

| Datei | Änderung |
| --- | --- |
| `backend/candidate_filter.py` | Neue reine Funktion; Datum ODER Beobachtungs-Suchrang ODER exakte ID; stabile Reihenfolge; überlappende Gründe-Zähler. |
| `backend/hybrid_pipeline.py` | Env-Schalter/-Parameter, eigene aktive Version, geordnete separate Work-Hits, Filter vor Compact, bereinigte Treffer, IDs-Statistik; ungenutzte Compact-pending-Liste entfällt. |
| `tests/test_hotset.py` | Neue synthetische Filter-, Versions-, Request-Identitäts-, Promptvergleichs- und Integrationstests mit lokaler Mock-Stage. |
| `tests/existing/test_hybrid.py`, `test_compact_reconcile.py` | Unveränderte Kopien der bestehenden betroffenen Tests. |
| `tests/existing/test_memory.py`, `test_durable_calls.py`, `test_canonical_archive.py` | Unveränderte synthetische Fixture-Helfer für die vorhandenen Tests. |
| `run_tests.py` | Stdlib-Testlauf mit lokalen Importpfaden, Tempdateien nur hier, deaktiviertem Bytecode, leerem Prozess-Environment sowie Audit-Sperren für Netzwerk, Subprozesse, Secretdateien und externe Schreibzugriffe. |
| `verify_scope.py` | Vergleich der Ausgangs-Dateizeitstempel unter Working Memory, Quellhashes und Testkopien; Code-Diff ohne Git; Syntaxprüfung ohne Bytecode. |
| `DEPLOY-NOTES.md` | Auftrag, Annahmen, Wirkung, Rückweg, Risiken und tatsächliche Testgrenzen. |
| `evidence/` | Manifeste, vollständige Testausgaben, Quell-Diff, Review und Zeitstempelvergleich; temporäre Testdateien sind synthetisch. |

Keine Änderungen an den übrigen kopierten Backend-Modulen oder den fünf
Hilfsressourcen. Der genaue Diff und Abschlussstand werden als
`evidence/backend.diff` und `evidence/validation-summary.json` gesichert.

## Regel und bewusste Annahmen

`filter_work(work, query_hits, observations, meeting_date, exact_ids,
*, age_days_max=30, rank_max=5)` gibt `(kept, dropped, stats)` zurück.

* Alter: `(meeting_date - last_changed).days <= age_days_max`. Genau 30 Tage
  ist inklusive. Fehlende/ungültige Datumswerte werden konservativ behalten.
  ISO-Daten, ISO-Zeitstempel sowie Python-`date`/`datetime` werden unterstützt;
  Zeitstempel werden auf ihren angegebenen Kalendertag reduziert. Zukünftige
  Änderungsdaten erfüllen entsprechend der vorgegebenen Ungleichung die Regel.
* Rang: Query exakt `' '.join([title, subject, *search_keywords])`, mit den
  ursprünglichen Defaults für `subject` und `search_keywords`. Nur Queries der
  Beobachtungen zählen; allgemeine Meeting-Queries allein reichen nicht.
  Positionen sind nullbasiert, `< rank_max`. Die separate `['work']`-Suche mit
  K=20 ist die Rangquelle. Gemischte Treffer haben eine andere Einfügereihenfolge
  und dürfen dafür nicht verwendet werden.
* Exakt: Eine aus dem ursprünglichen `allwork` stammende, im Transkript enthaltene
  Aufgaben-ID bleibt. Die bestehende Substring-Erkennung wird unverändert genutzt.
* `done` wird gleich behandelt. Ausgabeobjekte und Reihenfolge bleiben unverändert.
  Doppelte Treffer belegen ihre ursprünglichen Suchplätze; ein Work-Eintrag zählt
  pro Grund höchstens einmal. Die Zähler `age`, `rank`, `exact` sind unabhängig
  und dürfen sich überlappen. Ein Treffer ohne `kind` gilt in der reinen Funktion
  als Work; explizite Nicht-Work-Treffer werden beim Zählen ignoriert.
* Schwellen müssen nichtnegative ganze Zahlen sein; 0 ist zulässig. Ungültige
  aktive Env-Werte lösen vor Jobregistrierung `ValidationError` aus. Bei
  deaktiviertem Filter oder Nicht-Compact werden diese Env-Werte nicht ausgewertet.

Standard ist seit 2026-10-13 **A=30 Tage, k=5**. Die vorhandene
Validierung mit echten Produktions-Suchrängen in
[`../selector/RANK-VALIDATION.md`](../selector/RANK-VALIDATION.md) belegt
**64/64 bei 49,1 % behaltenen Kandidaten** (6.002/12.223, separate Work-Liste).
Historischer Vergleich: A=21,k=5 erhielt 63/64; verpasst wurde eine
Lebenszyklusänderung einer 25 Tage alten Aufgabe mit nullbasiertem Suchrang 12
und ohne exakte Nennung. Der neue synthetische Regressionstest reproduziert
exakt diese Voraussetzungen: A=30 behält die Aufgabe allein wegen des Alters,
A=21 verwirft sie bei unverändertem k=5.

Die begrenzte Annahme bleibt: Alter und kurzer Suchrang erhalten fachlich
relevante Altbezüge auch außerhalb der untersuchten Fälle ausreichend. 64/64
belegt diese Stichprobe, keine allgemeine Zuverlässigkeit oder Kostenersparnis.
Die genannten 99,5 % `unchanged` stammen aus dem Nutzerbefund. Im aktuellen
Änderungsauftrag wurde nur der vorhandene Rangbericht gelesen; es gab keinen
Produktions-, Netzwerk- oder Providerzugriff.

## Compact-Einbindung und nachgelagerte Invarianten

Aktiv ausschließlich mit `compact=True` und `DASHBOARD_HOTSET_FILTER=1`.
`process()` hält die Work-Suchreihenfolge separat in `work_query_hits` fest,
filtert `work` unmittelbar vor `compact_reconcile.run()` und entfernt dropped
Work-Hits auch aus dessen `hits` und `query_hits`. Nicht-Work-Treffer bleiben.
Jede innerhalb der Ranggrenze gefundene Work-ID aus dem gewählten Bestand
bleibt damit im Work-Katalog; Work-Aliasnamen werden aus der gefilterten Liste
neu gebildet. Compact verlangt vollständige Lifecycle-Abdeckung dieser Liste.
Eine verworfene Aufgabe kann dort nicht per fremdem Work-Alias gewählt werden.

Im Compact-Modus ist `uncertain` bereits leer, weshalb die spätere erweiterte
Suche den gefilterten Bestand nicht überschreibt. `pending` war für Compact
unbenutzt und ist jetzt leer; so bricht ein konservativ behaltenes fehlendes
Datum nicht in dieser unbenutzten Liste. Gate-Aufgaben werden aus dem gefilterten
`work` nach den tatsächlich berührten IDs ausgewählt. Confidence, Originalbelege,
Known-ID-Validierung, Temporal Guard und Apply bleiben bestehen. Verworfen
bedeutet nicht gelöscht, erledigt oder als `unchanged` semantisch bestätigt.

`statistics['hotset']` enthält `n_in`, `n_kept`, `n_dropped`, `age`, `rank`,
`exact`, beide Schwellen und `dropped_ids` in ursprünglicher Reihenfolge.
Diese Statistik enthält keine Aufgaben- oder Meetingtexte. `selected_work`
bezeichnet aktiv die gefilterte Zahl, `total_work` weiterhin den Gesamtbestand.

## Versionskennung und Request-Identität

Die Kennung entsteht in `hybrid_pipeline.version(model, compact=True)`:
der vorhandene Quell-Fingerprint bezieht aktiv zusätzlich `candidate_filter.py`
ein; danach folgt `:hotset1:age=<Wert>:rank=<Wert>`. Die aktive Kennung
enthält somit die Parameterwerte und endet mit den neuen Defaults auf
`:hotset1:age=30:rank=5`. Der Suffix wird dynamisch erzeugt; keine feste
Versionsnummer muss umbenannt werden. Tests prüfen erzeugte und explizit
registrierte Kennungen. Auch andere Schwellen
erhalten unterschiedliche Identitäten. Inaktiv gibt es keinen Hot-Set-Suffix;
der geänderte Inhalt von `hybrid_pipeline.py` ändert allerdings auch inaktiv
seinen bestehenden Quell-Fingerprint gegenüber der unveränderten Release-Datei.
Die zugesagte Byte-Identität betrifft Prompttexte, nicht diesen Quellhash.

`process()` übergibt diese Kennung an `memory.register()`. Bei explizitem
`pipeline=` wird der gleiche aktive Suffix ergänzt, sofern er noch nicht am
Ende vorhanden ist. `memory.register()` bindet Pipeline an die Job-ID via
`fingerprint(source_version_id + ':' + pipeline)` und den eindeutigen
Schlüssel `(source_version, pipeline)`.

`durable_calls.DurableCalls.__init__()` bildet
`request_scope = {'pipeline': job['pipeline'], 'revision': job['expected_revision']}`.
Wenn `prior_calls` angegeben ist (einschließlich `[]`), enthält die serialisierte
Request-Identität dieses Scope; der Request-Hash bindet so auch den Hot-Set-Modus
bei identischem Prompt. Die Reservierung erfolgt über `reserve_call` für
Job-ID, Lease und Call-Index; bereits beantwortete Requests werden nur bei
passender Identität wiederverwendet. `call_budget.reserve_micro_usd()` berechnet
hingegen Beträge aus Prompt/Schema/Modell/Output; es liest die Pipelinekennung
nicht selbst. Der lokale `CallBudget` hat keinen Pipeline-basierten Request-Key.
Bei `prior_calls=None` enthält der Durable-Request keinen Scope; hier trennt
der verschiedene Job-ID-Namensraum die Ledger-Slots. Bei einem späteren
kanonischen Testlauf muss auch die äußere Job-/Store-Konfiguration die neue
Version tragen; nur einen inneren Override zu verändern aktualisiert keine
bereits instanziierte DurableCalls-Jobkonfiguration. Hier wird keine geändert.

## Schattenbetrieb und Rückweg

Beispielwerte für einen später separat freizugebenden Schattenlauf:

```text
DASHBOARD_HOTSET_FILTER=1
DASHBOARD_HOTSET_AGE_DAYS=30
DASHBOARD_HOTSET_RANK=5
```

Die Variablen aktivieren keinen Schattenmodus und verhindern `apply()` nicht.
Für einen Vergleich sind zwei voneinander und von Produktion getrennte Kopien
derselben Ausgangsdaten, Revision und Eingaben notwendig: Kontrollzweig ohne
Schalter, Schattenzweig mit Schalter. Ausschließlich isolierte lokale Datenbanken
und Mock-Stage verwenden; `api.store`, Dokumentindex und Receipt/Run-Verzeichnisse
dürfen keine Produktionsverbindung enthalten. Kein Live-Suche-/Providerzugriff
ist durch diesen Auftrag freigegeben. Verglichen werden Kandidatenzahl,
behaltene/verwarfene IDs, Zuordnungen und Zustandsvorschläge; keine Schatten-
Ergebnisse, Ledger, Outbox oder Projektionen in Produktion übernehmen. Alle
Fälle zählen; keine Nachgenerierung bis zum erwünschten Resultat.

Rückweg: `DASHBOARD_HOTSET_FILTER` entfernen oder auf `0` setzen. Die aktuelle
Kopie nutzt dann wieder den vollständigen gewählten Bestand. Für exakt den
ursprünglichen Code-/Versionsstand eine neue Kopie aus der unveränderten Quelle
erzeugen; das Manifest belegt den Ausgangsstand. Isolierte Schatten-Datenbanken
und -Jobs nicht mit anders versionierten Kontrolljobs vermischen. Ein Rollback
von Produktionsdaten ist nicht nötig, da keine veröffentlicht oder geändert wurden.

## Historische PoC-Prüfungen, Grenzen und offene Abnahme

Alle Tests nutzen synthetische Inhalte. Der Test-Runner leert sein Environment,
verwendet keine installierten Zusatzpakete und schreibt temporäre Dateien nur
unter `evidence/tmp`. Der Quell-Originalprozess für den Bytevergleich wird nur
lesend geladen; Laufzeitordner und benötigte Promptressourcen werden in eine
temporäre Kopie innerhalb dieses Verzeichnisses umgeleitet. Compact läuft sowohl
mit synthetischen API-Antworten als auch mit einer ausdrücklich ersetzten lokalen
Mock-Stage; keine Kernfunktion wurde mit einem echten Provider ausgeführt.

Die per `rg` gefundenen betroffenen Bestandstests sind `working-memory/test_hybrid.py`
und `working-memory/test_compact_reconcile.py`. Die fünf lokalen Testkopien sind
bytegleich zur Herkunft. `test_compact_reconcile.py` importiert eine in der festen
Release-Kopie fehlende `GPT6_MAX_INPUT_TOKENS`-Konstante. Der Runner entfernt
ausschließlich diesen Import im Speicher, ohne Wert, Assertion oder Testcode zu
ersetzen, damit die übrigen Tests überhaupt ausführbar werden. Im vollen Lauf
scheitert der zugehörige Test weiterhin an der fehlenden Konstante.

Vorher: Vollsuite **38/48 bestanden, 6 Failures, 4 Errors**, kompatibler Teil
**38/38 bestanden**. Zehn fachfremde Baseline-Fehler betreffen sieben neue
`StageResumeTests` (neuere Retry-/Mixed-Model-Funktion) sowie drei neue GPT6-
Budgettests. Der kompatible Teil lässt diese zehn mit namentlichem Nachweis im
vollen Log separat; der erfolgreiche Transport-Test dieser Klasse läuft mit.
Kein Hinzufügen der fehlenden Produktionsfunktionen ist Bestandteil des Auftrags.
Der generelle Anspruch „alle vorhandenen Tests grün“ bleibt wegen dieses
Versionskonflikts offen; eine grüne PoC-Suite ersetzt ihn nicht.

Vollständige Befehle, jeweils in `pipeline-v12/`:

```sh
python3 -I -B run_tests.py legacy-full
python3 -I -B run_tests.py compatible
python3 -I -B run_tests.py acceptance
python3 -I -B verify_scope.py
```

Vollständige Ausgaben liegen unter `evidence/tests-before-full.txt`,
`evidence/tests-before-compatible.txt`, `evidence/tests-after-full.txt` und
`evidence/tests-after-acceptance.txt`. Finale Zähler, Review und Zeitstempelvergleich
sind in `evidence/validation-summary.json` festgehalten.
Die ursprünglichen Quellzeitstempel wurden vor der ersten Dateiänderung für alle
Dateien unter `working-memory/` außerhalb `pipeline-v12/` erfasst. Inhaltshashes
der ausdrücklich kopierten Quellmodule/-ressourcen ergänzen den Abschlussvergleich.
Elternverzeichnis-Zeitstempel ändern sich durch das Anlegen der autorisierten
Unterordner; verglichen werden Dateien, nicht diese erwarteten Verzeichnisänderungen.

Nachher: kompatible Bestandstests plus 30 neue Hot-Set-Tests **68/68 bestanden**,
0 Failures/Errors/Skips. Vollsuite weiterhin **38/48 bestanden, 6 Failures,
4 Errors**; die zehn Baseline-Fehler sind unverändert. Der volle Anspruch einer
grünen Bestandssuite bleibt offen, der Hot-Set-PoC ist lokal validiert.

Das unabhängige read-only-Review `/root/hotset_review` bestätigt die lokalen
Hot-Set-Pflichten ohne Implementierungsblocker und die exakt gleichen zehn
Baseline-Fehler. Es erteilt wegen der weiterhin roten Vollsuite ausdrücklich
keine globale Abnahme. `evidence/independent-review.json` bindet diese Beurteilung
an die geprüften Datei-Hashes. Der Lead übernimmt separat den Scope-Nachweis.
Angeforderte Reviewer-Laufzeit: `gpt-6-astra`, Reasoning `high`; tatsächliche
hostseitige Identitätsmetadaten sind dem Reviewer nicht exponiert, eine technische
Gate-Durchsetzung wird daher nicht behauptet. Keine menschliche Abnahme.

### Abschluss des Schreibgrenzen-Nachweises

`verify_scope.py` hat den Vergleich abgeschlossen und korrekt Exit 1 geliefert:
19.131 Dateien vorher, 19.132 nachher; zwei veränderte Dateien, eine neue,
keine entfernte. Unter dem gemeinsamen Präfix
`working-memory/evaluation/poc-tiered-reconcile-20261012/`:

* `README.md`: Dateizeitstempel/Größe verändert.
* `m1-bewertung/aufgaben-bewertung.md`: Dateizeitstempel/Größe verändert.
* `selector/RANK-VALIDATION.md`: neu während des Auftrags.

Diese Pfade wurden von keiner Schreiboperation dieses Auftrags adressiert;
ihre Herkunft ist nicht untersucht. Sie werden als beobachtete externe
Änderungen mit ungeklärter Zuordnung erhalten, nicht zurückgesetzt. Die globale
Aussage „alle Dateien außerhalb pipeline-v12 unverändert“ ist daher **nicht
nachgewiesen** und wird nicht als bestanden ausgegeben. Ein Wiederherstellen
dieser fremden Dateien wäre außerhalb der Schreibfreigabe.

Separat positiv belegt: Alle 67 im Kopiermanifest erfassten Release-Quellen bzw.
Hilfsdateien behalten ihre Ausgangs-SHA-256; alle fünf Bestands-Testkopien sind
bytegleich zur Herkunft; unter den kopierten Ausgangsdateien wurde ausschließlich
`backend/hybrid_pipeline.py` verändert. Die neue `candidate_filter.py` steht
zusätzlich daneben. Syntaxprüfungen der fünf eigenen Python-Dateien sind grün.
Vollständiger Zeitstempelvergleich: `evidence/scope-verification.json` und
`evidence/scope-verification-output.txt`; Hashbindung und unveränderte Baseline-
Fehlernamen: `evidence/validation-summary.json`.

Der erste PoC-Testlauf (`evidence/tests-attempt1.txt`: 59/66, 1 Failure und 6
Errors) lief noch mit einem falsch benannten synthetischen Query-Feld (`query`
statt des bestehenden Vertrags `text`). Das wurde ausschließlich in der neuen
Fixture korrigiert; außerdem wurde die synthetische Non-Compact-Lifecycle-
Abdeckung berichtigt. Dieser Lauf belegt die Filter-Unit-Tests, aber nicht die
betroffenen Pipeline-Integrationsfälle. Die Abschlusswiederholung prüft den
korrigierten Stand einschließlich inzwischen ergänzter Invarianten; kein
Baseline-Fehler wurde dadurch versteckt oder als bestanden umgedeutet.

Bekannte Risiken: Alte Aufgaben außerhalb des Rangs können fachlich relevant sein
und werden nicht geprüft; fehlerhafte/fehlende Daten oder zukünftige Datumswerte
vergrößern konservativ den Hot-Set. Suchreihenfolge bestimmt die Auswahl, der
Filter ist nur bei gleichen Eingaben deterministisch. Exakte ID-Substringtreffer
können unbeabsichtigt mehr behalten. Grenzwerte sind Produktkompromisse, deren
Realqualität und tatsächliche Kostenwirkung hier ungeprüft bleiben. Keine Live-
Durchsetzung eines Governance-Hooks wird behauptet; unabhängig geprüft wird
der konkrete lokale Stand, nicht ein Produktionsbetrieb.


## Änderungsstand 2026-10-13: Default A=30, k=5

Der begrenzte Folgeauftrag ist lokal validiert: Funktionsstandard, Env-Default,
30-Tage-Grenztest, Statistikerwartungen, Versionssuffix-Tests und Beispielwerte
sind angepasst. Der Rangstandard bleibt 5. Der neue Test
`FilterTests.test_25_day_lifecycle_at_rank_12_is_kept_at_30_but_dropped_at_21`
prüft Alter 25, nullbasierten Work-Suchrang 12 und leere exakte Nennungen.
Behalten bei A=30 (auch ohne expliziten Parameter), verworfen bei A=21;
Rang und exakte Nennung tragen in beiden Fällen nicht zur Aufnahme bei.

Aktuelle tatsächliche Läufe, jeweils mit `python3 -I -B`:

| Prüfung | Vorher bestanden/gesamt | Nachher bestanden/gesamt |
| --- | --- | --- |
| `run_tests.py legacy-full` | 38/48 | 38/48 |
| `run_tests.py acceptance` | 68/68 | 69/69 |
| Gezielte Filter-/Versions- und zwei angepasste Integrationstests | — | 23/23 |

Die zehn bekannten Vollsuite-Fehler sind nach vollständigem Testnamen und
Fehlerklasse identisch (6 Failures, 4 Errors), auch gegenüber dem ursprünglichen
PoC-Nachweis. Kein neuer Fehler. Vollausgaben:
`evidence/tests-age30-before-full.txt`, `evidence/tests-age30-after-full.txt`,
`evidence/tests-age30-before-acceptance.txt`,
`evidence/tests-age30-after-acceptance.txt`, `evidence/tests-age30-targeted.txt`.
`evidence/age30-validation.json` enthält Namenvergleich, Zähler, Hashbindung,
Parameter-/Versionsbefund und die quellengebundenen 64/64 bei 49,1 %.
`evidence/age30-default-scan.txt` belegt den abschließenden `rg`-Suchlauf:
kein veralteter Default 21 im aktuellen Code, Tests, Dokument oder Backend-Diff.
A=21 bleibt nur als expliziter Gegenfall oder historischer Vergleich erhalten.
`evidence/backend.diff` spiegelt die aktuellen Backend-Defaults wider;
`evidence/age30-change.diff` zeigt die Änderung vom historischen A=21-Stand.
Alte Testausgaben, Review-Hashes und die übrigen ursprünglichen Felder von
`evidence/validation-summary.json` bleiben historische Nachweise; dessen
`latest_validation` verweist auf den aktuellen Stand. Das frühere unabhängige
Review wurde nicht als Review dieser Folgeänderung ausgegeben.

Schreiboperationen dieses Folgeauftrags und temporäre synthetische Testdaten
lagen ausschließlich in `pipeline-v12/`. Keine Git-, Netzwerk/API/Server-,
Secret- oder Installationsoperation. Der historische breitere Scope-Befund wird
hier weder erneut geprüft noch aufgehoben. Kein Deployment oder Live-Nachweis.
Rückweg zum bisherigen aktiven Filterverhalten: lokal explizit
`DASHBOARD_HOTSET_AGE_DAYS=21` setzen; die dynamische Kennung bildet dann den
expliziten historischen Parameter ab. Filter vollständig deaktivieren wie oben.
