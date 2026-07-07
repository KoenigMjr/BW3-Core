# <center>Server/Client Prinzip</center>

BOSWatch 3 wurde als Server/Client Anwendung entwickelt.

Dies ermöglicht es, mehrere Empfangsstationen an einer Auswerte- und Verteilereinheit zu bündeln.

---
## BOSWatch Client

Der **BOSWatch Client** übernimmt den Empfang und die Dekodierung der Daten. Anschließend werden die Daten mittels der implementierten
Dekoder ausgewertet und in ein sogenanntes bwPacket verpackt.

Dieses Paket wird anschließend in einer Sende-Queue abgelegt. Nun werden Pakete aus der Queue an den BOSWatch Server per TCP-Socket
gesendet. Der Ansatz, Pakete statt sie direkt zu versenden vorher in einer Queue zwischen zu speichern, verhindert den Verlust von
Paketen, sollte die Verbindung zum Server einmal abreissen. Nach einer erfolgreichen Wiederverbindung können die wartenden Pakete nun
nachträglich an den Server übermittelt werden.

Dabei überwacht der Client selbstständig die benötigten Programme zum Empfang der Daten und startet diese bei einem Fehler ggf. neu.

![Client-Prinzip](../img/client.png){ .center }

---
## BOSWatch Server

Nachdem die Daten vom Clienten über die TCP-Socket Verbindung empfangen wurden, übernimmt der **BOSWatch Server** die weitere
Verarbeitung der Daten.

Auch hier werden die empfangenen Daten in Form von bwPackets in einer Queue abgelegt, um zu gewährleisten, dass auch während einer länger
dauernden Plugin Ausführung alle Pakete korrekt empfangen werden können und es zu keinen Verlusten kommt.
Die Verarbeitung der Pakete geschieht anschließend in sogenannten Routern, welche aufgrund ihres Umfangs jedoch in einem eigenen Kapitel
erklärt werden. Diese steuern die Verteilung der Daten an die einzelnen Plugins.

![Server-Prinzip](../img/server.png){ .center }