# Einmalige Aufteilung der bestehenden 15-EUR-Obergrenze

09.09.2026, vor dem vollständigen v11-Vergleich. Keine neue Nutzerfreigabe und kein neues Gesamtbudget: Die bereits freigegebenen höchstens 15 EUR für den Gesamtauftrag gelten weiter.

- Gemeinsames Testledger unverändert weiterführen. Vor dem langen Vergleich: 9,874432 USD einschließlich 1,652205 USD ungeklärter, weiterhin vollständig reservierter Nutzung.
- Standard-Testdeckel bleibt 10 USD. Nur der explizite lange Vergleich darf mit `--ceiling-micro-usd 11500000` die ausgewiesene Reparaturreserve mitbenutzen. Kein automatisches Nachfüllen; maximaler expliziter Testdeckel 11,50 USD.
- Bereits bestehender Produktionsdeckel 8,878649 USD bleibt unverändert. Davon sind 6,620629 USD historische Nutzung vor diesem Gesamtauftrag; maximal 2,258020 USD für den hier gezählten Wiederanlauf.
- Somit höchstens 13,758020 USD Gesamtmodellkosten dieses Auftrags einschließlich aller noch möglichen Reservierungen. Beim zuletzt veröffentlichten EZB-Kurs vom 08.09.2026 (1 EUR = 1,1614 USD) sind das rund 11,85 EUR netto beziehungsweise 14,10 EUR mit vorsorglich 19 Prozent Steueraufschlag. Die restlichen rund 0,90 EUR bleiben Wechselkurs-/Abrechnungspuffer.
- Quelle Wechselkurs: https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml . Dies ist eine Kontrolle zu aufgezeichneten Listenpreisen, keine Anbieterrechnung.
- Für neue v11-Textaufrufe zählt der offizielle Responses-Tokenzählendpunkt denselben Originalinput und dasselbe Ausgabeschema. Zur gezählten Eingabe kommen 4096 Sicherheitstokens; vollständige maximale Ausgabe, mögliche Cache-Schreibkosten und Long-Context-Aufschläge werden weiterhin reserviert. Fehlende Zählung verhindert Generierung. Keine Schätzung mit Zeichen/4.
- Unveränderte bezahlte Extraktion und Embeddings werden weiterverwendet. Keine zweite Luna-Serie nach dem beobachteten Qualitätsfehler. Der lange Lauf veröffentlicht nichts.
