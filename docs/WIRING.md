# Wiring Guide

This guide explains how to connect your EG4 WallMount 280Ah battery to a Waveshare RS485-to-Ethernet adapter.

## Hardware Required

- EG4 WallMount Indoor 280Ah Battery
- Waveshare RS485 TO ETH (B) adapter (or similar)
- RJ45 cable (CAT5/5e/6)
- 9-24V DC power supply for Waveshare adapter

## RJ45 Pinout

The EG4 battery uses RS485 communication on pins 1 and 2 of the RJ45 "Battery-Comm" port.

### T568B Color Code

| Pin | Color        | Function    |
|-----|--------------|-------------|
| 1   | White/Orange | RS485 A (+) |
| 2   | Orange       | RS485 B (-) |
| 3   | White/Green  | Not used    |
| 4   | Blue         | Not used    |
| 5   | White/Blue   | Not used    |
| 6   | Green        | Not used    |
| 7   | White/Brown  | Not used    |
| 8   | Brown        | Not used    |

## Wiring Connections

### EG4 Battery to Waveshare Adapter

```
EG4 Battery (RJ45)              Waveshare Terminal
═══════════════════             ══════════════════
Pin 1 (White/Orange) ─────────► 485A (A+)
Pin 2 (Orange)       ─────────► 485B (B-)
```

### Waveshare Adapter Setup

1. Connect power (9-24V DC) to the power terminals
2. Connect Ethernet cable to your network
3. Configure the adapter's IP address via web interface (default: 192.168.1.200)

## DIP Switch Configuration

On the EG4 battery, set the DIP switches for address 1:

```
DIP Switch:  1   2   3   4   5   6
Position:   ON  OFF OFF OFF OFF OFF
```

This sets the Modbus device ID to 1.

## Protocol Settings

On the battery's LCD screen:
1. Press Settings
2. Select RS485
3. Select P01-EG4 protocol
4. Restart the BMS

## Troubleshooting

### No Communication

1. **Swap A and B wires** - Polarity may be reversed on some adapters
2. **Check baud rate** - EG4 default is 9600, 8N1
3. **Verify IP address** - Ensure you're connecting to the correct adapter IP
4. **Check DIP switches** - Device ID must be set correctly

### Intermittent Connection

1. Add 120Ω termination resistor if cable is long (>10m)
2. Check for loose connections
3. Ensure adequate power to the Waveshare adapter

## Network Diagram

```
┌─────────────────┐      RJ45 Cable      ┌───────────────────┐
│                 │  (Pins 1,2 only)     │                   │
│   EG4 Battery   │─────────────────────►│  Waveshare RS485  │
│   WallMount     │                      │   to ETH Adapter  │
│                 │                      │                   │
└─────────────────┘                      └─────────┬─────────┘
                                                   │
                                                   │ Ethernet
                                                   │
                                         ┌─────────▼─────────┐
                                         │                   │
                                         │  Network Switch   │
                                         │                   │
                                         └─────────┬─────────┘
                                                   │
                                    ┌──────────────┼──────────────┐
                                    │              │              │
                              ┌─────▼─────┐  ┌─────▼─────┐  ┌─────▼─────┐
                              │           │  │           │  │           │
                              │  Server   │  │   Home    │  │  Other    │
                              │ (Monitor) │  │ Assistant │  │  Devices  │
                              │           │  │           │  │           │
                              └───────────┘  └───────────┘  └───────────┘
```
