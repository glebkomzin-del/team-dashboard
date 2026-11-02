# <Name>

Vorlage, kein angelegter Funktionsstand und keine Freigabe. Die Hauptsession übergibt
die ausgefüllten Felder an funktion.py anlegen; das Skript erzeugt die Funktionsdatei.
Maschinenstand und Autorisierung niemals aus dieser Vorlage ableiten.

## Vertrag
Ziel, Nutzen, Nicht-Umfang, Abnahmekriterien, Kosten: noch offen.

## Einstufung
klein oder gross anhand der Wirkungsliste, mit Begründung.

## Vereinbarungen
Quelle ist die Diskussion oder Glebs datierte Aussage, niemals der Plan selbst.
Jede aktive Zeile braucht Aufgaben mit Kriterium und einem Argumentvektor als Prüfbefehl.

```json
[{"id":"v1","vereinbarung":"Gewünschtes Ergebnis","quelle":"Gleb JJJJ-MM-TT: Wortlaut",
  "aufgaben":["t1"],"gestrichen":false}]
```

Streichen erhält die Zeile mit `gestrichen: true` und
`gleb_aussage: {"datum":"JJJJ-MM-TT","verweis":"Glebs Änderung"}`.
Änderungen der Vereinbarungen erfordern eine neue Freigabe.

## Plan
JSON-Felder für funktion.py anlegen: id, title, type, goal, contract, scope,
packages, integration_command, vereinbarungen. Genau ein Besitzer je Bereich.

```json
[{"id":"p1","scope":["src"],"tasks":[
  {"id":"t1","criterion":"Beobachtbares Ergebnis","command":["python3","-m","unittest"]}]}]
```

## Verlauf
Vom Skript erzeugt; Prüfläufe, Freigaben und Urteile liegen im externen Zustandsordner.
