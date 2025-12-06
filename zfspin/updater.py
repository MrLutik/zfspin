"""ZFS-aware system updater for Arch Linux."""
from __future__ import annotations

import datetime
import os
import re
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Generator

from zfspin.config import PinningConfig, CompatibilityResult, UpdateResult
from zfspin.versions import VersionResolver
from zfspin.downloader import ArchiveDownloader
from zfspin.builder import AURBuilder
from zfspin.repository import LocalRepository
from zfspin.utils import run_command, log

if TYPE_CHECKING:
    pass


class KernelLock:
    """Manage kernel package locking in pacman.conf.

    Locks kernel packages by adding them to IgnorePkg in pacman.conf.
    This prevents accidental kernel updates that could break ZFS.

    The lock is atomic: if the update fails, packages remain locked.
    """

    LOCK_PACKAGES = [
        # Kernel packages
        "linux",
        "linux-headers",
        "linux-lts",
        "linux-lts-headers",
        "linux-zen",
        "linux-zen-headers",
        "linux-hardened",
        "linux-hardened-headers",
        # ZFS packages (must match kernel)
        "zfs-utils",
        "zfs-linux",
        "zfs-linux-lts",
        "zfs-linux-zen",
        "zfs-linux-hardened",
    ]

    LOCK_MARKER = "# zfspin kernel lock - do not edit manually"

    def __init__(self, pacman_conf: Path = Path("/etc/pacman.conf")):
        """Initialize the kernel lock manager.

        Args:
            pacman_conf: Path to pacman.conf
        """
        self.pacman_conf = pacman_conf

    def is_locked(self) -> bool:
        """Check if kernel packages are currently locked."""
        if not self.pacman_conf.exists():
            return False
        content = self.pacman_conf.read_text()
        return self.LOCK_MARKER in content

    def lock(self) -> None:
        """Lock kernel packages by adding to IgnorePkg.

        Adds kernel packages to IgnorePkg in pacman.conf to prevent
        accidental updates via regular pacman -Syu.
        """
        if self.is_locked():
            log.debug("Kernel packages already locked")
            return

        log.info("Locking kernel packages in pacman.conf")

        content = self.pacman_conf.read_text()

        # Build the ignore line
        ignore_line = f"IgnorePkg = {' '.join(self.LOCK_PACKAGES)}  {self.LOCK_MARKER}\n"

        # Find [options] section and add after it
        if "[options]" in content:
            # Add after [options] line
            content = content.replace(
                "[options]\n",
                f"[options]\n{ignore_line}"
            )
        else:
            # Fallback: add at beginning
            content = ignore_line + content

        self.pacman_conf.write_text(content)
        log.info("Kernel packages locked")

    def unlock(self) -> None:
        """Unlock kernel packages by removing from IgnorePkg.

        Removes the zfspin-managed IgnorePkg line from pacman.conf.
        """
        if not self.is_locked():
            log.debug("Kernel packages not locked")
            return

        log.info("Unlocking kernel packages in pacman.conf")

        content = self.pacman_conf.read_text()

        # Remove lines containing our marker
        lines = content.splitlines()
        new_lines = [line for line in lines if self.LOCK_MARKER not in line]

        self.pacman_conf.write_text("\n".join(new_lines) + "\n")
        log.info("Kernel packages unlocked")

    @contextmanager
    def unlocked(self) -> Generator[None, None, None]:
        """Context manager for temporarily unlocking kernel packages.

        Unlocks packages, yields, then re-locks. Re-locks even on exception.

        Example:
            >>> lock = KernelLock()
            >>> with lock.unlocked():
            ...     # kernel packages can be updated here
            ...     run_update()
            >>> # packages are locked again
        """
        was_locked = self.is_locked()

        if was_locked:
            self.unlock()

        try:
            yield
        finally:
            # Always re-lock if it was locked before
            if was_locked:
                self.lock()

    def get_locked_packages(self) -> list[str]:
        """Get list of currently locked packages from pacman.conf."""
        if not self.pacman_conf.exists():
            return []

        content = self.pacman_conf.read_text()
        locked = []

        for line in content.splitlines():
            if self.LOCK_MARKER in line and line.strip().startswith("IgnorePkg"):
                # Parse the IgnorePkg line
                match = re.match(r"IgnorePkg\s*=\s*(.+?)\s*#", line)
                if match:
                    locked = match.group(1).split()
                break

        return locked


class ZFSPinUpdater:
    """Orchestrate safe Arch Linux updates with ZFS boot environments.

    This updater:
    1. Checks kernel/ZFS compatibility with archzfs
    2. Creates ZFS boot environment before updates
    3. Builds compatible packages if needed
    4. Performs the system update
    5. Regenerates initramfs and boot entries
    6. Handles rollback on failure

    Example:
        >>> config = PinningConfig.auto_detect()
        >>> updater = ZFSPinUpdater(config)
        >>> result = updater.full_update()
        >>> if result.success:
        ...     print(f"Update complete! Reboot to {result.boot_environment}")
    """

    def __init__(
        self,
        config: PinningConfig | None = None,
        zfs_pool: str = "zroot",
        root_dataset: str | None = None,
    ):
        """Initialize the updater.

        Args:
            config: Pinning configuration (auto-detects if None)
            zfs_pool: Name of the ZFS pool
            root_dataset: Root dataset path (default: {pool}/ROOT/arch)
        """
        self.config = config
        self.zfs_pool = zfs_pool
        self.root_dataset = root_dataset or f"{zfs_pool}/ROOT/arch"
        self.work_dir: Path | None = None
        self._be_created: str | None = None
        self.kernel_lock = KernelLock()

    def full_update(
        self,
        dry_run: bool = False,
        skip_be: bool = False,
    ) -> UpdateResult:
        """Perform a full system update with ZFS boot environment protection.

        Steps:
        1. Check compatibility with archzfs
        2. Create boot environment (unless skip_be=True)
        3. Build pinned packages if needed
        4. Run pacman -Su
        5. Regenerate initramfs
        6. Update boot entries
        7. Prune old boot environments

        Args:
            dry_run: If True, only show what would be done
            skip_be: Skip boot environment creation

        Returns:
            UpdateResult with success status and details
        """
        actions = []

        try:
            # Setup work directory
            self.work_dir = Path(tempfile.mkdtemp(prefix="zfspin-"))
            log.info(f"Work directory: {self.work_dir}")

            # Step 1: Check compatibility
            log.info("Checking kernel/ZFS compatibility...")
            compat = self._check_compatibility()
            actions.append(f"Compatibility check: {compat.action_needed}")

            if dry_run:
                log.info("[DRY RUN] Would perform the following actions:")
                if not compat.compatible:
                    log.info(f"  - Build pinned packages (kernel={compat.required_kernel})")
                log.info("  - Create ZFS boot environment")
                log.info("  - Run pacman -Su")
                log.info("  - Regenerate initramfs")
                log.info("  - Update boot entries")
                return UpdateResult(
                    success=True,
                    actions_taken=["[DRY RUN] " + a for a in actions],
                )

            # Step 2: Create boot environment
            if not skip_be:
                be_name = self._create_boot_environment()
                self._be_created = be_name
                actions.append(f"Created boot environment: {be_name}")
            else:
                be_name = ""
                actions.append("Skipped boot environment creation")

            # Step 3: Build pinned packages if needed
            if not compat.compatible:
                self._prepare_pinned_packages()
                actions.append("Built pinned packages")

            # Step 4: System update (with atomic kernel unlock/lock)
            # Kernel packages are normally locked to prevent accidental updates.
            # We temporarily unlock them for our controlled update, then re-lock.
            was_locked = self.kernel_lock.is_locked()
            if was_locked:
                actions.append("Kernel packages were locked")

            with self.kernel_lock.unlocked():
                self._run_system_update()
                actions.append("Ran pacman -Su (kernel unlocked)")

            # After exiting context, kernel is re-locked automatically
            if was_locked:
                actions.append("Kernel packages re-locked")

            # Step 5: Regenerate initramfs
            self._regenerate_initramfs()
            actions.append("Regenerated initramfs")

            # Step 6: Update boot entries
            self._update_boot_entries()
            actions.append("Updated boot entries")

            # Step 7: Prune old boot environments
            if not skip_be:
                pruned = self._prune_boot_environments()
                if pruned:
                    actions.append(f"Pruned {len(pruned)} old boot environments")

            log.info("Update completed successfully!")
            return UpdateResult(
                success=True,
                boot_environment=be_name,
                actions_taken=actions,
            )

        except Exception as e:
            log.error(f"Update failed: {e}")

            # Attempt rollback if we created a BE
            if self._be_created:
                try:
                    self._rollback(self._be_created)
                    actions.append(f"Rolled back: destroyed {self._be_created}")
                except Exception as rb_error:
                    log.error(f"Rollback failed: {rb_error}")

            return UpdateResult(
                success=False,
                actions_taken=actions,
                error=str(e),
            )

        finally:
            # Cleanup work directory
            if self.work_dir and self.work_dir.exists():
                shutil.rmtree(self.work_dir, ignore_errors=True)

    def _check_compatibility(self) -> CompatibilityResult:
        """Check if current system is compatible with archzfs."""
        kernel = self.config.kernel_package if self.config else "linux-lts"
        resolver = VersionResolver()
        return resolver.check_compatibility(kernel)

    def _prepare_pinned_packages(self) -> None:
        """Build pinned packages for compatibility."""
        if not self.config:
            kernel = "linux-lts"
            log.info(f"Auto-detecting versions for {kernel}...")
            self.config = PinningConfig.auto_detect(kernel)

        log.info(f"Preparing pinned packages: kernel={self.config.kernel_version}, "
                 f"zfs-utils={self.config.zfs_utils_version}")

        # Create local repository
        repo_path = Path("/var/cache/zfspin/pinned")
        repo = LocalRepository(repo_path, self.config.local_repo_name)
        repo.create()

        # Download kernel from Arch Archive
        downloader = ArchiveDownloader(self.config, self.work_dir)
        kernel_pkgs = downloader.download_kernel_packages()
        repo.add_packages(kernel_pkgs)

        # Build zfs-utils from AUR
        builder = AURBuilder(self.config, self.work_dir)
        zfs_pkg = builder.build_zfs_utils(dest_dir=repo_path)
        repo.add_package(zfs_pkg)

        # Inject into pacman.conf
        pacman_conf = Path("/etc/pacman.conf")
        repo.inject_into_pacman_conf(pacman_conf)

        # Sync pacman database
        repo.sync_to_system()

    def _create_boot_environment(self) -> str:
        """Create a ZFS boot environment snapshot.

        Returns:
            Name of the created boot environment
        """
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        be_name = f"pre-update-{timestamp}"
        snapshot = f"{self.root_dataset}@{be_name}"

        log.info(f"Creating boot environment: {be_name}")

        # Create snapshot
        run_command(["zfs", "snapshot", "-r", snapshot])

        # Create clone for boot environment
        clone_dataset = f"{self.zfs_pool}/ROOT/{be_name}"
        run_command(["zfs", "clone", snapshot, clone_dataset])

        log.info(f"Boot environment created: {be_name}")
        return be_name

    def _run_system_update(self) -> None:
        """Run the system update with pacman."""
        log.info("Running system update...")

        # Sync and update
        run_command(
            ["pacman", "-Su", "--noconfirm"],
            timeout=3600,  # 1 hour timeout
        )

    def _regenerate_initramfs(self) -> None:
        """Regenerate the initramfs with mkinitcpio."""
        log.info("Regenerating initramfs...")

        # Determine kernel preset
        kernel = self.config.kernel_package if self.config else "linux-lts"
        preset = kernel

        run_command(["mkinitcpio", "-p", preset])

    def _update_boot_entries(self) -> None:
        """Update systemd-boot entries."""
        log.info("Updating boot entries...")

        # Check for generate-uki.sh script
        uki_script = Path("/usr/local/bin/generate-uki.sh")
        if uki_script.exists():
            run_command([str(uki_script)])
        else:
            # Fallback: just update bootloader
            run_command(["bootctl", "update"], check=False)

    def _prune_boot_environments(self, keep: int = 3) -> list[str]:
        """Prune old boot environments, keeping the most recent.

        Args:
            keep: Number of boot environments to keep

        Returns:
            List of pruned boot environment names
        """
        log.info(f"Pruning boot environments (keeping {keep} most recent)...")

        # List snapshots
        result = run_command(
            ["zfs", "list", "-H", "-t", "snapshot", "-o", "name", "-s", "creation"],
            capture_output=True,
        )

        # Filter to pre-update snapshots
        snapshots = []
        prefix = f"{self.root_dataset}@pre-update-"
        for line in result.stdout.strip().split("\n"):
            if line.startswith(prefix):
                snapshots.append(line)

        # Keep only the most recent 'keep' snapshots
        to_prune = snapshots[:-keep] if len(snapshots) > keep else []
        pruned = []

        for snapshot in to_prune:
            be_name = snapshot.split("@")[1]
            clone_dataset = f"{self.zfs_pool}/ROOT/{be_name}"

            try:
                # Destroy clone first
                run_command(["zfs", "destroy", "-r", clone_dataset], check=False)
                # Then destroy snapshot
                run_command(["zfs", "destroy", "-r", snapshot])
                pruned.append(be_name)
                log.debug(f"Pruned: {be_name}")
            except Exception as e:
                log.warning(f"Could not prune {be_name}: {e}")

        if pruned:
            log.info(f"Pruned {len(pruned)} old boot environments")

        return pruned

    def _rollback(self, be_name: str) -> None:
        """Rollback by destroying a failed boot environment.

        Args:
            be_name: Name of the boot environment to destroy
        """
        log.warning(f"Rolling back: destroying {be_name}")

        clone_dataset = f"{self.zfs_pool}/ROOT/{be_name}"
        snapshot = f"{self.root_dataset}@{be_name}"

        # Destroy clone
        run_command(["zfs", "destroy", "-r", clone_dataset], check=False)

        # Destroy snapshot
        run_command(["zfs", "destroy", "-r", snapshot], check=False)

    def check_only(self) -> CompatibilityResult:
        """Just check compatibility without updating.

        Returns:
            CompatibilityResult with current status
        """
        return self._check_compatibility()


class KernelHoldUpdater:
    """Fallback updater that holds kernel packages during update.

    Used when building pinned packages fails - this simply ignores
    kernel updates to avoid breaking ZFS.
    """

    HOLD_PACKAGES = [
        "linux",
        "linux-headers",
        "linux-lts",
        "linux-lts-headers",
        "linux-zen",
        "linux-zen-headers",
    ]

    def update_with_kernel_hold(self) -> UpdateResult:
        """Run update while holding kernel packages.

        Returns:
            UpdateResult with status
        """
        log.warning("Falling back to kernel hold update...")

        try:
            # Build ignore list
            ignore_pkgs = ",".join(self.HOLD_PACKAGES)

            run_command([
                "pacman", "-Su", "--noconfirm",
                f"--ignore={ignore_pkgs}"
            ], timeout=3600)

            return UpdateResult(
                success=True,
                actions_taken=["Updated with kernel packages held"],
            )

        except Exception as e:
            return UpdateResult(
                success=False,
                error=str(e),
            )
