FROM python:3.11-slim

LABEL maintainer="Your Name <your.email@example.com>"
LABEL description="EG4 WallMount 280Ah Battery Monitor with Home Assistant MQTT integration"

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY src/ ./src/
COPY pyproject.toml .

# Install the package
RUN pip install --no-cache-dir -e .

# Environment variables (can be overridden at runtime)
ENV EG4_BATTERY_IP="192.168.130.139"
ENV EG4_BATTERY_PORT="4196"
ENV EG4_DEVICE_ID="1"
ENV EG4_MQTT_BROKER="localhost"
ENV EG4_MQTT_PORT="1883"
ENV EG4_MQTT_USER=""
ENV EG4_MQTT_PASS=""
ENV EG4_POLL_INTERVAL="30"

# Run in headless mode by default
CMD ["eg4-monitor", "--no-ui"]
