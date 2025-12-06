#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Get version from git tag or environment variable, default to 0.0.0
if [ -n "${VERSION}" ]; then
    PKG_VERSION="${VERSION}"
elif git describe --tags --abbrev=0 >/dev/null 2>&1; then
    PKG_VERSION="$(git describe --tags --abbrev=0)"
    PKG_VERSION="${PKG_VERSION#v}"  # Remove leading 'v'
else
    PKG_VERSION="0.0.0"
fi

echo "Building AUR package version ${PKG_VERSION}..."

# Create output directory
mkdir -p "${PROJECT_ROOT}/dist/arch"

# Build Docker image
echo "Building Docker image..."
docker build -t zfspin-arch-builder -f "${SCRIPT_DIR}/Dockerfile" "${PROJECT_ROOT}"

# Run build
echo "Running package build..."
docker run --rm \
    -e VERSION="${PKG_VERSION}" \
    -v "${PROJECT_ROOT}/dist/arch:/output" \
    zfspin-arch-builder

echo ""
echo "Package built successfully!"
echo "Output: dist/arch/"
ls -la "${PROJECT_ROOT}/dist/arch/"
