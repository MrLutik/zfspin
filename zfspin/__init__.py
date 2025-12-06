"""
zfspin - ZFS/Kernel Pinning for Arch Linux

This package provides tools for managing kernel/ZFS version compatibility
in Arch Linux systems using prebuilt ZFS packages from archzfs.com.

Key features:
- Auto-detect compatible kernel/ZFS versions from archzfs repository
- Download specific kernel versions from Arch Archive
- Build zfs-utils from AUR at specific commits
- Create local pacman repositories for pinned packages
- Orchestrate safe system updates with ZFS boot environments
"""
from __future__ import annotations

from zfspin.config import PinningConfig
from zfspin.utils import setup_logging, acquire_lock, run_command, log

__version__ = "0.1.0"
__all__ = [
    "PinningConfig",
    "setup_logging",
    "acquire_lock",
    "run_command",
    "log",
]

# Lazy imports for heavy modules
def __getattr__(name: str):
    """Lazy import for optional modules."""
    if name == "VersionResolver":
        from zfspin.versions import VersionResolver
        return VersionResolver
    if name == "ArchiveDownloader":
        from zfspin.downloader import ArchiveDownloader
        return ArchiveDownloader
    if name == "AURBuilder":
        from zfspin.builder import AURBuilder
        return AURBuilder
    if name == "LocalRepository":
        from zfspin.repository import LocalRepository
        return LocalRepository
    if name == "ZFSPinUpdater":
        from zfspin.updater import ZFSPinUpdater
        return ZFSPinUpdater
    raise AttributeError(f"module 'zfspin' has no attribute {name!r}")
