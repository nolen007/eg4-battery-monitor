"""
Terminal UI for battery monitoring.
"""

import os
import sys
from typing import Optional, List

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
    
    def _render_battery(self, data: BatteryData) -> List[str]:
        """Render a single battery's data."""
        lines = []
        
        modbus_status = "🟢 Online" if data.online else "🔴 Offline"
        lines.append(f"║  {data.name:<30}  {modbus_status:<20}  ║")
        lines.append("╠══════════════════════════════════════════════════════════════════╣")
        
        if not data.online:
            lines.append("║               ⚠️  BATTERY OFFLINE / NO CONNECTION                ║")
            return lines
        
        # Alarms
        if data.alarms:
            lines.append("║  🚨 ALARMS:                                                      ║")
            for alarm in data.alarms:
                lines.append(f"║     • {alarm:<57} ║")
        
        # Battery state with progress bars
        soc_bar = self._progress_bar(data.soc, 100)
        
        lines.append(f"║  SOC: {data.soc:5.1f}%  {soc_bar}   V: {data.voltage:5.2f}V   I: {data.current:+6.2f}A  ║")
        lines.append(f"║  Power: {data.power:+7.1f}W   Temp: {data.temperature:5.1f}°C   Remaining: {data.remaining_kwh:5.2f}kWh  ║")
        lines.append(f"║  Cells: {data.cell_min:.3f}V - {data.cell_max:.3f}V  Δ{data.cell_delta:4.0f}mV   Cycles: {data.cycle_count:<6}   ║")
        
        return lines
    
    def render(self, batteries: List[BatteryData], mqtt_connected: bool):
        """Render the UI with current battery data."""
        self.update_count += 1
        self.mqtt_status = "🟢 Connected" if mqtt_connected else "🔴 Disconnected"
        
        self.clear_screen()
        
        # Header
        print("╔══════════════════════════════════════════════════════════════════╗")
        print("║              EG4 MULTI-BATTERY MONITOR                           ║")
        print("╠══════════════════════════════════════════════════════════════════╣")
        
        timestamp = batteries[0].timestamp[:19] if batteries else "--"
        print(f"║  Time: {timestamp:<20}  Updates: {self.update_count:<10}    ║")
        print(f"║  MQTT: {self.mqtt_status:<20}  Batteries: {len(batteries):<13} ║")
        print("╠══════════════════════════════════════════════════════════════════╣")
        
        # Render each battery
        for i, data in enumerate(batteries):
            if i > 0:
                print("╠══════════════════════════════════════════════════════════════════╣")
            for line in self._render_battery(data):
                print(line)
        
        # Summary
        print("╠══════════════════════════════════════════════════════════════════╣")
        
        online_count = sum(1 for b in batteries if b.online)
        total_kwh = sum(b.remaining_kwh for b in batteries if b.online)
        total_power = sum(b.power for b in batteries if b.online)
        alarm_count = sum(b.alarm_count for b in batteries)
        
        print(f"║  TOTALS: {online_count}/{len(batteries)} online   {total_kwh:6.2f} kWh   {total_power:+8.1f} W          ║")
        
        if alarm_count > 0:
            print(f"║  STATUS: 🔴 {alarm_count} ALARM(S) ACTIVE                                   ║")
        else:
            print("║  STATUS: 🟢 ALL SYSTEMS HEALTHY                                   ║")
        
        print("╚══════════════════════════════════════════════════════════════════╝")
        print("\n  Press Ctrl+C to exit")


class HeadlessUI:
    """Minimal UI for headless/service operation."""
    
    def __init__(self):
        self.update_count = 0
    
    def render(self, batteries: List[BatteryData], mqtt_connected: bool):
        """Print a single status line per battery."""
        self.update_count += 1
        
        mqtt = "MQTT:OK" if mqtt_connected else "MQTT:ERR"
        
        for data in batteries:
            status = "ALARM" if data.alarms else "OK"
            print(
                f"[{data.timestamp[:19]}] "
                f"{data.name}: "
                f"SOC:{data.soc:.0f}% "
                f"V:{data.voltage:.1f}V "
                f"I:{data.current:+.1f}A "
                f"T:{data.temperature:.0f}°C "
                f"Δ:{data.cell_delta:.0f}mV "
                f"{mqtt} "
                f"[{status}]"
            )
