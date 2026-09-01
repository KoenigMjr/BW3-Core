# <center>MQTT</center> 
---

## Beschreibung
Mit diesem Plugin ist es möglich, Alarmierungen als JSON-Nachricht an einen MQTT-Broker zu veröffentlichen. Das Paket wird dabei vollständig übernommen (alle Felder, auch die von vorgeschalteten Modulen wie Descriptor, Geocoding oder Multicast hinzugefügten) und muss nicht einzeln konfiguriert werden.

Um Nachrichtenverluste bei einem kurzzeitig nicht erreichbaren Broker zu vermeiden, sendet das Plugin nicht direkt, sondern über eine interne Warteschlange (Queue) mit eigenem Sende-Thread. Ist der Broker nicht erreichbar, bleiben Nachrichten in der Queue gepuffert und werden nach Wiederverbindung automatisch nachgeliefert. Erst wenn die Queue voll ist, wird das älteste gepufferte Paket verworfen (mit Logeintrag).

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
|clientId|MQTT Client-ID, mit der sich das Plugin am Broker anmeldet|boswatch|
|username|Benutzername für die Broker-Authentifizierung (optional)|leer|
|password|Passwort für die Broker-Authentifizierung (optional)|leer|
|qos|MQTT Quality of Service für den Versand (0, 1 oder 2)|0|
|retain|Ob die Nachricht beim Broker als "retained message" gespeichert werden soll|false|
|keepalive|MQTT Keepalive-Intervall in Sekunden|60|
|statusTopic|Optionales Topic für Online/Offline-Status (Last Will and Testament)|leer (deaktiviert)|
|queueSize|Maximale Anzahl gepufferter Nachrichten bei fehlender Verbindung|200|
|maxRetries|Anzahl der Sendeversuche pro Nachricht, bevor sie verworfen wird|5|
|initialDelay|Initiale Wartezeit zwischen Sendeversuchen in Sekunden|2|
|maxDelay|Maximale Wartezeit zwischen Sendeversuchen in Sekunden (exponentielles Backoff)|60|

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

### statusTopic (Last Will and Testament)
Wird `statusTopic` gesetzt, veröffentlicht das Plugin dort:

- `online` (retained), sobald die Verbindung zum Broker steht
- `offline` (retained), beim regulären Beenden von BOSWatch
- `offline` (retained), automatisch durch den Broker selbst, falls die Verbindung unsauber abbricht (Last Will)

Damit lässt sich die Erreichbarkeit des BOSWatch-Systems zuverlässig überwachen, ohne auf einen reinen Timeout angewiesen zu sein.

### Warteschlange und Zustellverhalten
Nachrichten werden nicht sofort und blockierend gesendet, sondern in eine interne Queue (`queueSize`) eingereiht und von einem eigenen Thread sequentiell abgearbeitet:

- Bei fehlender Verbindung bleibt eine Nachricht gepuffert und wird nach Wiederverbindung automatisch zugestellt.
- Schlägt ein Sendeversuch fehl, wird die Nachricht mit exponentiellem Backoff (`initialDelay` bis `maxDelay`) bis zu `maxRetries`-mal erneut versucht.
- Ist die Queue voll, wird die **älteste** gepufferte Nachricht verworfen, damit aktuelle Alarme nicht hinter veralteten Nachrichten blockiert werden. Dies wird im Log vermerkt.
- Beim Beenden von BOSWatch versucht das Plugin für maximal 5 Sekunden, die Queue noch zu leeren (Graceful Shutdown), bevor verbleibende Nachrichten verworfen werden.

---
## Modul Abhängigkeiten
- keine

---
## Externe Abhängigkeiten
- paho-mqtt
