# <center>WebSocket</center> 
---

## Beschreibung
Mit diesem Plugin ist es möglich, Alarmierungen über eine dauerhafte (persistente) WebSocket-Verbindung zu versenden. Im Gegensatz zum HTTP-Plugin bleibt die Verbindung zum Server offen, was eine deutlich schnellere Datenübertragung ermöglicht.

Das Plugin arbeitet asynchron in einem eigenen Hintergrund-Thread. Dadurch wird der Hauptprozess von BOSWatch nicht blockiert, falls das Netzwerk langsam ist oder der Server kurzzeitig nicht antwortet. Zudem verfügt es über einen automatischen Wiederverbindungs-Mechanismus mit "Exponential Backoff".

**Besonderheit:** Das Plugin extrahiert automatisch alle verfügbaren Felder aus dem `bwPacket`. Somit werden auch Felder übertragen, die durch zusätzliche Module (z. B. GPS-Daten oder Textersetzungen) hinzugefügt wurden.

## Unterstütze Alarmtypen
- Fms
- Pocsag
- Zvei
- Msg

## Resource
`websocket`

## Konfiguration
|Feld|Beschreibung|Default|
|----|------------|-------|
|**url**|Ziel-URL des WebSocket-Servers (z. B. ws://10.0.0.1:8765)|**Erforderlich**|
|**max_retries**|Maximale Anzahl an Reconnect-Versuchen (0 = unendlich)|0|
|**initial_delay**|Erste Wartezeit in Sekunden bei Verbindungsverlust|2.0|
|**max_delay**|Maximale Wartezeit in Sekunden zwischen Versuchen|60.0|

**Beispiel:**
```yaml
  - type: plugin
    name: WebSocket Plugin
    res: websocket
    config:
      url: "ws://192.168.178.50:8080/alarme"
      max_retries: 0
      initial_delay: 2.0
      max_delay: 30.0
```

## Datenausgabe (Beispiel JSON Payload)
Die Daten werden als valides JSON-Objekt gesendet. Die Felder entsprechen den internen Namen des BOSWatch-Pakets:
```json
{
  "mode": "pocsag",
  "timestamp": "29.03.2026 19:15:01",
  "ric": "1234567",
  "subric": "1",
  "message": "Einsatz fuer die Feuerwehr...",
  "serverName": "BOSWatch-Zentrale",
  "alarm_type_plugin": "POCSAG"
}
```

---
## Modul Abhängigkeiten
- keine

---
## Externe Abhängigkeiten
- asyncio
- websockets