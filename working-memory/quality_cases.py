"""Eight predeclared cases, independent expected behavior; no paid LLM judge."""
CASES=[
 {'id':'clear_promise','difficulty':'easy','text':'Gleb: Ich sende Maria morgen den Monatsbericht.','tasks':1,'done':0,'due':'morgen'},
 {'id':'fact_no_action','difficulty':'easy','text':'Gleb: Der Monatsbericht enthält zwölf Tabellen.','tasks':0,'done':0},
 {'id':'paraphrase','difficulty':'medium','seed':[('Monatsbericht senden','Gleb: Ich sende Maria den Monatsbericht.')],'text':'Gleb: Die monatliche Auswertung ist jetzt per Mail bei Maria angekommen. Damit ist mein zugesagter Versand erledigt.','tasks':0,'done':1},
 {'id':'idea_prerequisite','difficulty':'medium','text':'Gleb: Wir könnten die Daten vielleicht migrieren. Dafür bräuchten wir erst eine Freigabe. Ich habe noch keine Umsetzung zugesagt.','tasks':0,'done':0},
 {'id':'event_not_deadline','difficulty':'medium','text':'Gleb: Ich versende die Einladung für den Austausch mit Maria. Das Treffen ist am Freitag um 10 Uhr; wann ich die Einladung versende, steht noch nicht fest.','tasks':1,'done':0,'due':None},
 {'id':'old_promise','difficulty':'hard','seed_date':'2025-01-10','seed':[('Abstimmung mit Maria organisieren','Gleb: Ich organisiere den Abstimmungstermin mit Maria zur Monatsauswertung.')],'text':'Gleb: Maria, wir sitzen heute wie von mir damals zugesagt zur Abstimmung der Monatsauswertung zusammen. Damit habe ich den Termin organisiert. Über die Datenfreigabe haben wir noch nicht entschieden.','tasks':0,'done':1},
 {'id':'same_topic_different_action','difficulty':'hard','seed':[('Monatsbericht senden','Gleb: Ich sende Maria den Monatsbericht.'),('Monatsbericht prüfen','Gleb: Ich prüfe die Zahlen im Monatsbericht.')],'text':'Gleb: Den Monatsbericht habe ich Maria wie zugesagt geschickt. Die Prüfung der Zahlen habe ich noch nicht erledigt.','tasks':0,'done':1},
 {'id':'partial_condition','difficulty':'hard','seed':[('Daten migrieren','Gleb: Sobald Maria und Tom freigeben, migriere ich die Daten.')],'condition':'Sobald Maria und Tom freigeben','text':'Gleb: Maria hat freigegeben. Toms Freigabe fehlt noch. Die Migration hat noch nicht begonnen.','tasks':0,'done':0,'condition_retained':True},
]
