#!/usr/bin/env bash
set -euo pipefail

REGISTRY="${REGISTRY:-localhost:5000}"
IMAGE="eg4-battery-monitor"
TAG="${TAG:-latest}"
FULL="${REGISTRY}/${IMAGE}:${TAG}"

echo "Building ${FULL}..."
docker build -t "${FULL}" .

echo "Pushing ${FULL}..."
docker push "${FULL}"

echo "Done: ${FULL}"
