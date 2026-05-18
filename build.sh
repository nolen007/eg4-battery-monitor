#!/usr/bin/env bash
set -euo pipefail

IMAGE="eg4-battery-monitor"
TAG="${TAG:-latest}"

echo "Building ${IMAGE}:${TAG}..."
docker build -t "${IMAGE}:${TAG}" .
echo "Done: ${IMAGE}:${TAG}"
