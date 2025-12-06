"""Version resolution for zfspin - auto-detect from archzfs.com."""
from __future__ import annotations

import tarfile
import tempfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

from zfspin.utils import run_command, log

if TYPE_CHECKING:
    pass


@dataclass
class ArchZFSPackageInfo:
    """Information about a ZFS package from archzfs repository."""

    name: str
    version: str
    depends: list[str]
    provides: list[str]


class VersionResolver:
    """Resolve compatible kernel/ZFS versions from archzfs.com.

    This class scrapes the archzfs repository to find:
    - Available ZFS module packages (zfs-linux, zfs-linux-lts, etc.)
    - Required kernel versions from package dependencies
    - Required zfs-utils version

    It can also find AUR commit hashes for specific zfs-utils versions.
    """

    def __init__(
        self,
        archzfs_url: str = "https://archzfs.com/archzfs/x86_64/",
        aur_base_url: str = "https://aur.archlinux.org",
    ):
        """Initialize the version resolver.

        Args:
            archzfs_url: Base URL for archzfs repository
            aur_base_url: Base URL for AUR
        """
        self.archzfs_url = archzfs_url.rstrip("/")
        self.aur_base_url = aur_base_url.rstrip("/")
        self._package_cache: dict[str, ArchZFSPackageInfo] = {}

    def get_archzfs_requirements(self, kernel: str = "linux-lts") -> dict:
        """Get version requirements from archzfs repository.

        Parses the archzfs repo database to find what kernel version
        and zfs-utils version are required for the specified kernel's
        ZFS module package.

        Args:
            kernel: Kernel package name (linux, linux-lts, linux-zen, etc.)

        Returns:
            Dictionary with:
                - kernel_version: Required kernel version (e.g., "6.12.29-1")
                - zfs_utils_version: Required zfs-utils version (e.g., "2.3.2")
                - zfs_module_version: Full ZFS module version (e.g., "2.3.2_6.12.29.1-1")
                - zfs_module_package: Package name (e.g., "zfs-linux-lts")

        Raises:
            RuntimeError: If package not found or parsing fails
        """
        # Determine the ZFS module package name
        if kernel == "linux":
            zfs_pkg_name = "zfs-linux"
        elif kernel == "linux-lts":
            zfs_pkg_name = "zfs-linux-lts"
        else:
            suffix = kernel.replace("linux-", "")
            zfs_pkg_name = f"zfs-linux-{suffix}"

        log.info(f"Resolving versions for {zfs_pkg_name} from archzfs...")

        # Fetch and parse the repository database
        packages = self._fetch_repo_db()

        if zfs_pkg_name not in packages:
            available = [p for p in packages if p.startswith("zfs-linux")]
            raise RuntimeError(
                f"Package {zfs_pkg_name} not found in archzfs. "
                f"Available: {', '.join(available)}"
            )

        pkg_info = packages[zfs_pkg_name]
        log.debug(f"Found {zfs_pkg_name} version {pkg_info.version}")
        log.debug(f"Dependencies: {pkg_info.depends}")

        # Parse dependencies to find required versions
        kernel_version = None
        zfs_utils_version = None

        for dep in pkg_info.depends:
            # Parse dependency like "linux-lts=6.12.29" or "zfs-utils=2.3.2"
            if "=" in dep:
                name, version = dep.split("=", 1)
                if name == kernel:
                    kernel_version = version
                elif name == "zfs-utils":
                    zfs_utils_version = version

        if not kernel_version:
            raise RuntimeError(
                f"Could not find {kernel} version requirement in {zfs_pkg_name} dependencies"
            )

        if not zfs_utils_version:
            raise RuntimeError(
                f"Could not find zfs-utils version requirement in {zfs_pkg_name} dependencies"
            )

        result = {
            "kernel_version": kernel_version,
            "zfs_utils_version": zfs_utils_version,
            "zfs_module_version": pkg_info.version,
            "zfs_module_package": zfs_pkg_name,
        }

        log.info(
            f"Resolved: kernel={kernel_version}, "
            f"zfs-utils={zfs_utils_version}, "
            f"zfs-module={pkg_info.version}"
        )

        return result

    def _fetch_repo_db(self) -> dict[str, ArchZFSPackageInfo]:
        """Fetch and parse the archzfs repository database.

        Returns:
            Dictionary mapping package names to ArchZFSPackageInfo
        """
        if self._package_cache:
            return self._package_cache

        db_url = f"{self.archzfs_url}/archzfs.db"
        log.debug(f"Fetching repo database: {db_url}")

        # Download the database (it's a gzipped tar)
        result = run_command(
            ["curl", "-fsSL", db_url],
            capture_output=True,
            text=False,
        )

        # Parse the tar.gz database (already bytes since text=False)
        db_content = result.stdout

        # The database is a tar.gz containing directories for each package
        # Each directory has a 'desc' file with package metadata
        packages = {}

        with tarfile.open(fileobj=BytesIO(db_content), mode="r:*") as tar:
            for member in tar.getmembers():
                if member.name.endswith("/desc"):
                    # Extract and parse the desc file
                    f = tar.extractfile(member)
                    if f:
                        desc_content = f.read().decode("utf-8")
                        pkg_info = self._parse_desc(desc_content)
                        if pkg_info:
                            packages[pkg_info.name] = pkg_info

        self._package_cache = packages
        log.debug(f"Parsed {len(packages)} packages from archzfs repo")
        return packages

    def _parse_desc(self, content: str) -> ArchZFSPackageInfo | None:
        """Parse a package 'desc' file from the repo database.

        Args:
            content: Contents of the desc file

        Returns:
            ArchZFSPackageInfo or None if parsing fails
        """
        # The desc file format is:
        # %FIELD%
        # value(s)
        #
        # %NEXTFIELD%
        # ...

        fields: dict[str, list[str]] = {}
        current_field = None
        current_values: list[str] = []

        for line in content.splitlines():
            line = line.strip()
            if line.startswith("%") and line.endswith("%"):
                # Save previous field
                if current_field:
                    fields[current_field] = current_values
                current_field = line[1:-1]
                current_values = []
            elif line and current_field:
                current_values.append(line)

        # Don't forget the last field
        if current_field:
            fields[current_field] = current_values

        # Extract required fields
        name = fields.get("NAME", [""])[0]
        version = fields.get("VERSION", [""])[0]

        if not name:
            return None

        return ArchZFSPackageInfo(
            name=name,
            version=version,
            depends=fields.get("DEPENDS", []),
            provides=fields.get("PROVIDES", []),
        )

    def find_aur_commit(self, zfs_version: str, work_dir: Path | None = None) -> str:
        """Find the AUR commit hash for a specific zfs-utils version.

        Clones the zfs-utils AUR repo and searches git history for
        the commit that sets pkgver to the specified version.

        Args:
            zfs_version: The zfs-utils version to find (e.g., "2.3.2")
            work_dir: Working directory for git clone (uses temp dir if None)

        Returns:
            Git commit hash (full 40 chars)

        Raises:
            RuntimeError: If commit cannot be found
        """
        log.info(f"Finding AUR commit for zfs-utils={zfs_version}...")

        # Use temp dir if not specified
        cleanup = False
        if work_dir is None:
            work_dir = Path(tempfile.mkdtemp(prefix="zfspin-aur-"))
            cleanup = True

        try:
            aur_repo = work_dir / "zfs-utils"

            # Clone if not already present
            if not aur_repo.exists():
                log.debug("Cloning zfs-utils AUR repo...")
                run_command([
                    "git", "clone", "--quiet",
                    f"{self.aur_base_url}/zfs-utils.git",
                    str(aur_repo),
                ])

            # Search git log for the version
            # We look for commits that set pkgver= to our version
            result = run_command(
                ["git", "-C", str(aur_repo), "log", "--oneline", "--all", "-n", "500"],
                capture_output=True,
            )

            # For each commit, check if PKGBUILD has pkgver=<version>
            for line in result.stdout.splitlines():
                if not line.strip():
                    continue
                commit_hash = line.split()[0]

                # Check PKGBUILD at this commit
                try:
                    pkgbuild = run_command(
                        ["git", "-C", str(aur_repo), "show", f"{commit_hash}:PKGBUILD"],
                        capture_output=True,
                        check=False,
                    )
                    if pkgbuild.returncode == 0:
                        # Look for pkgver=X.X.X
                        for pkgline in pkgbuild.stdout.splitlines():
                            if pkgline.startswith("pkgver="):
                                found_version = pkgline.split("=", 1)[1].strip().strip('"\'')
                                if found_version == zfs_version:
                                    # Get full commit hash
                                    full_hash = run_command(
                                        ["git", "-C", str(aur_repo), "rev-parse", commit_hash],
                                        capture_output=True,
                                    ).stdout.strip()
                                    log.info(f"Found commit: {full_hash[:12]} for zfs-utils={zfs_version}")
                                    return full_hash
                except Exception:
                    continue

            raise RuntimeError(
                f"Could not find AUR commit for zfs-utils={zfs_version}. "
                "The version may be too old or not yet released."
            )

        finally:
            if cleanup and work_dir.exists():
                import shutil
                shutil.rmtree(work_dir, ignore_errors=True)

    def get_installed_versions(self) -> dict[str, str]:
        """Get currently installed kernel and ZFS versions.

        Returns:
            Dictionary with 'kernel' and 'zfs_utils' version strings,
            or empty strings if not installed.
        """
        result = {
            "kernel": "",
            "zfs_utils": "",
        }

        # Get kernel version from pacman
        try:
            pkg_result = run_command(
                ["pacman", "-Q", "linux-lts"],
                capture_output=True,
                check=False,
            )
            if pkg_result.returncode == 0:
                # Output format: "linux-lts 6.12.29-1"
                parts = pkg_result.stdout.strip().split()
                if len(parts) >= 2:
                    result["kernel"] = parts[1]
        except Exception:
            pass

        # Get zfs-utils version
        try:
            pkg_result = run_command(
                ["pacman", "-Q", "zfs-utils"],
                capture_output=True,
                check=False,
            )
            if pkg_result.returncode == 0:
                parts = pkg_result.stdout.strip().split()
                if len(parts) >= 2:
                    result["zfs_utils"] = parts[1]
        except Exception:
            pass

        return result

    def check_compatibility(self, kernel: str = "linux-lts") -> "CompatibilityResult":  # noqa: F821
        """Check if the current system is compatible with archzfs.

        Compares installed kernel and zfs-utils versions against
        what archzfs requires.

        Args:
            kernel: Kernel package name to check

        Returns:
            CompatibilityResult with compatibility status and action needed
        """
        from zfspin.config import CompatibilityResult

        requirements = self.get_archzfs_requirements(kernel)
        installed = self.get_installed_versions()

        current_kernel = installed.get("kernel", "")
        current_zfs = installed.get("zfs_utils", "")
        required_kernel = requirements["kernel_version"]
        required_zfs = requirements["zfs_utils_version"]

        # Check if versions match
        # For kernel, we need exact major.minor.patch match (ignore -release suffix for comparison)
        kernel_match = self._version_matches(current_kernel, required_kernel)
        zfs_match = self._version_matches(current_zfs, required_zfs)

        if kernel_match and zfs_match:
            return CompatibilityResult(
                compatible=True,
                current_kernel=current_kernel,
                required_kernel=required_kernel,
                current_zfs_utils=current_zfs,
                required_zfs_utils=required_zfs,
                action_needed="none",
            )

        # Determine what action is needed
        if not kernel_match and not zfs_match:
            action = "update_both"
        elif not kernel_match:
            action = "downgrade_kernel"
        else:
            action = "build_zfs_utils"

        return CompatibilityResult(
            compatible=False,
            current_kernel=current_kernel,
            required_kernel=required_kernel,
            current_zfs_utils=current_zfs,
            required_zfs_utils=required_zfs,
            action_needed=action,
        )

    @staticmethod
    def _version_matches(installed: str, required: str) -> bool:
        """Check if installed version matches required version.

        Args:
            installed: Installed version string (e.g., "6.12.29-1")
            required: Required version string (e.g., "6.12.29")

        Returns:
            True if versions are compatible
        """
        if not installed or not required:
            return False

        # Normalize versions - remove package release suffix for comparison
        # e.g., "2.3.2-1" -> "2.3.2"
        installed_base = installed.split("-")[0] if "-" in installed else installed
        required_base = required.split("-")[0] if "-" in required else required

        # For kernel, required might be "6.12.29" and installed "6.12.29-1"
        # We consider them matching if the base versions match
        return installed_base == required_base or installed.startswith(required)
