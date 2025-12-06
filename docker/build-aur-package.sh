#!/bin/bash
# Build zfspin AUR package using Docker
# Output: ./output/zfspin-*.pkg.tar.zst

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$REPO_ROOT"

echo "Building zfspin AUR package..."

# Create output directory
mkdir -p output

# Build using Docker BuildKit with output
DOCKER_BUILDKIT=1 docker build \
    -f docker/Dockerfile.builder \
    --output type=local,dest=output \
    .

echo ""
echo "Build complete! Package available in:"
ls -la output/*.pkg.tar.zst 2>/dev/null || echo "No package found - build may have failed"
