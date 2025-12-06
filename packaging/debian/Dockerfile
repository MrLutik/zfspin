FROM debian:bookworm

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    devscripts \
    debhelper \
    dh-python \
    python3 \
    python3-pip \
    python3-venv \
    python3-build \
    python3-installer \
    python3-wheel \
    python3-setuptools \
    git \
    lintian \
    fakeroot \
    && rm -rf /var/lib/apt/lists/*

# Set up build directory
WORKDIR /build

# Copy source with debian directory
COPY . /build/zfspin-1.0.0/
COPY packaging/debian/debian /build/zfspin-1.0.0/debian/

WORKDIR /build/zfspin-1.0.0

# Build the package
CMD ["bash", "-c", "\
    VERSION=${VERSION:-1.0.0} && \
    sed -i \"s/zfspin (.*)/zfspin (${VERSION}-1)/\" debian/changelog && \
    dpkg-buildpackage -us -uc -b -d && \
    lintian ../*.deb 2>&1 || true && \
    cp ../*.deb /output/ \
"]
