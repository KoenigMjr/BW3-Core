# <center>MQTT</center> 
---

## Beschreibung
Mit diesem Plugin ist es möglich, Alarmierungen als JSON-Nachricht an einen MQTT-Broker zu veröffentlichen. Das Paket wird dabei vollständig übernommen (alle Felder, auch die von vorgeschalteten Modulen wie Descriptor, Geocoding oder Multicast hinzugefügten) und muss nicht einzeln konfiguriert werden.

Das Plugin sendet nicht direkt, sondern über eine interne Warteschlange (Queue) mit eigenem Sende-Thread. Ist der Broker nicht erreichbar, bleiben Nachrichten in der Queue gepuffert und werden nach der Wiederverbindung in der ursprünglichen Reihenfolge nachgeliefert. Erst wenn die Queue voll ist, wird das älteste gepufferte Paket verworfen (mit Logeintrag).

Zusätzlich unterstützt das Plugin einen optionalen Status-Topic nach dem MQTT-Standardmuster "Last Will and Testament" (LWT): Beim Verbindungsaufbau wird `online` veröffentlicht, bei sauberem Beenden von BOSWatch sowie im Falle eines unsauberen Verbindungsabbruchs (z.B. Absturz des Hosts) meldet der Broker selbstständig `offline`. Das eignet sich für Verfügbarkeits-Automatisierungen und Dashboards (z.B. Home Assistant).

## Unterstützte Alarmtypen
- Fms
- Pocsag
- Zvei
- Msg

## Resource
`mqtt`

## Konfiguration
|Feld|Beschreibung|Default|
|----|------------|-------|
|brokerAddress|IP-Adresse oder Hostname des MQTT-Brokers (Pflichtfeld)||
|brokerPort|Port des MQTT-Brokers|1883|
|topic|Ziel-Topic für die Alarme, unterstützt Wildcards (siehe unten)|boswatch/alarm|
|clientId|MQTT Client-ID, mit der sich das Plugin am Broker anmeldet. Muss pro Verbindung eindeutig sein (siehe unten)|boswatch-\<Hostname\>|
|username|Benutzername für die Broker-Authentifizierung (optional)|leer|
|password|Passwort für die Broker-Authentifizierung (optional)|leer|
|qos|MQTT Quality of Service für den Versand (0, 1 oder 2), siehe unten|0|
|retain|Ob die Nachricht beim Broker als "retained message" gespeichert werden soll|false|
|keepalive|MQTT Keepalive-Intervall in Sekunden|60|
|statusTopic|Optionales Topic für Online/Offline-Status (Last Will and Testament)|leer (deaktiviert)|
|queueSize|Maximale Anzahl gepufferter Nachrichten bei fehlender Verbindung|200|
|maxRetries|Anzahl der Wiederholungen, wenn der MQTT-Client eine Nachricht ablehnt (z.B. weil sein interner Puffer voll ist). Gilt nicht für fehlende Verbindung oder ausbleibende Bestätigung|5|
|initialDelay|Initiale Wartezeit zwischen diesen Wiederholungen in Sekunden|2|
|maxDelay|Maximale Wartezeit zwischen diesen Wiederholungen in Sekunden (exponentielles Backoff)|60|

**Beispiel:**
```yaml
  - type: plugin
    name: MQTT Plugin
    res: mqtt
    config:
      brokerAddress: 192.168.178.27
      brokerPort: 1883
      topic: "boswatch/{MODE}/alarm"
      clientId: bw3-server
      statusTopic: "boswatch/status"
      qos: 1
      retain: false
```

### topic
Das Topic kann feste Bestandteile mit BOSWatch-Wildcards kombinieren (siehe [BOSWatch Paket](../develop/packet.md)-Dokumentation), z.B.:

```yaml
topic: "boswatch/{MODE}/alarm"
```
Ergibt je nach Alarmtyp z.B. `boswatch/pocsag/alarm` oder `boswatch/fms/alarm`.

**Hinweis zu Multicast:** Bei einem Multicast-Alarm entsteht pro Empfänger ein eigenes Paket, und damit pro Empfänger eine eigene MQTT-Nachricht (bei `{RIC}` im Topic jeweils auf einem eigenen Topic). Alle diese Pakete tragen dieselbe Empfängerliste. Soll ein Empfänger der MQTT-Nachrichten nur **eine** Nachricht pro Alarm erhalten, muss das im Router gefiltert werden (z.B. auf den Multicast-Index, wie bei der Telegram-Route), oder der Empfänger muss die Nachrichten selbst zusammenfassen.

### clientId
Der Broker erlaubt pro Client-ID nur eine Verbindung. Meldet sich ein zweiter Client mit derselben ID an, trennt der Broker den ersten. Beide verbinden sich daraufhin immer wieder neu, was zu Wiederholungen von Nachrichten führen kann. Laufen mehrere BOSWatch-Instanzen (oder andere Programme) am selben Broker, muss jede eine eigene `clientId` verwenden. Ohne Angabe wird `boswatch-<Hostname>` verwendet.

### statusTopic (Last Will and Testament)
Wird `statusTopic` gesetzt, veröffentlicht das Plugin dort:

- `online` (retained), sobald die Verbindung zum Broker steht
- `offline` (retained), beim regulären Beenden von BOSWatch
- `offline` (retained), automatisch durch den Broker selbst, falls die Verbindung unsauber abbricht (Last Will)

Damit lässt sich die Erreichbarkeit des BOSWatch-Systems zuverlässig überwachen, ohne auf einen reinen Timeout angewiesen zu sein.

### Warteschlange und Zustellverhalten
Nachrichten werden nicht sofort und blockierend gesendet, sondern in eine interne Queue (`queueSize`) eingereiht und von einem eigenen Thread nacheinander abgearbeitet. Dabei gilt: **Jede Nachricht hat zu jedem Zeitpunkt genau einen Besitzer.**

- **Das Plugin ist Besitzer**, solange der MQTT-Client die Nachricht nicht übernommen hat. Bei fehlender Verbindung bleibt sie in der Queue und wird nach der Wiederverbindung zugestellt. Die Reihenfolge bleibt dabei erhalten. Das Warten zählt nicht als fehlgeschlagener Versuch.
- **Der MQTT-Client (paho-mqtt) ist Besitzer**, sobald er die Nachricht übernommen hat. Bei QoS 1 und 2 sendet er sie nach einem Verbindungsabbruch selbstständig erneut. Das Plugin sendet eine solche Nachricht **nie ein zweites Mal**, auch dann nicht, wenn die Bestätigung des Brokers ausbleibt. Das wird im Log vermerkt ("message stays with the MQTT client ... NOT sending it again").
- Lehnt der MQTT-Client eine Nachricht ab (z.B. interner Puffer voll), wird sie mit exponentiellem Backoff (`initialDelay` bis `maxDelay`) bis zu `maxRetries`-mal wiederholt und danach mit Logeintrag verworfen. Ein ungültiges Topic (z.B. mit nicht ersetzten Wildcards `+` oder `#`) wird sofort verworfen, da eine Wiederholung nichts ändern würde.
- Ist die Queue voll, wird die **älteste** gepufferte Nachricht verworfen, damit aktuelle Alarme nicht hinter veralteten Nachrichten blockiert werden. Dies wird im Log vermerkt.
- Beim Beenden von BOSWatch versucht das Plugin für maximal 5 Sekunden, die Queue noch zu leeren (Graceful Shutdown), und wartet danach kurz auf offene Bestätigungen des Brokers. Was dann noch nicht gesendet ist, wird mit Logeintrag verworfen.

**Zustellgarantie je nach `qos`:**

|qos|Garantie|Auswirkung|
|---|--------|----------|
|0|keine|Nachrichten, die in eine bereits abgerissene Verbindung geschrieben wurden, gehen verloren. Während eines erkannten Ausfalls werden sie aber gepuffert.|
|1|mindestens einmal|Es geht keine Nachricht verloren, die der MQTT-Client übernommen hat. Fällt die Bestätigung des Brokers aus, kann der Empfänger **in seltenen Fällen dieselbe Nachricht doppelt** erhalten. Das ist bei QoS 1 vom MQTT-Standard so vorgesehen.|
|2|genau einmal|Aufwändigstes Verfahren, verhindert auch diese Duplikate zwischen Plugin und Broker.|

Empfänger, für die ein doppelter Alarm unerwünscht ist, sollten daher identische Nachrichten innerhalb weniger Sekunden selbst zusammenfassen.

---
## Modul Abhängigkeiten
- keine

---
## Externe Abhängigkeiten
- paho-mqtt
