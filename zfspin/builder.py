"""AUR package builder for zfspin."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from zfspin.utils import run_command, log

if TYPE_CHECKING:
    from zfspin.config import PinningConfig


class AURBuilder:
    """Build packages from AUR at specific git commits.

    This class clones AUR packages and builds them using makepkg
    at specific git commits to get exact package versions.

    Example:
        >>> config = PinningConfig(zfs_utils_commit="35d368ef2c...")
        >>> builder = AURBuilder(config, work_dir=Path("/tmp/build"))
        >>> pkg = builder.build_zfs_utils()
        >>> print(pkg)
        Path('/tmp/build/zfs-utils-2.3.2-1-x86_64.pkg.tar.zst')
    """

    def __init__(self, config: "PinningConfig", work_dir: Path):
        """Initialize the builder.

        Args:
            config: Pinning configuration with AUR settings
            work_dir: Directory for building packages
        """
        self.config = config
        self.work_dir = work_dir
        self.aur_base_url = config.aur_base_url

    def build_zfs_utils(
        self,
        commit: str | None = None,
        dest_dir: Path | None = None,
    ) -> Path:
        """Build zfs-utils from AUR at a specific commit.

        Clones the zfs-utils AUR package, checks out the specified
        commit, and builds using makepkg.

        Args:
            commit: Git commit hash (uses config.zfs_utils_commit if None)
            dest_dir: Directory for output package (uses work_dir if None)

        Returns:
            Path to the built package file

        Raises:
            RuntimeError: If build fails
        """
        commit = commit or self.config.zfs_utils_commit
        if not commit:
            raise ValueError("zfs_utils_commit must be specified")

        dest_dir = dest_dir or self.work_dir
        dest_dir.mkdir(parents=True, exist_ok=True)

        return self._build_aur_package("zfs-utils", commit, dest_dir)

    def build_package(
        self,
        package_name: str,
        commit: str,
        dest_dir: Path | None = None,
    ) -> Path:
        """Build an arbitrary AUR package at a specific commit.

        Args:
            package_name: Name of the AUR package
            commit: Git commit hash to checkout
            dest_dir: Directory for output package

        Returns:
            Path to the built package file
        """
        dest_dir = dest_dir or self.work_dir
        dest_dir.mkdir(parents=True, exist_ok=True)

        return self._build_aur_package(package_name, commit, dest_dir)

    def _build_aur_package(
        self,
        package_name: str,
        commit: str,
        dest_dir: Path,
    ) -> Path:
        """Internal method to build an AUR package.

        Args:
            package_name: AUR package name
            commit: Git commit to checkout
            dest_dir: Destination for built package

        Returns:
            Path to built package
        """
        log.info(f"Building {package_name} from AUR (commit {commit[:12]})...")

        # Create build directory
        build_dir = self.work_dir / "aur-build"
        build_dir.mkdir(parents=True, exist_ok=True)

        pkg_dir = build_dir / package_name

        # Clean up existing if present
        if pkg_dir.exists():
            shutil.rmtree(pkg_dir)

        # Clone the AUR repo
        aur_url = f"{self.aur_base_url}/{package_name}.git"
        log.debug(f"Cloning {aur_url}")

        run_command([
            "git", "clone", "--quiet", aur_url, str(pkg_dir)
        ])

        # Checkout the specific commit
        log.debug(f"Checking out commit {commit}")
        run_command([
            "git", "-C", str(pkg_dir), "checkout", "--quiet", commit
        ])

        # Prepare for building
        self._prepare_build_dir(pkg_dir)

        # Build the package
        built_pkg = self._run_makepkg(pkg_dir, dest_dir)

        log.info(f"Built: {built_pkg.name}")
        return built_pkg

    def _prepare_build_dir(self, pkg_dir: Path) -> None:
        """Prepare build directory with correct permissions.

        makepkg refuses to run as root, so we need to set up
        the directory for building as a non-root user.

        Args:
            pkg_dir: Path to the package directory
        """
        build_user = self.config.build_as_user

        # Make parent directories accessible
        parent = pkg_dir.parent
        run_command(["chmod", "755", str(parent)])
        if parent.parent != parent:
            run_command(["chmod", "755", str(parent.parent)], check=False)

        # Change ownership of the package directory
        run_command([
            "chown", "-R", f"{build_user}:{build_user}", str(pkg_dir)
        ])

    def _run_makepkg(self, pkg_dir: Path, dest_dir: Path) -> Path:
        """Run makepkg to build the package.

        Args:
            pkg_dir: Directory containing PKGBUILD
            dest_dir: Destination for built package

        Returns:
            Path to the built package

        Raises:
            RuntimeError: If build fails or no package produced
        """
        build_user = self.config.build_as_user

        # Build with makepkg
        # - PKGDEST sets where the package is output
        # - -s: install dependencies
        # - --noconfirm: don't prompt
        # - --skippgpcheck: skip PGP verification (AUR packages often lack keys)
        log.debug(f"Running makepkg as {build_user}")

        run_command([
            "sudo", "-u", build_user,
            "env",
            f"HOME=/tmp/{build_user}-home",
            f"PKGDEST={pkg_dir}",
            "bash", "-c",
            f"cd {pkg_dir} && makepkg -s --noconfirm --skippgpcheck"
        ], timeout=1800)  # 30 minute timeout for builds

        # Find the built package
        packages = list(pkg_dir.glob("*.pkg.tar.zst"))
        if not packages:
            packages = list(pkg_dir.glob("*.pkg.tar.xz"))

        if not packages:
            raise RuntimeError(
                f"No package file produced in {pkg_dir}. "
                "Check build logs for errors."
            )

        # Copy to destination
        pkg = packages[0]
        dest = dest_dir / pkg.name

        if dest != pkg:
            shutil.copy(pkg, dest)

        return dest

    def get_pkgbuild_version(self, pkg_dir: Path) -> str | None:
        """Extract pkgver from a PKGBUILD file.

        Args:
            pkg_dir: Directory containing PKGBUILD

        Returns:
            Version string or None if not found
        """
        pkgbuild = pkg_dir / "PKGBUILD"
        if not pkgbuild.exists():
            return None

        content = pkgbuild.read_text()
        for line in content.splitlines():
            if line.startswith("pkgver="):
                version = line.split("=", 1)[1].strip().strip("'\"")
                return version

        return None

    def clean_build_dir(self) -> None:
        """Clean up the build directory."""
        build_dir = self.work_dir / "aur-build"
        if build_dir.exists():
            log.debug(f"Cleaning build directory: {build_dir}")
            shutil.rmtree(build_dir, ignore_errors=True)
