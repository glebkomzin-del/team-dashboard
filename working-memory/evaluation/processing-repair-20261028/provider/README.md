# Empfangsfehler: lokale Diagnosekorrektur

## Ergebnis

Der exakt exportierte Produktionsadapter verliert beim Empfang eines SSE-Fehlers
den technischen Fehlercode: Er wandelt das Ereignis in `ValueError` um und liefert
`provider_error_code: null`. Auch ein unvollständiger Stream und ein widersprüchlicher
Endstatus erscheinen nur als `ValueError`. Das ist offline reproduziert.

Die lokale Kandidatendatei `openai_provider.py` erhält ausschließlich eine endliche
Allowlist bekannter technischer Fehlercodes und ergänzt `stream_error_kind` mit
intern vergebenen Kategorien. Provider-Nachrichten, Parameterwerte und Rohereignisse
werden nicht gespeichert. Bisherige Fehlerklasse, leere Ausgabe, fehlende endgültige
Nutzung und Terminalstatus bleiben erhalten. Erfolgreiche Antworten bleiben identisch.
Retry-, Fallback- und Veröffentlichungsregeln wurden nicht erweitert.

## Änderungen

- `openai_provider.py`: Kopie von `../baseline/openai_provider.py`, ausschließlich
  sichere Zusatzdiagnose und Prüfung der Ereignis-/Terminalobjektform.
- `test_provider.py`: sechs Offline-Prüfungen mit künstlichen Daten und Netzwerkstub.
- `test-results.txt`: ausgeführter grüner Prüflauf.

Ponytail full: vorhandenen Adapter und Python-Standardbibliothek verwendet; keine
Abhängigkeiten ergänzt. Bekannte Aufrufer sind Standard-Request und Flex-Kette
derselben Datei. Beide verwenden `collect_stream`; der gemeinsame Ort wird korrigiert.

## Prüfung

```text
python3 -m unittest discover -s meeting-os/working-memory/evaluation/processing-repair-20261028/provider -p test_provider.py
```

Rot: Vor Änderung liefen fünf Tests gegen die unveränderte Produktionskopie;
vier scheiterten wegen fehlender `stream_error_kind`-Diagnose, der Erfolgstest bestand.
Grün: sechs Tests bestanden, Exit 0. Der zusätzliche Test über den vollständigen
Flex-Requestpfad bestätigt auch für `flex_unavailable` im Stream genau einen
Netzwerkstub-Aufruf und keinen Retry/Fallback.

Abgedeckt: Allowlist und Ausschluss unbekannter Codes/privater Meldungen,
unvollständiger Stream, Endstatuswiderspruch, ungültiges JSON, ungültige Ereignisform,
unveränderte erfolgreiche Antwort sowie kein zusätzlicher Versand.

## Grenzen / Offen

Die 22 vorhandenen gespeicherten Fehler enthalten keine ursprünglichen SSE-Ereignisse.
Ihr konkreter Auslöser bleibt nicht belegt; die Korrektur verbessert die nächste
Diagnose und repariert keine verlorenen Inhalte. Für die zwei Inhaltsprüfungsfehler
ist dieses Paket ebenfalls keine Reparatur.

Keine Zugangsdaten gelesen, kein Provideraufruf, kein Probe-Skript erstellt,
keine Serverdatei/Produktionsdaten geändert, kein Deploy und kein Commit.
Eine produktive Übernahme benötigt die Freigabe und Lead-Abnahme. Bereits gespeicherte
Antworten wurden nicht verändert und Quellen nicht erneut eingereiht.

Aufwand: Skill, zwei Baseline-Dateien beziehungsweise gezielte Ausschnitte
und Graphfundstellen gelesen; zwei Pythondateien plus Bericht/Prüfbeleg geschrieben.
Weitere Arbeit zur eigentlichen Wiederherstellung ist erforderlich.
