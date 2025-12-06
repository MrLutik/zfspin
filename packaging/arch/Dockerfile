FROM archlinux:base-devel

# Update system and install dependencies
RUN pacman -Syu --noconfirm && \
    pacman -S --noconfirm python python-build python-installer python-wheel python-setuptools git namcap fakeroot sudo && \
    pacman -Scc --noconfirm

# Create build user (makepkg refuses to run as root)
RUN useradd -m builder && \
    echo "builder ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers && \
    mkdir -p /build /output && \
    chown -R builder:builder /build /output

USER builder
WORKDIR /build

# Copy PKGBUILD and install file
COPY --chown=builder:builder packaging/arch/PKGBUILD /build/
COPY --chown=builder:builder packaging/arch/zfspin.install /build/

# Create source tarball from the repo
COPY --chown=builder:builder . /build/zfspin-src/

# Build the package
CMD ["bash", "-c", "\
    VERSION=${VERSION:-0.1.0} && \
    VERSION=${VERSION//-/.} && \
    sed -i \"s/pkgver=.*/pkgver=${VERSION}/\" PKGBUILD && \
    cd /build/zfspin-src && \
    tar czf /build/zfspin-${VERSION}.tar.gz --transform \"s,^,zfspin-${VERSION}/,\" \
        --exclude='.git' --exclude='dist' --exclude='*.egg-info' --exclude='__pycache__' \
        . && \
    cd /build && \
    sed -i 's|source=(.*)|source=(\"zfspin-${VERSION}.tar.gz\")|' PKGBUILD && \
    makepkg -sf --noconfirm && \
    namcap *.pkg.tar.zst 2>&1 || true && \
    sudo cp *.pkg.tar.zst /output/ \
"]
