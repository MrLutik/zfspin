# Multistage Dockerfile for building zfspin AUR package
# Usage: docker build -f docker/Dockerfile.builder -o output .

# Stage 1: Build environment
FROM archlinux:latest AS builder

# Install build dependencies
RUN pacman -Syu --noconfirm \
    base-devel \
    git \
    python \
    python-build \
    python-installer \
    python-wheel \
    python-setuptools

# Create non-root build user (makepkg requirement)
RUN useradd -m builder && \
    echo "builder ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers

WORKDIR /build

# Copy source files
COPY --chown=builder:builder . .

# Build as non-root user
USER builder

# Build Python wheel first
RUN python -m build --wheel --no-isolation

# Build AUR package
WORKDIR /build/aur
RUN makepkg -s --noconfirm --skipinteg

# Stage 2: Export only the package
FROM scratch AS export
COPY --from=builder /build/aur/*.pkg.tar.zst /
