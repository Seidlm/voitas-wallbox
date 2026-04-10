# Voitas Wallbox — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Seidlm&repository=ha-voitas-wallbox&category=integration)
[![HA Version](https://img.shields.io/badge/Home%20Assistant-2025.1%2B-blue)](https://www.home-assistant.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-seidlm-FFDD00?style=flat&logo=buy-me-a-coffee&logoColor=black)](https://www.buymeacoffee.com/seidlm)
[![GitHub Stars](https://img.shields.io/github/stars/Seidlm/ha-voitas-wallbox?style=flat)](https://github.com/Seidlm/ha-voitas-wallbox/stargazers)
[![GitHub Downloads](https://img.shields.io/github/downloads/Seidlm/ha-voitas-wallbox/total?style=flat)](https://github.com/Seidlm/ha-voitas-wallbox/releases)
[![GitHub Issues](https://img.shields.io/github/issues/Seidlm/ha-voitas-wallbox?style=flat)](https://github.com/Seidlm/ha-voitas-wallbox/issues)

Local Home Assistant integration for the **Voitas V11 Wallbox** EV charger.

> ⚠️ **Background:** Voitas Innovations has ceased operations and their cloud infrastructure is largely offline. The official app no longer works. This integration bypasses the cloud entirely by listening to the **local UDP broadcast** that the wallbox transmits on your network — no internet connection required.

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

This integration listens for these broadcasts and exposes the data as Home Assistant entities. No polling, no cloud, no authentication required.

> **Note on charging power:** The UDP broadcast does not include the actual charging power in watts. To track energy consumption (kWh), you can either enter a fixed power value or connect a sensor from your car's HA integration (e.g. Audi, Volkswagen) that reports the live charging power.

---

## Features

- 📡 **Local push** — UDP broadcast, near real-time (~600ms), no polling
- 🔌 **Charging status** — `idle` / `charging`
- ⚡ **Charging power** — from a fixed kW value or any HA power sensor (e.g. your car)
- 🔋 **Energy (kWh)** — calculated via time integration, compatible with HA Energy Dashboard
- ⏱️ **Session duration** — minutes since charging started, resets when done
- 📊 **Last session summary** — duration + kWh of the previous charge stored as attributes
- 🏥 **Availability monitoring** — sensors go `unavailable` if no packet received for 30s
- 🔧 **Diagnostic sensor** — raw packet data and packet counter for debugging

---

## Installation via HACS

### One-click install

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Seidlm&repository=ha-voitas-wallbox&category=integration)

### Manual

1. In HACS → **Integrations** → ⋮ → **Custom repositories**
2. Add `https://github.com/Seidlm/ha-voitas-wallbox` → Category: **Integration**
3. Click **Download**
4. Restart Home Assistant
5. Go to **Settings → Devices & Services → + Add Integration → Voitas Wallbox**

---

## Setup

### Step 1 — Wallbox IP
Enter the local IP address of your Voitas V11 (e.g. `192.168.1.149`). The integration will listen for UDP broadcasts on port **43000** and verify connectivity before proceeding.

### Step 2 — Power Source

| Option | When to use |
|--------|-------------|
| **Manual (kW)** | Enter a fixed value matching your wallbox configuration (e.g. `11.0` kW) |
| **HA Entity** | Select a sensor from your car integration that reports live charging power in kW |

### Changing the power source later
Go to **Settings → Devices & Services → Voitas Wallbox → ⋮ → Configure**

---

## Entities

| Entity | Type | Unit | Description |
|--------|------|------|-------------|
| `binary_sensor.*_charging` | Binary Sensor | — | `on` when charging |
| `sensor.*_status` | Sensor | — | `idle` or `charging` |
| `sensor.*_charging_power` | Sensor | kW | Current charging power |
| `sensor.*_energy` | Sensor | kWh | Total energy (Energy Dashboard compatible) |
| `sensor.*_session_duration` | Sensor | min | Minutes since charging started |
| `sensor.*_max_power` | Sensor | kW | Wallbox max capacity *(disabled by default)* |
| `sensor.*_last_packet` | Diagnostic | — | Raw UDP data + packet count *(disabled by default)* |

### Last session attributes
After a charging session ends, the `status` sensor stores a summary:
- `last_session_duration_min`
- `last_session_energy_kwh`
- `last_session_start` / `last_session_end`

### Energy Dashboard
Add `sensor.*_energy` to your HA Energy Dashboard under **Individual devices**.

---

## Network requirements

- HA and the Voitas Wallbox must be on the **same network/VLAN**
- UDP port **43000** must not be blocked
- The wallbox must be connected via **WiFi or LAN**

---

## Troubleshooting

**"Cannot connect" during setup** → Check IP, wallbox powered on, UDP 43000 reachable

**Sensors show `unavailable`** → No UDP packet for 30s — check network connectivity

**Energy shows 0** → Configure a power source (manual kW or car entity in kW)

---

## Technical details

The Voitas V11 runs on an **Orange Pi Zero** (Debian 10). The UDP broadcast protocol was reverse-engineered since the official cloud (Voitas Innovations) is no longer functional. Modbus TCP is also available on port 502 per datasheet but requires app activation.

---

## Contributing

Found more protocol fields? Managed to enable Modbus? Open an issue or PR!

---

## License

MIT — see [LICENSE](LICENSE)

---

## Support

If this integration saved your wallbox from becoming a paperweight, consider buying me a coffee! ☕

[![Buy Me a Coffee](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/seidlm)

---

*Reverse-engineered with ❤️ for the Voitas community.*
