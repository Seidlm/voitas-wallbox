# Voitas Wallbox — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

Local integration for the **Voitas V11 Wallbox** EV charger via its UDP broadcast protocol (port 43000). Works fully **offline** — no cloud required.

> ⚠️ Voitas Innovations is no longer active. This integration was reverse-engineered from the local UDP protocol broadcast by the wallbox.

---

## Features

- 🔌 **Charging status** — idle / charging
- ⚡ **Charging power** — manual kW value or from any HA entity (e.g. your car's charging sensor)
- 🔋 **Energy (kWh)** — calculated via time integration, compatible with HA Energy Dashboard
- 📡 **Local push** — UDP broadcast, no polling, near real-time (~600ms)
- 🏠 **No cloud** — works even though Voitas servers are offline

---

## Installation via HACS

1. In HACS → **Integrations** → ⋮ → **Custom repositories**
2. Add `https://github.com/Seidlm/Voitas-Walbox-HA-Integration` as **Integration**
3. Install **Voitas Wallbox**
4. Restart Home Assistant
5. Go to **Settings → Devices & Services → Add Integration → Voitas Wallbox**

---

## Setup

### Step 1: Wallbox IP
Enter the local IP address of your Voitas V11 (e.g. `192.168.1.149`).

The integration will listen for UDP broadcasts on port **43000**.

### Step 2: Charging Power Source

| Option | Description |
|--------|-------------|
| **Manual (kW)** | Enter a fixed value (e.g. `11.0` for 11kW) |
| **HA Entity** | Select a sensor that reports charging power in kW (e.g. from Audi, Volkswagen, or other car integrations) |

Using an actual car sensor gives you accurate kWh calculations.

---

## Entities

| Entity | Type | Description |
|--------|------|-------------|
| `binary_sensor.voitas_wallbox_charging` | Binary Sensor | `on` when charging |
| `sensor.voitas_wallbox_status` | Sensor | `idle` or `charging` |
| `sensor.voitas_wallbox_charging_power` | Sensor (kW) | Current charging power |
| `sensor.voitas_wallbox_energy` | Sensor (kWh) | Total energy delivered (resets on HA restart) |

### Energy Dashboard
Add `sensor.voitas_wallbox_energy` to your Energy Dashboard under **Individual devices**.

---

## UDP Protocol

The Voitas V11 broadcasts on UDP port 43000 every ~600ms:

```
WALLBOX-LD <proto> <uuid> <status> <f4> <max_power_w> <min_current_ma> <interval_ms>
```

Example:
```
WALLBOX-LD 3 74c777d2-807e-4a9f-ba83-d606130065f3 charging 0 20000 2000 600
```

| Field | Value | Meaning |
|-------|-------|---------|
| 0 | `WALLBOX-LD` | Device type |
| 1 | `3` | Protocol version |
| 2 | UUID | Device identifier |
| 3 | `idle`/`charging` | Current status |
| 4 | `0` | Unknown |
| 5 | `20000` | Max power (W) |
| 6 | `2000` | Min current (mA) |
| 7 | `600` | Broadcast interval (ms) |

---

## Troubleshooting

**No data received:**
- Make sure HA and the Wallbox are on the same network/VLAN
- Check that UDP port 43000 is not blocked by a firewall
- The Wallbox must be powered on and connected to WiFi/LAN

---

## Contributing

Found more fields in the protocol? Open an issue or PR!

---

*Reverse-engineered with ❤️ — for the Voitas community.*
