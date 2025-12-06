"""Configuration management for zfspin."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


@dataclass
class PinningConfig:
    """Configuration for kernel/ZFS version pinning.

    Attributes:
        kernel_package: Name of the kernel package (e.g., "linux-lts")
        kernel_version: Specific kernel version (None = auto-detect)
        zfs_utils_version: ZFS utils version (None = auto-detect)
        zfs_utils_commit: AUR commit hash for zfs-utils (None = auto-detect)
        zfs_module_version: Full zfs-linux-* version from archzfs
        arch_archive_url: Base URL for Arch Archive
        archzfs_url: Base URL for archzfs repository
        aur_base_url: Base URL for AUR
        build_as_user: User to run makepkg as
        local_repo_name: Name for the local pinned repo
        work_dir: Working directory for builds
    """

    kernel_package: str = "linux-lts"
    kernel_version: str | None = None
    zfs_utils_version: str | None = None
    zfs_utils_commit: str | None = None
    zfs_module_version: str | None = None

    arch_archive_url: str = "https://archive.archlinux.org/packages"
    archzfs_url: str = "https://archzfs.com/archzfs/x86_64/"
    aur_base_url: str = "https://aur.archlinux.org"

    build_as_user: str = "nobody"
    local_repo_name: str = "pinned"
    work_dir: Path | None = None

    @classmethod
    def from_toml(cls, config_path: Path) -> "PinningConfig":
        """Load configuration from TOML file.

        Args:
            config_path: Path to config.toml

        Returns:
            PinningConfig instance
        """
        with open(config_path, "rb") as f:
            data = tomllib.load(f)

        pinning = data.get("pinning", {})
        system = data.get("system", {})

        # Determine kernel from system config if not in pinning
        kernel = pinning.get("kernel_package") or system.get("kernel", "linux-lts")

        # Normalize kernel name (remove -lts suffix variations)
        if kernel == "linux":
            kernel = "linux"
        elif "lts" in kernel.lower():
            kernel = "linux-lts"

        return cls(
            kernel_package=kernel,
            kernel_version=pinning.get("kernel_version"),
            zfs_utils_version=pinning.get("zfs_utils_version"),
            zfs_utils_commit=pinning.get("zfs_utils_commit"),
            build_as_user=pinning.get("build_as_user", "nobody"),
            local_repo_name=pinning.get("local_repo_name", "pinned"),
        )

    @classmethod
    def auto_detect(cls, kernel: str = "linux-lts") -> "PinningConfig":
        """Auto-detect compatible versions from archzfs.com.

        Args:
            kernel: Kernel package name (linux, linux-lts, etc.)

        Returns:
            PinningConfig with detected versions
        """
        from zfspin.versions import VersionResolver

        resolver = VersionResolver()
        info = resolver.get_archzfs_requirements(kernel)

        # Find AUR commit for the required zfs-utils version
        commit = resolver.find_aur_commit(info["zfs_utils_version"])

        return cls(
            kernel_package=kernel,
            kernel_version=info["kernel_version"],
            zfs_utils_version=info["zfs_utils_version"],
            zfs_utils_commit=commit,
            zfs_module_version=info.get("zfs_module_version"),
        )

    @classmethod
    def auto_detect_with_fallback(cls) -> "PinningConfig":
        """Auto-detect versions, trying LTS first then standard kernel.

        Strategy:
        1. Try linux-lts with zfs-linux-lts (more stable for ZFS)
        2. If fails, fall back to linux with zfs-linux

        Returns:
            PinningConfig with detected versions
        """
        print("=" * 60, flush=True)
        print("AUTO-DETECTING COMPATIBLE KERNEL/ZFS VERSIONS", flush=True)
        print("=" * 60, flush=True)

        # Try LTS first (preferred for ZFS stability)
        try:
            print("\n[1/2] Trying linux-lts kernel (preferred for ZFS)...", flush=True)
            config = cls.auto_detect(kernel="linux-lts")
            print("  ✓ Found compatible LTS!", flush=True)
            print(f"    Kernel: {config.kernel_version}", flush=True)
            print(f"    ZFS utils: {config.zfs_utils_version}", flush=True)
            print("=" * 60, flush=True)
            return config
        except Exception as e:
            print(f"  ✗ LTS not available: {e}", flush=True)

        # Fallback to standard kernel
        try:
            print("\n[2/2] Falling back to standard linux kernel...", flush=True)
            config = cls.auto_detect(kernel="linux")
            print("  ✓ Found compatible standard kernel!", flush=True)
            print(f"    Kernel: {config.kernel_version}", flush=True)
            print(f"    ZFS utils: {config.zfs_utils_version}", flush=True)
            print("=" * 60, flush=True)
            return config
        except Exception as e:
            print(f"  ✗ Standard kernel also failed: {e}", flush=True)
            print("=" * 60, flush=True)
            raise RuntimeError(f"No compatible kernel/ZFS combination found: {e}") from e

    @property
    def zfs_module_package(self) -> str:
        """Get the zfs-linux-* package name for this kernel."""
        if self.kernel_package == "linux":
            return "zfs-linux"
        elif self.kernel_package == "linux-lts":
            return "zfs-linux-lts"
        else:
            # For other kernels like linux-zen, linux-hardened
            suffix = self.kernel_package.replace("linux-", "")
            return f"zfs-linux-{suffix}"

    def validate(self) -> list[str]:
        """Validate the configuration.

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        if not self.kernel_package:
            errors.append("kernel_package is required")

        if self.kernel_version and not self._is_valid_version(self.kernel_version):
            errors.append(f"Invalid kernel_version format: {self.kernel_version}")

        if self.zfs_utils_commit and len(self.zfs_utils_commit) < 7:
            errors.append("zfs_utils_commit should be at least 7 characters")

        return errors

    @staticmethod
    def _is_valid_version(version: str) -> bool:
        """Check if version string is valid."""
        # Basic validation: should have format like "6.12.29-1"
        import re
        return bool(re.match(r"^\d+\.\d+\.\d+(-\d+)?$", version))

    def __post_init__(self):
        """Convert work_dir to Path if string."""
        if isinstance(self.work_dir, str):
            self.work_dir = Path(self.work_dir)


@dataclass
class CompatibilityResult:
    """Result of a kernel/ZFS compatibility check.

    Attributes:
        compatible: Whether current system is compatible
        current_kernel: Currently installed kernel version
        required_kernel: Kernel version required by archzfs
        current_zfs_utils: Currently installed zfs-utils version
        required_zfs_utils: zfs-utils version required
        action_needed: Description of action needed
    """

    compatible: bool
    current_kernel: str
    required_kernel: str
    current_zfs_utils: str = ""
    required_zfs_utils: str = ""
    action_needed: str = "none"

    def __str__(self) -> str:
        if self.compatible:
            return f"System compatible (kernel={self.current_kernel})"
        return (
            f"Incompatible: kernel {self.current_kernel} -> {self.required_kernel}, "
            f"action: {self.action_needed}"
        )


@dataclass
class UpdateResult:
    """Result of an update operation.

    Attributes:
        success: Whether update succeeded
        boot_environment: Name of the created boot environment
        actions_taken: List of actions performed
        error: Error message if failed
    """

    success: bool
    boot_environment: str = ""
    actions_taken: list[str] = field(default_factory=list)
    error: str | None = None

    def __str__(self) -> str:
        if self.success:
            return f"Update successful (BE: {self.boot_environment})"
        return f"Update failed: {self.error}"
