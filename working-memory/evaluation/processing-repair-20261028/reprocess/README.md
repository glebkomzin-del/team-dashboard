# Reguläre Neuverarbeitung der 22 Quellen

Auftrag: „Nein, jagge die 22 Quellen durch die Pipeline ganz normal.“
Genau die Originale in `../audit/private/reprocess22-targets.json`; unveränderte
Produktionsmodelle, Tarifpolitik, `CanonicalWorker.schema`, `processor.process`,
Recherche, Prüfungen und Zusammenfassung. Keine synthetischen Providerproben.

## Korrektur des tatsächlich aufgetretenen 32er-Blockers

Der erste Adapter benutzte den auf 32 Belege beschränkten manuellen
`bounded_recovery_generation`-Kostenweg. Eine kurze Quelle wurde damit übernommen.
Bei a409 wurden ein Modellaufruf und 31 Embeddingantworten vollständig gespeichert;
Aufruf 33 wurde vor dem Provider gestoppt. Diese bekannten Antworten werden nicht
neu angefordert. Der richtige bestehende Weg für die Vollpipeline ist das normale
`wm_model_calls`-Ledger mit `wm_reserve_call`/`wm_receive_call` und Grenze 1023.
Keine Tabellen-/Funktions-/Schemaänderung und keine aggregierten Scheinbelege.

## Expliziter Owner-Neulauf und dauerhafte Historie

`claim` bindet einen vollständigen Neulauf mit einer serialisierbaren Transaktion:
Raum und Auftrag werden gesperrt, Zieloriginal, Hash und ursprünglicher Stand
geprüft. Eine unveränderliche `wm_job_decisions`-Zeile mit `action=retry`,
`execution_path=owner_full_reprocess_standard_ledger`, ursprünglichem Auftrag,
Eigentümer und eindeutigem Befehl hält die ausdrückliche Beauftragung fest.
Die vorhandene Frontend-Schnellwiederholungsregel wird dabei nicht als erfüllt
behauptet: Es handelt sich um den ausdrücklich angeforderten vollständigen Neulauf
mit historischem Vorgängerstand und anschließender chronologischer Generation.
Der Auftrag erhält normale Pipelinebindung, laufenden Zustand und einen Lease.

Der Startindex wird **vor** jedem Import im Datenbankaudit fest eingefroren.
Nach Import der Slots 1–32 bleibt er deshalb 1, nicht 33. Wiederaufnahme liest
denselben auditierten Lauf; fremder Lease, geänderte Originale, Kontext oder
Pipeline stoppen. Alte Modellaufrufe und Originale werden nicht verändert.

`import` prüft vorhandene Antworten numerisch: exakte JSON-Kodierung, Request- und
Responsehash, Modell, Kosten und Kontext müssen stimmen. Normale Reserve-/Receive-
Funktionen registrieren diese Antworten ohne einen Provideraufruf. Anschließend
nutzt jeder neue Aufruf dieselben Funktionen vor Versand beziehungsweise nach
Antwort. Der normale Kosten-/Budgetvertrag ist maßgeblich; keine doppelte lokale
Verbrauchsaddition. Eine gespeicherte, aber unbestätigte Reservierung löst niemals
nochmals einen Send aus. Ein vorhandener Antwortkörper darf nachgereicht werden.

Private Prompts, Antworten, Archivkopie und Vorschau liegen im registrierten
`worker-reprocess22`-Cache. Dauerhafte Reservierungs-/Hash-/Kostenmetadaten ohne
Originaltext liegen getrennt daneben. Entfernte Antwortkörper stoppen sicher.
Die frühere Request-Serialisierung mit Scope-Literal `bounded_recovery_generation`
bleibt ausschließlich für Hashkompatibilität der schon bezahlten Antworten erhalten;
die Quellenprovenienz heißt jetzt `owner_full_reprocess_standard_ledger`, enthält
normale Slotverweise und keine manuelle Recovery-Belegliste.

## Speicherung und Bedienung durch den Lead

Hold: fünf bereits geprüfte Containerflags `READ_ONLY=1`, `AUTOMATIC=0`,
`INTAKE=0`, `QA=0`, `ORIGINAL_DELETION=0`. **Für normale Reservierungen muss die
Datenbankkonfiguration `enabled=true` sein.** Die abgeschalteten Worker und der
Lesemodus verhindern dabei konkurrierende normale Verarbeitung/Handänderungen.
Der Adapter ändert diese Betriebseinstellungen nicht selbst.

```text
python3 meeting-os/working-memory/evaluation/processing-repair-20261028/reprocess/run.py claim --job a40913ae --execute
python3 meeting-os/working-memory/evaluation/processing-repair-20261028/reprocess/run.py import --job a40913ae --execute
python3 meeting-os/working-memory/evaluation/processing-repair-20261028/reprocess/run.py one --job a40913ae --execute
python3 meeting-os/working-memory/evaluation/processing-repair-20261028/reprocess/run.py all --execute
```

`claim` und `import` sind getrennte Schritte ohne Modellgenerierung. `one`/`all`
beanspruchen fehlende Läufe selbst und importieren bekannte Antworten idempotent.
Bereits bestätigte Übernahmen werden übersprungen. Eine bekannte Antwort kann
mehrfach als `paid_call_received` im Ablauf erscheinen; das ist kein erneuter
Provideraufruf. Maßgeblich sind die eindeutigen normalen Ledger-Slots.

Die unveränderte Vollpipeline läuft am chronologischen Vorgängerstand. Die
anschließende vollständige Generation erhält spätere Quellen und persönliche
Entscheidungen. In **einer** serialisierbaren Transaktion: Lease-/Stand-/Original-
prüfung, `wm_pause_job(context_changed)`, Archivnotiz, Generation vormerken und
annehmen. Bei Fehler rollt auch das Pausieren zurück. Ein echter Pipelinefehler
wird separat mit normalem Pausengrund festgehalten. Kein blindes Zurücksetzen.

## Ausgeführte Nachweise und Grenzen

15 Offline-Tests, Exit 0, einschließlich echtem Runtime-Generationsvertrag:
32 bekannte Antworten ohne Provider numerisch importieren; alter Ledgerbereich
unverändert; Wiederaufnahme mit Startindex 1; regulärer Aufruf 33 möglich;
Slot 1023 zulässig, 1024 vorher gesperrt; `send=false` ohne Antwort niemals senden;
Crash nach Antwort vor Beleg; Originaldatenpurge; Kosten-/Hashabweichung; normale
Budgetgrenze; Owner-Audit-/Startindexbindung; Pause und Annahme in einer Transaktion;
Tmpfs-Codeübertragung und Originalschutz. Syntaxprüfung aller fünf Dateien grün.
Rohbeleg: `normal-ledger-tests.txt` enthält ausschließlich synthetische Testdaten.

Kein Provideraufruf, keine produktive Änderung und kein Commit durch diesen
Umsetzer. Der Lead führt Claim/Import aus und liest vor weiterem Versand alle
32 normalen Slots samt Hashes/Kosten zurück. Ein realer vollständiger Erfolg aller
22 Quellen wird damit noch nicht behauptet. Grober Aufwand: fünf Paketdateien,
vorhandene SQL-Verträge und gezielte Runtimequellen gelesen; vier operative
Dateien und zugehörige Tests/Bericht angepasst. Keine neue Abhängigkeit.

## Genau ein weiterer Vollversuch nach geprüfter Inhaltsablehnung

Bei Quelle `f09befd7` wurde ein regulär geliefertes Gate-Ergebnis korrekt
abgelehnt: Eine Gesprächszeit ist keine neue Frist der referenzierten
Einladungsaufgabe. Das Ergebnis verband dennoch `date_changed` mit
`due_role=event_time`. Die Schutzprüfung bleibt unverändert. Der normale
Schnellretry ist ohne vorbereitetes Ergebnis gesperrt und wird nicht benutzt.
Die konkrete Inhaltsprüfung und die unabhängige Planprüfung erlauben genau
einen neuen vollständigen normalen Versuch im bereits autorisierten 22er-Auftrag.

`reviewed-preflight` ist vollständig lesend: auch keine Skriptübertragung oder
Cacheanlage, auch bei Unterprozessfehlern keine Diagnosedatei. Der anschließende Claim prüft denselben Stand unter Sperren erneut.
Fest gebunden sind Quelle/Originalhash, Revision 354, der frühere Ownerbefehl,
Fehlerzeit `2026-10-28T19:00:16.227267+00:00`, unveränderte Pipeline, der genaue
Request-/Responsehash von Gate-Aufruf 66 und alle 67 bestätigten alten Antworten.
Ein ungeklärter Aufruf sperrt den ersten neuen Claim. Der deterministische neue
Ownerbefehl erhält eine neue Lease, Startindex 67 und eigene Versuchspfade.

```text
python3 meeting-os/working-memory/evaluation/processing-repair-20261028/reprocess/run.py reviewed-preflight --job f09befd7
python3 meeting-os/working-memory/evaluation/processing-repair-20261028/reprocess/run.py reviewed-claim --job f09befd7 --execute
python3 meeting-os/working-memory/evaluation/processing-repair-20261028/reprocess/run.py reviewed-one --job f09befd7 --execute
python3 meeting-os/working-memory/evaluation/processing-repair-20261028/reprocess/run.py all --execute
```

Wiederaufnahme benutzt denselben neuen Befehl und erhöht Versuche nicht erneut.
Ein weiterer abgeschlossener Inhaltsfehler sperrt diesen Weg; er erzeugt keinen
dritten Vollneulauf. Modelle, Prompts, Schemas und Validatoren ändern sich nicht.
Die alten Antworten, Reservierungen und Fehlerdateien bleiben erhalten. Neue
Antworten/Status/Archivkopie liegen unter `worker-reprocess22/<Quelle>/attempts/<Befehl>`;
dauerhafte Metadaten analog unter `reprocess22-reservations/<Quelle>/attempts/<Befehl>`.
Nur das erstmals erfolgreiche `prepared.json` bleibt für die bestehende atomare
Übernahme am bisherigen Quellenpfad. Die alte Fehlerdatei dort ist Historie.

Die Abschlussprüfung liest Aufrufe per `EXISTS` statt eines vervielfachenden
Joins. Sie ordnet jeden Aufruf genau einem Bereich zu: erster Vollversuch 1–66,
neuer Versuch ab 67. Alle Kosten einschließlich des abgelehnten Versuchs und
alle rekursiv gesammelten Einzelbelege werden genau einmal geprüft.

Umsetzerprüfung: **21 Tests bestanden, Exit 0** mit
`python3 -B -m unittest discover -s meeting-os/working-memory/evaluation/processing-repair-20261028/reprocess -p test_reprocess.py`.
Zusätzliche Fälle: lesendes Preflight ohne Schreibanweisung/Diagnosedatei bei Fehlern, eingefrorene
Fehlstand-/Hashbindung, gleicher neuer Befehl bei Wiederaufnahme, Sperre eines
weiteren Inhaltsfehlers, Index 67 und unveränderte alte Historie, getrennte
Versuchspfade sowie eindeutige Kostenbereiche mit Ablehnung von Lücken/Duplikaten.
Syntax aller sechs Pythondateien und Audit-Selbstprüfung: PASS, Exit 0; ohne `--execute` sperrt `reviewed-one` vor SSH (erwartet Exit 2).
SQL-Guards sind nur als erzeugter Vertrag geprüft; echte lesende SQL-Vorprüfung und Ausführung: Lead.

Keine Produktmutation, kein KI-Aufruf und kein Commit durch diesen Umsetzer.
Geändert: `run.py`, `remote.py`, `container_worker.py`, `test_reprocess.py`,
dieser Bericht sowie `../audit/reprocess22-final.py`. `paid_calls.py` bleibt
unverändert. Grober Aufwand: sechs gezielt gelesene Paketdateien, sechs geändert;
keine neue Abhängigkeit. Offen: Lead-Vorprüfung/Abnahme und tatsächliches Ergebnis
des neuen Versuchs samt restlichen sieben Quellen und Betriebswiederherstellung.

## Genau ein Tokenlimit-Neulauf für Quelle 16

Planreview PASS; tatsächliche Ursache separat belegt: Quelle `9266439f`, Stand355,
Slot1, bekannter Abschluss `incomplete/max_output_tokens` mit finaler Nutzung
29.115 Eingabe-/24.000 Ausgabetokens. Die bereits verbuchten 149.115 µUSD bleiben
unverändert, ebenso der alte Slot0. Originalhash und Fehlerzeit
`2026-10-28T19:49:05.965092+00:00` sowie Request-/Responsehash sind eingefroren.

Der vorhandene `reviewed-preflight/claim/one`-Weg enthält genau einen zweiten
festgelegten Fall, keine allgemeine Wiederholungsfreigabe. Neuer Ownerbefehl,
Lease und Versuchscache sind deterministisch an diesen Fehlerstand gebunden;
Startindex2, Versuche2→3. Wiederaufnahme verwendet denselben Versuch. Ein neuer
bekannter Tokenabbruch sperrt bereits im SQL-Guard die erneute Wiederaufnahme;
ungeklärte Reservierungen führen niemals zu erneutem Versand. Quelle15 und ihre
unveränderte Bindung/Versuchspfade bleiben erhalten.

`PaidCalls` vergleicht beim ersten Modellaufruf den **ursprünglichen**, noch nicht
veränderten Requesthash mit dem genau gespeicherten Extraktionsrequest. Nur dann
ändert es `max_tokens` von24.000 auf48.000, vor neuem Requesthash, Reservierung und
Provideraufruf. Prompt, Schema, Modell und Tarifpolitik bleiben unverändert.
Falsche Quelle, Revision, Startindex, Hash oder Ausgabebudget stoppen vor Versand.
Der tatsächliche größere Kontext wird nochmals konservativ gegen die bestehenden
220.000 Zeichen/1.050.000 Tokens geprüft. Anschließende Stufen erhalten ihre
ursprünglichen Ausgabelimits. Die normale Budgetfunktion reserviert tatsächlich
48.000 Ausgabetokens; ein dafür nicht ausreichendes Projektbudget stoppt vorher.

Der Abschlussprüfer zählt die getrennten Bereiche1..1 und2..n genau einmal,
prüft den alten bekannten Preis149.115, die neue48k-Anforderung ausschließlich
an Index2 und die Bindung im Owneraudit. Erfindet keine vollständige Antwort aus
dem abgeschnittenen Ergebnis. Alle Inhalts-, Original- und Generationsprüfungen
bleiben unverändert; keine Produktdatei, kein Image und kein SQL-Schema geändert.

Bedienung durch den Lead nach Ergebnisabnahme:

```text
python3 meeting-os/working-memory/evaluation/processing-repair-20261028/reprocess/run.py reviewed-preflight --job 9266439f
python3 meeting-os/working-memory/evaluation/processing-repair-20261028/reprocess/run.py reviewed-one --job 9266439f --execute
```

Ausgeführt durch diesen Umsetzer:26 Offline-Tests Exit0 (einschließlich aller
21 vorherigen), Syntaxprüfung der sechs Pythondateien und Audit-Selbstprüfung
Exit0. Tests: exakter Prehash, tatsächliche48k-Reservierung/Send-/Requestbindung,
Wiederaufnahme ohne zweiten Versand, falsche Quelle/Revision/Startindex/Hash,
Kontextgrenze, ungenügendes48k-Budget, ungeklärte Antwort ohne Resend, getrennte
Versuchsbereiche und bekannte Tokenfehlerkosten genau einmal. Nur die notwendige
produktionsseitige Metadatenabfrage wurde READ ONLY ausgeführt; keine KI-Aufrufe,
keine produktive Mutation, kein Commit. Echter48k-Erfolg und alle22 Quellen sind
weiterhin durch den Lead zu prüfen.

Aufwand: sechs vorhandene Paketdateien gezielt geändert, keine neue Abhängigkeit.
Offen: frisches Ergebnisreview, reale Vorprüfung, Ausführung und Gesamtabnahme.

Rohbeleg der betroffenen Prüfung (synthetisch, ohne Netzwerk):

```text
python3 -m unittest discover -s meeting-os/working-memory/evaluation/processing-repair-20261028/reprocess -p 'test_*.py'
Ran 26 tests in 0.214s
OK
Exit 0
```

## Fortsetzung desselben Versuchs mit exakter Kontextzählung

Frischer Prüfer: **neuer-ansatz PASS**, keine fachliche Planänderung. Quelle16
bleibt auf Revision355, Versuch3 und Ownerbefehl`e9a2a394-dab8-5585-b7ee-7570223ac4b8`.
Alle123 bekannten Antworten2–124 (167049µUSD) bleiben unverändert. Der neue
Continuation-Vermerk hat einen anderen `execution_path`, keine neue Fullrun-
Kostenrange und keinen weiteren Versuch. Eingefroren: Fehlerzeit20:18:07.253703,
Metadatenhash`c0ae6f2c…`, Original und vollständige Pipelinebindung.

Der getrennte Offline-Capture belegt compact-0:968641Promptbytes+30139Schemabytes+
4096Reserve+59736normaleAusgabetokens=1062612; die konservative Obergrenze liegt
12612 über1050000. Prompt-/Schemahash und sämtliche ersten Requestmaße sind
fest gebunden. Keine Kandidaten-/Katalogkürzung, kein Modell-/Prompt-/Tarifwechsel.
Nur in diesem isolierten Operatorprozess dürfen normale compact-* Stufen den
vorhandenen exakten Inputzähler nutzen:Count+4096+vollerOutput muss<=1050000 sein.
Derselbe Count wird nach exaktem Requesthash privat gespeichert und im normalen
Kostenreserveweg wiederverwendet. Wiederaufnahme nutzt bekannte Counts/Antworten;
neue Generierung frühestensIndex125. Die installierten Produktdateien bleiben gleich.

Zählausfall ist `ContextCountUnavailable`/`transport_failed` ohne Generierung und
technisch wiederaufnehmbar; tatsächliche Überschreitung ist `budget_exceeded`.
Eine neue Inhaltsablehnung bleibt `validation_failed` und ist durch den alten
Continuation-Vermerk ausdrücklich nicht freigegeben. Beide neuen Fehlertypen
melden `generation_sent=false`. Alle123 alten Belege werden vor Freigabe geprüft.

Lead-Befehle nach frischer Ergebnisabnahme:
```text
python3 meeting-os/working-memory/evaluation/processing-repair-20261028/reprocess/run.py context-preflight --job 9266439f
python3 meeting-os/working-memory/evaluation/processing-repair-20261028/reprocess/run.py context-one --job 9266439f --execute
```
`context-preflight` bleibt auch bei Fehlern vollständig lesend. Der Schlussprüfer
liest Continuation/Countbelege separat, prüft den exakten Count im Reservebeleg
und die unveränderte123-Antworten-Präfixsumme; Fullrunbereiche bleiben1..1/2..n.

Ausgeführt:32 Offline-Tests (alle26 vorherigen), Exit0, Syntax sechs Dateien plus
beider eingebetteten Auditprogramme, Audit-Selbstprüfung Exit0. Rohkurzbeleg:
`Ran 32 tests / OK`. Geprüft:Scope-/Captureabweichung vorCount, exakte
Kontextgrenze, Countausfall/Überschreitung ohneReserve/Send, identischerCount für
Reserve, Wiederaufnahme ohneCount-/Generierungswiederholung, lesende Fehlerpfade
und Sperre einer neuen Inhaltsablehnung. Erster Lauf enthielt zwei korrigierte
Testharnessfehler (falscherBase64-Slot und doppelt geladene Klassentypen).
Keine Provider-/TokenCount-Ausführung, produktive Mutation, Deploy oder Commit.
Nur notwendige Metadaten/zulässige Pausegründe wurden READ ONLY gelesen.

Geändert:sechs Pythondateien und dieser Bericht; kein neuer Fremdcode/Abhängigkeit.
Offen:frisches Ergebnisreview, echte lesende Vorprüfung, tatsächliche Fortsetzung
und Gesamtabnahme aller22Quellen sowie ursprünglicheBetriebseinstellungen. Die
Materialisierung bleibt unverändert; der zusätzliche SQLite-Fastpath wurde verworfen.
