"""Local pacman repository management for zfspin."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from zfspin.utils import run_command, log

if TYPE_CHECKING:
    pass


class LocalRepository:
    """Manage a local pacman repository for pinned packages.

    Creates and maintains a local package repository that can be
    injected into pacman.conf to provide specific package versions.

    Example:
        >>> repo = LocalRepository(Path("/var/cache/pinned"))
        >>> repo.create()
        >>> repo.add_packages([Path("linux-lts-6.12.29-1-x86_64.pkg.tar.zst")])
        >>> repo.inject_into_pacman_conf(Path("/etc/pacman.conf"))
    """

    def __init__(
        self,
        repo_path: Path,
        repo_name: str = "pinned",
    ):
        """Initialize the local repository.

        Args:
            repo_path: Path to the repository directory
            repo_name: Name for the repository (default: "pinned")
        """
        self.repo_path = repo_path
        self.repo_name = repo_name
        self.db_file = repo_path / f"{repo_name}.db.tar.gz"

    def create(self) -> None:
        """Create the repository directory.

        Creates the directory if it doesn't exist.
        """
        log.debug(f"Creating local repository at {self.repo_path}")
        self.repo_path.mkdir(parents=True, exist_ok=True)

    def add_packages(self, packages: list[Path]) -> None:
        """Add packages to the repository.

        Copies packages to the repository directory and updates
        the repo database using repo-add.

        Args:
            packages: List of paths to package files (.pkg.tar.zst)
        """
        if not packages:
            log.warning("No packages to add to repository")
            return

        self.create()

        # Copy packages to repo directory
        repo_packages = []
        for pkg in packages:
            dest = self.repo_path / pkg.name
            if dest != pkg:
                shutil.copy(pkg, dest)
            repo_packages.append(dest)
            log.debug(f"Added to repo: {pkg.name}")

        # Update the repository database
        self._update_database(repo_packages)

    def add_package(self, package: Path) -> None:
        """Add a single package to the repository.

        Args:
            package: Path to the package file
        """
        self.add_packages([package])

    def _update_database(self, packages: list[Path]) -> None:
        """Update the repository database with repo-add.

        Args:
            packages: List of package paths in the repository
        """
        if not packages:
            return

        log.info(f"Updating repository database: {self.repo_name}")

        cmd = ["repo-add", str(self.db_file)]
        cmd.extend(str(p) for p in packages)

        run_command(cmd)

    def remove_package(self, package_name: str) -> None:
        """Remove a package from the repository.

        Args:
            package_name: Name of the package to remove (without version)
        """
        log.info(f"Removing {package_name} from repository")

        run_command([
            "repo-remove", str(self.db_file), package_name
        ], check=False)

        # Also remove the package files
        for pkg_file in self.repo_path.glob(f"{package_name}-*.pkg.tar.*"):
            pkg_file.unlink()
            log.debug(f"Removed: {pkg_file.name}")

    def list_packages(self) -> list[str]:
        """List packages in the repository.

        Returns:
            List of package filenames in the repository
        """
        packages = []
        for pattern in ["*.pkg.tar.zst", "*.pkg.tar.xz"]:
            packages.extend(p.name for p in self.repo_path.glob(pattern))
        return sorted(packages)

    def inject_into_pacman_conf(
        self,
        pacman_conf: Path,
        before_section: str = "core",
    ) -> None:
        """Add this repository to pacman.conf.

        Injects the repository configuration before the specified
        section to ensure it has priority over standard repos.

        Args:
            pacman_conf: Path to pacman.conf
            before_section: Insert before this section (default: "core")
        """
        log.info(f"Injecting [{self.repo_name}] into {pacman_conf}")

        content = pacman_conf.read_text()

        # Check if already injected
        if f"[{self.repo_name}]" in content:
            log.debug("Repository already in pacman.conf")
            return

        # Build the repo configuration
        repo_config = f"""
# Pinned packages repository (managed by zfspin)
[{self.repo_name}]
SigLevel = Optional TrustAll
Server = file://{self.repo_path}

"""

        # Insert before the specified section
        marker = f"\n[{before_section}]"
        if marker in content:
            content = content.replace(marker, repo_config + f"[{before_section}]")
        else:
            # If section not found, append to end
            content += repo_config

        pacman_conf.write_text(content)
        log.info(f"Added [{self.repo_name}] repository to pacman.conf")

    def remove_from_pacman_conf(self, pacman_conf: Path) -> None:
        """Remove this repository from pacman.conf.

        Args:
            pacman_conf: Path to pacman.conf
        """
        content = pacman_conf.read_text()

        if f"[{self.repo_name}]" not in content:
            return

        # Remove the section and its configuration
        lines = content.splitlines()
        new_lines = []
        skip_until_next_section = False
        skip_comment = False

        for line in lines:
            # Check for our comment
            if "Pinned packages repository" in line:
                skip_comment = True
                continue
            if skip_comment and line.strip() == "":
                skip_comment = False
                continue

            # Check for our section
            if line.strip() == f"[{self.repo_name}]":
                skip_until_next_section = True
                continue

            # Check for next section
            if skip_until_next_section:
                if line.strip().startswith("[") and line.strip().endswith("]"):
                    skip_until_next_section = False
                else:
                    continue

            new_lines.append(line)

        pacman_conf.write_text("\n".join(new_lines))
        log.info(f"Removed [{self.repo_name}] from pacman.conf")

    def clean(self) -> None:
        """Remove the entire repository directory."""
        if self.repo_path.exists():
            log.info(f"Cleaning repository: {self.repo_path}")
            shutil.rmtree(self.repo_path, ignore_errors=True)

    def sync_to_system(self) -> None:
        """Run pacman -Sy to sync the repository.

        This updates pacman's local database with packages from
        this repository.
        """
        log.info("Syncing pacman database")
        run_command(["pacman", "-Sy", "--noconfirm"])

    @property
    def exists(self) -> bool:
        """Check if the repository exists and has packages."""
        return self.db_file.exists()


class ArchZFSRepository:
    """Manage archzfs repository configuration.

    Handles adding/removing the archzfs.com repository from pacman.conf.
    """

    REPO_CONFIG = """
# ArchZFS repository (https://archzfs.com)
[archzfs]
Server = https://archzfs.com/$repo/$arch
"""

    def __init__(self, pacman_conf: Path = Path("/etc/pacman.conf")):
        """Initialize the archzfs repository manager.

        Args:
            pacman_conf: Path to pacman.conf
        """
        self.pacman_conf = pacman_conf

    def is_configured(self) -> bool:
        """Check if archzfs is configured in pacman.conf."""
        if not self.pacman_conf.exists():
            return False
        return "[archzfs]" in self.pacman_conf.read_text()

    def add(self) -> None:
        """Add archzfs repository to pacman.conf."""
        if self.is_configured():
            log.debug("archzfs repository already configured")
            return

        log.info("Adding archzfs repository to pacman.conf")

        content = self.pacman_conf.read_text()

        # Add before [extra] if it exists, otherwise at end
        if "\n[extra]" in content:
            content = content.replace("\n[extra]", self.REPO_CONFIG + "\n[extra]")
        else:
            content += self.REPO_CONFIG

        self.pacman_conf.write_text(content)

    def remove(self) -> None:
        """Remove archzfs repository from pacman.conf."""
        if not self.is_configured():
            return

        log.info("Removing archzfs repository from pacman.conf")

        content = self.pacman_conf.read_text()
        lines = content.splitlines()
        new_lines = []
        skip_section = False

        for line in lines:
            if "ArchZFS repository" in line:
                continue
            if line.strip() == "[archzfs]":
                skip_section = True
                continue
            if skip_section:
                if line.strip().startswith("[") and line.strip().endswith("]"):
                    skip_section = False
                else:
                    continue
            new_lines.append(line)

        self.pacman_conf.write_text("\n".join(new_lines))

    def import_key(self) -> None:
        """Import the archzfs PGP key."""
        log.info("Importing archzfs PGP key")
        run_command([
            "pacman-key", "-r", "DDF7DB817396A49B2A2723F7403BD972F75D9D76"
        ], check=False)
        run_command([
            "pacman-key", "--lsign-key", "DDF7DB817396A49B2A2723F7403BD972F75D9D76"
        ], check=False)
