"""Arch Archive package downloader for zfspin."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from zfspin.utils import download_file, log

if TYPE_CHECKING:
    from zfspin.config import PinningConfig


class ArchiveDownloader:
    """Download specific package versions from Arch Archive.

    The Arch Archive (archive.archlinux.org) stores historical versions
    of all Arch Linux packages. This class downloads kernel packages
    at specific versions for pinning.

    Example:
        >>> config = PinningConfig(kernel_version="6.12.29-1")
        >>> downloader = ArchiveDownloader(config, work_dir=Path("/tmp/build"))
        >>> packages = downloader.download_kernel_packages()
        >>> print(packages)
        [Path('/tmp/build/linux-lts-6.12.29-1-x86_64.pkg.tar.zst'),
         Path('/tmp/build/linux-lts-headers-6.12.29-1-x86_64.pkg.tar.zst')]
    """

    def __init__(self, config: "PinningConfig", work_dir: Path):
        """Initialize the downloader.

        Args:
            config: Pinning configuration with archive URL and versions
            work_dir: Directory to download packages to
        """
        self.config = config
        self.work_dir = work_dir
        self.arch = "x86_64"

    def download_kernel_packages(
        self,
        version: str | None = None,
        include_headers: bool = True,
    ) -> list[Path]:
        """Download kernel packages from Arch Archive.

        Downloads the main kernel package and optionally the headers
        package from archive.archlinux.org.

        Args:
            version: Kernel version to download (uses config if None)
            include_headers: Whether to download headers package

        Returns:
            List of paths to downloaded package files

        Raises:
            RuntimeError: If download fails
        """
        version = version or self.config.kernel_version
        if not version:
            raise ValueError("Kernel version must be specified")

        kernel = self.config.kernel_package
        packages_to_download = [kernel]
        if include_headers:
            packages_to_download.append(f"{kernel}-headers")

        self.work_dir.mkdir(parents=True, exist_ok=True)
        downloaded = []

        for pkg_name in packages_to_download:
            pkg_file = self._download_package(pkg_name, version)
            downloaded.append(pkg_file)

        return downloaded

    def download_package(
        self,
        package_name: str,
        version: str,
    ) -> Path:
        """Download a single package from Arch Archive.

        Args:
            package_name: Name of the package (e.g., "linux-lts")
            version: Package version (e.g., "6.12.29-1")

        Returns:
            Path to downloaded package file

        Raises:
            RuntimeError: If download fails
        """
        return self._download_package(package_name, version)

    def _download_package(self, package_name: str, version: str) -> Path:
        """Internal method to download a package.

        Args:
            package_name: Package name
            version: Package version

        Returns:
            Path to downloaded file
        """
        # Construct the archive URL
        # Format: packages/<first-letter>/<package-name>/<package-name>-<version>-<arch>.pkg.tar.zst
        first_letter = package_name[0].lower()
        filename = f"{package_name}-{version}-{self.arch}.pkg.tar.zst"
        url = f"{self.config.arch_archive_url}/{first_letter}/{package_name}/{filename}"

        dest = self.work_dir / filename

        if dest.exists():
            log.info(f"Package already downloaded: {filename}")
            return dest

        log.info(f"Downloading {package_name}={version} from Arch Archive...")
        download_file(url, dest)

        return dest

    def get_available_versions(self, package_name: str, limit: int = 10) -> list[str]:
        """List available versions of a package in Arch Archive.

        Note: This scrapes the archive HTML page, which may be slow.

        Args:
            package_name: Package name to look up
            limit: Maximum number of versions to return

        Returns:
            List of available version strings (newest first)
        """
        import re
        from zfspin.utils import fetch_url

        first_letter = package_name[0].lower()
        url = f"{self.config.arch_archive_url}/{first_letter}/{package_name}/"

        log.debug(f"Fetching available versions from {url}")

        try:
            html = fetch_url(url)
        except Exception as e:
            log.warning(f"Could not fetch version list: {e}")
            return []

        # Parse version numbers from the HTML
        # Links look like: <a href="linux-lts-6.12.29-1-x86_64.pkg.tar.zst">
        pattern = rf'href="{re.escape(package_name)}-([^"]+)-{self.arch}\.pkg\.tar\.zst"'
        versions = re.findall(pattern, html)

        # Sort by version (reverse so newest first)
        # This is a simple string sort which works for most version formats
        versions = sorted(set(versions), reverse=True)

        return versions[:limit]

    def verify_package(self, package_path: Path) -> bool:
        """Verify a downloaded package using pacman.

        Args:
            package_path: Path to the package file

        Returns:
            True if package is valid
        """
        from zfspin.utils import run_command

        if not package_path.exists():
            return False

        try:
            # Use pacman to verify package integrity
            result = run_command(
                ["pacman", "-Qp", str(package_path)],
                check=False,
                capture_output=True,
            )
            return result.returncode == 0
        except Exception:
            return False


class ArchZFSDownloader:
    """Download ZFS packages from archzfs.com repository.

    This downloads the prebuilt ZFS module packages (zfs-linux-lts, etc.)
    directly from the archzfs repository.
    """

    def __init__(self, config: "PinningConfig", work_dir: Path):
        """Initialize the downloader.

        Args:
            config: Pinning configuration with archzfs URL
            work_dir: Directory to download packages to
        """
        self.config = config
        self.work_dir = work_dir

    def download_zfs_module(self, version: str | None = None) -> Path:
        """Download the ZFS kernel module package.

        Args:
            version: ZFS module version (uses config.zfs_module_version if None)

        Returns:
            Path to downloaded package

        Raises:
            RuntimeError: If download fails or version not specified
        """
        version = version or self.config.zfs_module_version
        if not version:
            raise ValueError("ZFS module version must be specified")

        package_name = self.config.zfs_module_package
        filename = f"{package_name}-{version}-x86_64.pkg.tar.zst"
        url = f"{self.config.archzfs_url}/{filename}"

        dest = self.work_dir / filename
        self.work_dir.mkdir(parents=True, exist_ok=True)

        if dest.exists():
            log.info(f"Package already downloaded: {filename}")
            return dest

        log.info(f"Downloading {package_name}={version} from archzfs...")
        download_file(url, dest)

        return dest
