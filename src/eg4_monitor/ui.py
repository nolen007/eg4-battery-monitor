"""
Terminal UI for battery monitoring.
"""

import os
import sys
from typing import Optional

from .battery import BatteryData


class TerminalUI:
    """Terminal-based user interface for battery monitoring."""
    
    def __init__(self):
        self.update_count = 0
        self.mqtt_status = "Disconnected"
    
    @staticmethod
    def clear_screen():
        """Clear the terminal screen."""
        os.system('cls' if os.name == 'nt' else 'clear')
    
    @staticmethod
    def supports_unicode() -> bool:
        """Check if terminal supports Unicode."""
        try:
            return sys.stdout.encoding.lower().startswith('utf')
        except Exception:
            return False
    
    def _progress_bar(self, value: float, max_val: float, width: int = 20) -> str:
        """Create a text progress bar."""
        ratio = min(value / max_val, 1.0) if max_val > 0 else 0
        filled = int(ratio * width)
        empty = width - filled
        return f"[{'█' * filled}{'░' * empty}]"
    
    def render(self, data: BatteryData, mqtt_connected: bool):
        """Render the UI with current battery data."""
        self.update_count += 1
        self.mqtt_status = "🟢 Connected" if mqtt_connected else "🔴 Disconnected"
        modbus_status = "🟢 Online" if data.online else "🔴 Offline"
        
        self.clear_screen()
        
        # Header
        print("╔══════════════════════════════════════════════════════════════════╗")
        print("║          EG4 WALLMOUNT 280Ah BATTERY MONITOR                     ║")
        print("╠══════════════════════════════════════════════════════════════════╣")
        print(f"║  Time: {data.timestamp[:19]:<20}  Updates: {self.update_count:<10}    ║")
        print(f"║  MQTT: {self.mqtt_status:<20}  Modbus: {modbus_status:<15} ║")
        print("╠══════════════════════════════════════════════════════════════════╣")
        
        if not data.online:
            print("║                                                                  ║")
            print("║               ⚠️  BATTERY OFFLINE / NO CONNECTION                ║")
            print("║                                                                  ║")
            print("╚══════════════════════════════════════════════════════════════════╝")
            print("\n  Press Ctrl+C to exit")
            return
        
        # Alarms section
        if data.alarms:
            print("║  🚨 ALARMS:                                                      ║")
            for alarm in data.alarms:
                print(f"║     • {alarm:<57} ║")
            print("╠══════════════════════════════════════════════════════════════════╣")
        
        # Battery state with progress bars
        soc_bar = self._progress_bar(data.soc, 100)
        soh_bar = self._progress_bar(data.soh, 100)
        
        print("║  BATTERY STATE                                                   ║")
        print(f"║    SOC: {data.soc:5.1f}%  {soc_bar}                        ║")
        print(f"║    SOH: {data.soh:5.1f}%  {soh_bar}                        ║")
        print(f"║    Cycles: {data.cycle_count:<6}   Status: {data.status:<5}                        ║")
        print("╠══════════════════════════════════════════════════════════════════╣")
        
        # Electrical
        print("║  ELECTRICAL                                                      ║")
        print(f"║    Voltage:     {data.voltage:>7.2f} V                                    ║")
        print(f"║    Current:     {data.current:>+7.2f} A                                    ║")
        print(f"║    Power:       {data.power:>+7.1f} W                                    ║")
        print(f"║    Temperature: {data.temperature:>7.1f} °C                                   ║")
        print("╠══════════════════════════════════════════════════════════════════╣")
        
        # Capacity
        print("║  CAPACITY                                                        ║")
        print(f"║    Remaining:   {data.remaining_ah:>7.1f} Ah  /  {data.remaining_kwh:>6.2f} kWh               ║")
        print(f"║    Design:      {data.design_capacity:>7.0f} Ah                                   ║")
        print("╠══════════════════════════════════════════════════════════════════╣")
        
        # Cell voltages
        print("║  CELL VOLTAGES                                                   ║")
        if data.cell_voltages:
            for i in range(0, len(data.cell_voltages), 4):
                cells = data.cell_voltages[i:i+4]
                cell_str = "  ".join([f"C{i+j+1:02d}:{v:.3f}" for j, v in enumerate(cells)])
                print(f"║    {cell_str:<60} ║")
        print(f"║    Min: {data.cell_min:.3f}V  Max: {data.cell_max:.3f}V  Delta: {data.cell_delta:>5.1f}mV            ║")
        print("╠══════════════════════════════════════════════════════════════════╣")
        
        # Overall status
        if data.alarms:
            status = "🔴 ALARM"
        elif data.cell_delta > 30:
            status = "🟡 WARNING"
        else:
            status = "🟢 HEALTHY"
        
        print(f"║  STATUS: {status:<55} ║")
        print("╚══════════════════════════════════════════════════════════════════╝")
        print("\n  Press Ctrl+C to exit")


class HeadlessUI:
    """Minimal UI for headless/service operation."""
    
    def __init__(self):
        self.update_count = 0
    
    def render(self, data: BatteryData, mqtt_connected: bool):
        """Print a single status line."""
        self.update_count += 1
        
        status = "ALARM" if data.alarms else "OK"
        mqtt = "MQTT:OK" if mqtt_connected else "MQTT:ERR"
        
        print(
            f"[{data.timestamp[:19]}] "
            f"SOC:{data.soc:.0f}% "
            f"V:{data.voltage:.1f}V "
            f"I:{data.current:+.1f}A "
            f"T:{data.temperature:.0f}°C "
            f"Δ:{data.cell_delta:.0f}mV "
            f"{mqtt} "
            f"[{status}]"
        )
