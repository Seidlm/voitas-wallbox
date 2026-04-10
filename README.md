# Voitas Wallbox â€” Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Seidlm&repository=Voitas-Wallbox-HA-Integration&category=integration)
[![HA Version](https://img.shields.io/badge/Home%20Assistant-2025.1%2B-blue)](https://www.home-assistant.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-seidlm-FFDD00?style=flat&logo=buy-me-a-coffee&logoColor=black)](https://www.buymeacoffee.com/seidlm)
[![GitHub Stars](https://img.shields.io/github/stars/Seidlm/Voitas-Wallbox-HA-Integration?style=flat)](https://github.com/Seidlm/Voitas-Wallbox-HA-Integration/stargazers)
[![GitHub Downloads](https://img.shields.io/github/downloads/Seidlm/Voitas-Wallbox-HA-Integration/total?style=flat)](https://github.com/Seidlm/Voitas-Wallbox-HA-Integration/releases)
[![GitHub Issues](https://img.shields.io/github/issues/Seidlm/Voitas-Wallbox-HA-Integration?style=flat)](https://github.com/Seidlm/Voitas-Wallbox-HA-Integration/issues)

Local Home Assistant integration for the **Voitas V11 Wallbox** EV charger.

> âš ï¸ **Background:** Voitas Innovations has ceased operations and their cloud infrastructure is largely offline. The official app no longer works. This integration bypasses the cloud entirely by listening to the **local UDP broadcast** that the wallbox transmits on your network â€” no internet connection required.

---

## How it works

The Voitas V11 broadcasts a status packet every ~600ms on **UDP port 43000** to the local network:

```
WALLBOX-LD 3 <device-uuid> <status> <f4> <max_power_w> <min_current_ma> <interval_ms>
```

**Example:**
```
WALLBOX-LD 3 74c777d2-807e-4a9f-ba83-d606130065f3 charging 0 20000 2000 600
```

This integration listens for these broadcasts and exposes the data as Home Assistant entities. No polling, no cloud, no authentication required â€” it just works as long as your HA instance is on the same network as the wallbox.

> **Note on charging power:** The UDP broadcast does not include the actual charging power in watts. To track energy consumption (kWh), you can either enter a fixed power value (e.g. your wallbox's configured limit) or connect a sensor from your car's HA integration (e.g. Audi, Volkswagen, Hyundai) that reports the live charging power.

---

## Features

- ðŸ“¡ **Local push** â€” UDP broadcast, near real-time (~600ms), no polling
- ðŸ”Œ **Charging status** â€” `idle` / `charging`
- âš¡ **Charging power** â€” from a fixed kW value or any HA power sensor (e.g. your car)
- ðŸ”‹ **Energy (kWh)** â€” calculated via time integration, compatible with HA Energy Dashboard
- â±ï¸ **Session duration** â€” minutes since charging started, resets when done
- ðŸ“Š **Last session summary** â€” duration + kWh of the previous charge stored as attributes
- ðŸ¥ **Availability monitoring** â€” sensors go `unavailable` if no packet received for 30s
- ðŸ”§ **Diagnostic sensor** â€” raw packet data and packet counter for debugging

---

## Installation via HACS

### One-click install

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Seidlm&repository=Voitas-Wallbox-HA-Integration&category=integration)

### Manual

1. In HACS â†’ **Integrations** â†’ â‹® â†’ **Custom repositories**
2. Add `https://github.com/Seidlm/Voitas-Wallbox-HA-Integration` â†’ Category: **Integration**
3. Click **Download**
4. Restart Home Assistant
5. Go to **Settings â†’ Devices & Services â†’ + Add Integration â†’ Voitas Wallbox**

---

## Setup

### Step 1 â€” Wallbox IP
Enter the local IP address of your Voitas V11 (e.g. `192.168.1.149`). The integration will listen for UDP broadcasts on port **43000** and verify connectivity before proceeding.

### Step 2 â€” Power Source
Choose how the charging power is determined:

| Option | When to use |
|--------|-------------|
| **Manual (kW)** | Enter a fixed value matching your wallbox configuration (e.g. `11.0` kW) |
| **HA Entity** | Select a sensor from your car integration that reports live charging power in kW |

Using an actual car sensor gives you precise kWh calculations. The Audi, Volkswagen, and other car integrations typically expose a `sensor.*_charging_power` entity.

### Changing the power source later
Go to **Settings â†’ Devices & Services â†’ Voitas Wallbox â†’ â‹® â†’ Configure**

---

## Entities

| Entity | Type | Unit | Description |
|--------|------|------|-------------|
| `binary_sensor.*_charging` | Binary Sensor | â€” | `on` when charging |
| `sensor.*_status` | Sensor | â€” | `idle` or `charging` |
| `sensor.*_charging_power` | Sensor | kW | Current charging power |
| `sensor.*_energy` | Sensor | kWh | Total energy (session, resets on HA restart) |
| `sensor.*_session_duration` | Sensor | min | Minutes since charging started |
| `sensor.*_max_power` | Sensor | kW | Wallbox max capacity *(disabled by default)* |
| `sensor.*_last_packet` | Diagnostic | â€” | Raw UDP data + packet count *(disabled by default)* |

### Last session attributes
After a charging session ends, the `status` sensor stores a summary:
- `last_session_duration_min` â€” how long it took
- `last_session_energy_kwh` â€” how much was charged
- `last_session_start` / `last_session_end` â€” timestamps

### Energy Dashboard
Add `sensor.*_energy` to your HA Energy Dashboard under **Individual devices**.

---

## Network requirements

- Home Assistant and the Voitas Wallbox must be on the **same network/VLAN**
- UDP port **43000** must not be blocked by a firewall between them
- The wallbox must be connected via **WiFi or LAN**

---

## Troubleshooting

**Integration setup fails / "Cannot connect"**
â†’ Make sure the IP is correct, the wallbox is powered on and connected to your network, and that UDP port 43000 is reachable from your HA host.

**Sensors show `unavailable`**
â†’ No UDP packet received for 30 seconds. Check network connectivity. The wallbox broadcasts continuously when powered.

**Energy shows 0**
â†’ Make sure a power source is configured. If using a car entity, check that the entity reports values in **kW** (not W).

**Charging power shows 0 while charging**
â†’ The wallbox status shows `charging` but power is 0 because the car hasn't started drawing power yet, or the configured entity is unavailable.

---

## Technical details

The Voitas V11 runs on an **Orange Pi Zero** (Debian 10). The UDP broadcast protocol was reverse-engineered since the official cloud infrastructure (AWS WebSocket backend) is no longer functional following Voitas Innovations' closure. The wallbox also has Modbus TCP (port 502) support per its datasheet (PN-EN IEC 61851-1), but it appears to require activation via the now-defunct app.

---

## Contributing

Found more fields in the protocol? Managed to enable Modbus? Open an issue or PR!

---

## License

MIT â€” see [LICENSE](LICENSE)

---

*Reverse-engineered with â¤ï¸ for the Voitas community.*

---

## Support

If this integration saved your wallbox from becoming a paperweight, consider buying me a coffee! â˜•

[![Buy Me a Coffee](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/seidlm)

