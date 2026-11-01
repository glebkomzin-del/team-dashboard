# Unabhängige Offline-Abnahme: FLEX-RELEASE

Urteil: **ACCEPT für den vereinbarten Offlineumfang**, keine verbleibenden
Pflichtblocker. Frischer unabhängiger Read-only-Reviewer `/root/release_review`;
keine Umsetzung oder Delegation durch den Reviewer. Angefordert wurde eine
unabhängige Reviewer-Konfiguration; tatsächliches Modell/Reasoning wurde durch
die verfügbaren Host-Metadaten nicht bestätigt. Laufzeitdurchsetzung globaler
Governance-Gates wurde nicht eingerichtet oder behauptet.

Das erste Review fand einen Race zwischen Cancellation und Transportstart sowie
eine nicht ausreichend an die eigene Standardfrist gekoppelte Caller-Wartezeit.
Beide Befunde wurden synthetisch reproduziert; sie sperrten die Abnahme.

Die anschließende begrenzte Korrektur ordnet Deadlineprüfung, Versuchszulassung
und Abbruch über dieselbe Sperre (`openai_provider.py:339`). Der Caller wacht bei
der Standardzulassung auf und verwendet deren eigene Frist (`:319`). Der Reviewer
führte tatsächlich alle **16 Providertests** aus. Geprüft wurden insbesondere:

- Abbruch vor Zulassung: kein Request und null Flex-Versuche.
- Bereits zugelassener später sendender Versuch: Unknown, keine weitere Zulassung.
- Blockierter Standardstream: Caller beendet an seiner eigenen 420-s-Frist,
  obwohl die gemeinsame 480-s-Frist noch nicht abgelaufen ist.

Unveränderte Kosten-/Identitätsnachweise wurden übernommen. Beide Overlaydateien
entsprechen den geprüften Rootdateien. Der Lead führte den abschließenden
Gesamtlauf mit **31/31 Unittests** und **14/14 Offlineprüfungen** aus; die echten
Ausgaben stehen in `TEST-RESULTS.txt` und `OFFLINE-RESULTS.txt`.

Die dokumentierte Versuchszulassung ist eine technische Annahme des Pakets:
Bereits zugelassene Transporte können nach dem Caller-Timeout physisch senden
oder auslaufen. Sie sind Unknown und erlauben keinen neuen Versuch. Ein physischer
Abbruch oder eine Live-Lease-/Container-/Produktionsabnahme wird nicht behauptet.
Das lokale Versionsasset `{}` ist ausdrücklich ein Stub; der Containerprüfpfad
benötigt vollständige echte Ressourcen und verwendet diesen Stub nicht.

Produktionsmanifest fehlt lokal; `make_manifest.py` ist getestet, das Manifest
wurde nicht erfunden. Kein Build, Deployment oder echter Provideraufruf wurde
ausgeführt. Die akzeptierte lokale Paketversion ist Paket 1 mit Provider 444
Zeilen und Budget 121 Zeilen; die README nennt die Produktionsdiff-Zahlen.
