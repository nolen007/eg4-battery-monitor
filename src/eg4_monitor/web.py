"""
Web GUI for EG4 Battery Monitor.
"""

import json
import logging
import threading
from datetime import datetime
from flask import Flask, render_template_string, jsonify

from .battery import BatteryData

logger = logging.getLogger(__name__)


# HTML Template with embedded CSS and JavaScript
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>EG4 Battery Monitor</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #eee;
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        
        header {
            text-align: center;
            margin-bottom: 30px;
        }
        
        header h1 {
            font-size: 2.5em;
            color: #00d4ff;
            text-shadow: 0 0 20px rgba(0, 212, 255, 0.3);
        }
        
        .status-bar {
            display: flex;
            justify-content: center;
            gap: 30px;
            margin-top: 10px;
            font-size: 0.9em;
            color: #888;
        }
        
        .status-indicator {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .status-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: #888;
        }
        
        .status-dot.online { background: #00ff88; box-shadow: 0 0 10px #00ff88; }
        .status-dot.offline { background: #ff4444; box-shadow: 0 0 10px #ff4444; }
        
        .dashboard {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
        }
        
        .card {
            background: rgba(255, 255, 255, 0.05);
            border-radius: 16px;
            padding: 24px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        
        .card h2 {
            font-size: 1.1em;
            color: #00d4ff;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }
        
        .big-number {
            font-size: 4em;
            font-weight: 700;
            text-align: center;
            color: #fff;
            line-height: 1;
        }
        
        .big-number .unit {
            font-size: 0.3em;
            color: #888;
            font-weight: 400;
        }
        
        .big-number.positive { color: #00ff88; }
        .big-number.negative { color: #ff6b6b; }
        
        .progress-container {
            margin-top: 20px;
        }
        
        .progress-bar {
            height: 20px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 10px;
            overflow: hidden;
        }
        
        .progress-fill {
            height: 100%;
            border-radius: 10px;
            transition: width 0.5s ease, background 0.5s ease;
        }
        
        .progress-fill.high { background: linear-gradient(90deg, #00ff88, #00d4ff); }
        .progress-fill.medium { background: linear-gradient(90deg, #ffaa00, #ff6b00); }
        .progress-fill.low { background: linear-gradient(90deg, #ff4444, #ff0000); }
        
        .stat-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 15px;
        }
        
        .stat-item {
            background: rgba(0, 0, 0, 0.2);
            padding: 15px;
            border-radius: 10px;
        }
        
        .stat-item .label {
            font-size: 0.8em;
            color: #888;
            margin-bottom: 5px;
        }
        
        .stat-item .value {
            font-size: 1.5em;
            font-weight: 600;
        }
        
        .cell-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 10px;
        }
        
        .cell {
            background: rgba(0, 0, 0, 0.3);
            padding: 12px 8px;
            border-radius: 8px;
            text-align: center;
            border: 2px solid transparent;
            transition: all 0.3s ease;
        }
        
        .cell.min { border-color: #ff6b6b; background: rgba(255, 107, 107, 0.1); }
        .cell.max { border-color: #00ff88; background: rgba(0, 255, 136, 0.1); }
        
        .cell .cell-num {
            font-size: 0.7em;
            color: #666;
            margin-bottom: 4px;
        }
        
        .cell .cell-voltage {
            font-size: 1.1em;
            font-weight: 600;
            font-family: 'Courier New', monospace;
        }
        
        .alarm-card {
            background: rgba(255, 68, 68, 0.1);
            border: 1px solid #ff4444;
        }
        
        .alarm-list {
            list-style: none;
        }
        
        .alarm-list li {
            padding: 10px;
            background: rgba(255, 68, 68, 0.2);
            border-radius: 8px;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .alarm-list li::before {
            content: "⚠️";
        }
        
        .no-alarms {
            text-align: center;
            color: #00ff88;
            padding: 20px;
        }
        
        .no-alarms::before {
            content: "✓ ";
        }
        
        .card.wide {
            grid-column: span 2;
        }
        
        @media (max-width: 768px) {
            .card.wide {
                grid-column: span 1;
            }
            
            .cell-grid {
                grid-template-columns: repeat(2, 1fr);
            }
            
            .big-number {
                font-size: 3em;
            }
        }
        
        .last-update {
            text-align: center;
            color: #666;
            margin-top: 20px;
            font-size: 0.85em;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🔋 EG4 Battery Monitor</h1>
            <div class="status-bar">
                <div class="status-indicator">
                    <div class="status-dot" id="modbus-status"></div>
                    <span>Modbus</span>
                </div>
                <div class="status-indicator">
                    <div class="status-dot" id="mqtt-status"></div>
                    <span>MQTT</span>
                </div>
            </div>
        </header>
        
        <div class="dashboard">
            <!-- SOC Card -->
            <div class="card">
                <h2>State of Charge</h2>
                <div class="big-number"><span id="soc">--</span><span class="unit">%</span></div>
                <div class="progress-container">
                    <div class="progress-bar">
                        <div class="progress-fill high" id="soc-bar" style="width: 0%"></div>
                    </div>
                </div>
            </div>
            
            <!-- Power Card -->
            <div class="card">
                <h2>Power</h2>
                <div class="big-number" id="power-display"><span id="power">--</span><span class="unit">W</span></div>
            </div>
            
            <!-- Electrical Stats -->
            <div class="card">
                <h2>Electrical</h2>
                <div class="stat-grid">
                    <div class="stat-item">
                        <div class="label">Voltage</div>
                        <div class="value"><span id="voltage">--</span> V</div>
                    </div>
                    <div class="stat-item">
                        <div class="label">Current</div>
                        <div class="value"><span id="current">--</span> A</div>
                    </div>
                    <div class="stat-item">
                        <div class="label">Temperature</div>
                        <div class="value"><span id="temperature">--</span> °C</div>
                    </div>
                    <div class="stat-item">
                        <div class="label">SOH</div>
                        <div class="value"><span id="soh">--</span> %</div>
                    </div>
                </div>
            </div>
            
            <!-- Capacity Stats -->
            <div class="card">
                <h2>Capacity</h2>
                <div class="stat-grid">
                    <div class="stat-item">
                        <div class="label">Remaining</div>
                        <div class="value"><span id="remaining_kwh">--</span> kWh</div>
                    </div>
                    <div class="stat-item">
                        <div class="label">Remaining Ah</div>
                        <div class="value"><span id="remaining_ah">--</span> Ah</div>
                    </div>
                    <div class="stat-item">
                        <div class="label">Design</div>
                        <div class="value"><span id="design_capacity">--</span> Ah</div>
                    </div>
                    <div class="stat-item">
                        <div class="label">Cycles</div>
                        <div class="value"><span id="cycle_count">--</span></div>
                    </div>
                </div>
            </div>
            
            <!-- Cell Voltages -->
            <div class="card wide">
                <h2>Cell Voltages (Min: <span id="cell_min">--</span>V | Max: <span id="cell_max">--</span>V | Delta: <span id="cell_delta">--</span>mV)</h2>
                <div class="cell-grid" id="cell-grid">
                    <!-- Cells will be populated by JavaScript -->
                </div>
            </div>
            
            <!-- Alarms -->
            <div class="card" id="alarm-card">
                <h2>Alarms</h2>
                <div id="alarm-container">
                    <div class="no-alarms">No active alarms</div>
                </div>
            </div>
        </div>
        
        <div class="last-update">
            Last updated: <span id="timestamp">--</span>
        </div>
    </div>
    
    <script>
        // Initialize cell grid
        const cellGrid = document.getElementById('cell-grid');
        for (let i = 1; i <= 16; i++) {
            const cell = document.createElement('div');
            cell.className = 'cell';
            cell.id = `cell-${i}`;
            cell.innerHTML = `
                <div class="cell-num">Cell ${i}</div>
                <div class="cell-voltage" id="cell-voltage-${i}">-.---</div>
            `;
            cellGrid.appendChild(cell);
        }
        
        function updateData() {
            fetch('/api/data')
                .then(response => response.json())
                .then(data => {
                    // Update status indicators
                    document.getElementById('modbus-status').className = 
                        'status-dot ' + (data.online ? 'online' : 'offline');
                    document.getElementById('mqtt-status').className = 
                        'status-dot ' + (data.mqtt_connected ? 'online' : 'offline');
                    
                    // Update main values
                    document.getElementById('soc').textContent = data.soc?.toFixed(1) || '--';
                    document.getElementById('soh').textContent = data.soh?.toFixed(1) || '--';
                    document.getElementById('voltage').textContent = data.voltage?.toFixed(2) || '--';
                    document.getElementById('current').textContent = data.current?.toFixed(2) || '--';
                    document.getElementById('power').textContent = data.power?.toFixed(0) || '--';
                    document.getElementById('temperature').textContent = data.temperature?.toFixed(1) || '--';
                    document.getElementById('remaining_kwh').textContent = data.remaining_kwh?.toFixed(2) || '--';
                    document.getElementById('remaining_ah').textContent = data.remaining_ah?.toFixed(1) || '--';
                    document.getElementById('design_capacity').textContent = data.design_capacity?.toFixed(0) || '--';
                    document.getElementById('cycle_count').textContent = data.cycle_count || '--';
                    
                    // Update SOC bar
                    const socBar = document.getElementById('soc-bar');
                    const soc = data.soc || 0;
                    socBar.style.width = soc + '%';
                    socBar.className = 'progress-fill ' + (soc > 50 ? 'high' : soc > 20 ? 'medium' : 'low');
                    
                    // Update power display color
                    const powerDisplay = document.getElementById('power-display');
                    const power = data.power || 0;
                    powerDisplay.className = 'big-number ' + (power > 0 ? 'negative' : power < 0 ? 'positive' : '');
                    
                    // Update cell voltages
                    document.getElementById('cell_min').textContent = data.cell_min?.toFixed(3) || '--';
                    document.getElementById('cell_max').textContent = data.cell_max?.toFixed(3) || '--';
                    document.getElementById('cell_delta').textContent = data.cell_delta?.toFixed(1) || '--';
                    
                    if (data.cell_voltages && data.cell_voltages.length > 0) {
                        const minV = Math.min(...data.cell_voltages);
                        const maxV = Math.max(...data.cell_voltages);
                        
                        data.cell_voltages.forEach((voltage, i) => {
                            const cellEl = document.getElementById(`cell-${i + 1}`);
                            const voltageEl = document.getElementById(`cell-voltage-${i + 1}`);
                            
                            voltageEl.textContent = voltage.toFixed(3);
                            
                            // Highlight min/max cells
                            cellEl.className = 'cell';
                            if (voltage === minV) cellEl.className += ' min';
                            if (voltage === maxV) cellEl.className += ' max';
                        });
                    }
                    
                    // Update alarms
                    const alarmContainer = document.getElementById('alarm-container');
                    const alarmCard = document.getElementById('alarm-card');
                    
                    if (data.alarms && data.alarms.length > 0) {
                        alarmCard.className = 'card alarm-card';
                        alarmContainer.innerHTML = '<ul class="alarm-list">' + 
                            data.alarms.map(a => `<li>${a}</li>`).join('') + '</ul>';
                    } else {
                        alarmCard.className = 'card';
                        alarmContainer.innerHTML = '<div class="no-alarms">No active alarms</div>';
                    }
                    
                    // Update timestamp
                    document.getElementById('timestamp').textContent = 
                        data.timestamp ? new Date(data.timestamp).toLocaleString() : '--';
                })
                .catch(error => {
                    console.error('Error fetching data:', error);
                    document.getElementById('modbus-status').className = 'status-dot offline';
                });
        }
        
        // Initial update and set interval
        updateData();
        setInterval(updateData, 5000);  // Update every 5 seconds
    </script>
</body>
</html>
"""


class WebServer:
    """Flask web server for battery monitoring GUI."""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 5000):
        self.host = host
        self.port = port
        self.app = Flask(__name__)
        self.data: BatteryData = BatteryData()
        self.mqtt_connected: bool = False
        self._thread = None
        
        # Register routes
        self.app.add_url_rule('/', 'index', self._index)
        self.app.add_url_rule('/api/data', 'api_data', self._api_data)
        
        # Disable Flask logging in production
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.WARNING)
    
    def _index(self):
        """Serve the main dashboard page."""
        return render_template_string(HTML_TEMPLATE)
    
    def _api_data(self):
        """Return current battery data as JSON."""
        data = self.data.to_dict()
        data['mqtt_connected'] = self.mqtt_connected
        return jsonify(data)
    
    def update_data(self, data: BatteryData, mqtt_connected: bool = False):
        """Update the current battery data."""
        self.data = data
        self.mqtt_connected = mqtt_connected
    
    def start(self):
        """Start the web server in a background thread."""
        self._thread = threading.Thread(
            target=self._run_server,
            daemon=True
        )
        self._thread.start()
        logger.info(f"Web server started at http://{self.host}:{self.port}")
    
    def _run_server(self):
        """Run the Flask server."""
        self.app.run(
            host=self.host,
            port=self.port,
            debug=False,
            use_reloader=False,
            threaded=True
        )
    
    def stop(self):
        """Stop the web server."""
        # Flask doesn't have a clean shutdown, but the daemon thread will exit
        logger.info("Web server stopping")
