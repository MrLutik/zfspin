"""Command-line interface for zfspin."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from zfspin import PinningConfig, setup_logging, log
from zfspin.versions import VersionResolver
from zfspin.updater import ZFSPinUpdater


def cmd_check(args: argparse.Namespace) -> int:
    """Check kernel/ZFS compatibility."""
    kernel = args.kernel or "linux-lts"

    log.info(f"Checking compatibility for {kernel}...")

    resolver = VersionResolver()

    # Get requirements from archzfs
    try:
        requirements = resolver.get_archzfs_requirements(kernel)
        log.info(f"archzfs requires:")
        log.info(f"  Kernel: {requirements['kernel_version']}")
        log.info(f"  ZFS utils: {requirements['zfs_utils_version']}")
        log.info(f"  ZFS module: {requirements['zfs_module_version']}")
    except Exception as e:
        log.error(f"Failed to get archzfs requirements: {e}")
        return 1

    # Check compatibility
    compat = resolver.check_compatibility(kernel)

    if compat.compatible:
        log.info("✓ System is compatible with archzfs")
        return 0
    else:
        log.warning(f"✗ System is not compatible:")
        log.warning(f"  Current kernel: {compat.current_kernel}")
        log.warning(f"  Required kernel: {compat.required_kernel}")
        log.warning(f"  Action needed: {compat.action_needed}")
        return 1


def cmd_resolve(args: argparse.Namespace) -> int:
    """Resolve compatible versions."""
    kernel = args.kernel or "linux-lts"

    log.info(f"Resolving versions for {kernel}...")

    try:
        config = PinningConfig.auto_detect(kernel)

        print(f"Kernel package: {config.kernel_package}")
        print(f"Kernel version: {config.kernel_version}")
        print(f"ZFS utils version: {config.zfs_utils_version}")
        print(f"ZFS utils commit: {config.zfs_utils_commit}")
        print(f"ZFS module version: {config.zfs_module_version}")

        return 0

    except Exception as e:
        log.error(f"Failed to resolve versions: {e}")
        return 1


def cmd_update(args: argparse.Namespace) -> int:
    """Run a safe system update."""
    import os

    if os.geteuid() != 0:
        log.error("This command must be run as root")
        return 1

    kernel = args.kernel or "linux-lts"
    zfs_pool = args.pool or "zroot"

    log.info("Starting safe system update...")

    try:
        config = PinningConfig.auto_detect(kernel)
        updater = ZFSPinUpdater(config, zfs_pool=zfs_pool)

        result = updater.full_update(
            dry_run=args.dry_run,
            skip_be=args.no_be,
        )

        if result.success:
            log.info("Update completed successfully!")
            if result.boot_environment:
                log.info(f"Boot environment: {result.boot_environment}")
            log.info("Reboot to apply changes.")
            return 0
        else:
            log.error(f"Update failed: {result.error}")
            return 1

    except Exception as e:
        log.error(f"Update failed: {e}")
        return 1


def cmd_build(args: argparse.Namespace) -> int:
    """Build pinned packages only (don't update)."""
    import os

    if os.geteuid() != 0:
        log.error("This command must be run as root")
        return 1

    kernel = args.kernel or "linux-lts"
    output_dir = Path(args.output) if args.output else Path("/var/cache/zfspin/pinned")

    log.info(f"Building pinned packages for {kernel}...")

    try:
        from zfspin.downloader import ArchiveDownloader
        from zfspin.builder import AURBuilder
        from zfspin.repository import LocalRepository
        import tempfile

        config = PinningConfig.auto_detect(kernel)
        work_dir = Path(tempfile.mkdtemp(prefix="zfspin-build-"))

        # Create repository
        repo = LocalRepository(output_dir)
        repo.create()

        # Download kernel
        downloader = ArchiveDownloader(config, work_dir)
        kernel_pkgs = downloader.download_kernel_packages()
        repo.add_packages(kernel_pkgs)

        # Build zfs-utils
        builder = AURBuilder(config, work_dir)
        zfs_pkg = builder.build_zfs_utils(dest_dir=output_dir)
        repo.add_package(zfs_pkg)

        log.info(f"Packages built in: {output_dir}")
        log.info("Packages:")
        for pkg in repo.list_packages():
            log.info(f"  {pkg}")

        return 0

    except Exception as e:
        log.error(f"Build failed: {e}")
        return 1


def cmd_lock(args: argparse.Namespace) -> int:
    """Manage kernel package lock."""
    from zfspin.updater import KernelLock

    lock = KernelLock()

    if args.action == "status":
        if lock.is_locked():
            log.info("Kernel packages are LOCKED")
            log.info("Locked packages: " + ", ".join(lock.get_locked_packages()))
            log.info("Regular 'pacman -Syu' will NOT update kernel packages")
        else:
            log.warning("Kernel packages are UNLOCKED")
            log.warning("Regular 'pacman -Syu' CAN update kernel packages (may break ZFS)")
        return 0

    elif args.action == "enable":
        if lock.is_locked():
            log.info("Kernel packages already locked")
        else:
            lock.lock()
            log.info("Kernel packages locked")
            log.info("Use 'zfspin update' for safe kernel updates")
        return 0

    elif args.action == "disable":
        if not lock.is_locked():
            log.info("Kernel packages not locked")
        else:
            lock.unlock()
            log.warning("Kernel packages unlocked")
            log.warning("Be careful with 'pacman -Syu' - it may break ZFS!")
        return 0

    else:
        log.error(f"Unknown action: {args.action}")
        return 1


def main(argv: list[str] | None = None) -> int:
    """Main entry point for zfspin CLI."""
    parser = argparse.ArgumentParser(
        prog="zfspin",
        description="ZFS/Kernel pinning for Arch Linux",
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output",
    )

    parser.add_argument(
        "--log-file",
        type=str,
        help="Log to file",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # check command
    check_parser = subparsers.add_parser("check", help="Check kernel/ZFS compatibility")
    check_parser.add_argument("-k", "--kernel", help="Kernel package (default: linux-lts)")

    # resolve command
    resolve_parser = subparsers.add_parser("resolve", help="Resolve compatible versions")
    resolve_parser.add_argument("-k", "--kernel", help="Kernel package (default: linux-lts)")

    # update command
    update_parser = subparsers.add_parser("update", help="Run safe system update")
    update_parser.add_argument("-k", "--kernel", help="Kernel package (default: linux-lts)")
    update_parser.add_argument("-p", "--pool", help="ZFS pool name (default: zroot)")
    update_parser.add_argument("-n", "--dry-run", action="store_true", help="Show what would be done")
    update_parser.add_argument("--no-be", action="store_true", help="Skip boot environment creation")

    # build command
    build_parser = subparsers.add_parser("build", help="Build pinned packages")
    build_parser.add_argument("-k", "--kernel", help="Kernel package (default: linux-lts)")
    build_parser.add_argument("-o", "--output", help="Output directory")

    # lock command
    lock_parser = subparsers.add_parser("lock", help="Manage kernel package lock")
    lock_parser.add_argument(
        "action",
        choices=["status", "enable", "disable"],
        help="status: show lock state, enable: lock packages, disable: unlock packages"
    )

    args = parser.parse_args(argv)

    # Setup logging
    import logging
    level = logging.DEBUG if args.verbose else logging.INFO
    setup_logging(args.log_file, level)

    if not args.command:
        parser.print_help()
        return 0

    # Dispatch to command handler
    commands = {
        "check": cmd_check,
        "resolve": cmd_resolve,
        "update": cmd_update,
        "build": cmd_build,
        "lock": cmd_lock,
    }

    handler = commands.get(args.command)
    if handler:
        return handler(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
