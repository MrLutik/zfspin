# zfspin

ZFS/Kernel version pinning for Arch Linux - safe updates with boot environments.

## Problem

On Arch Linux with ZFS, kernel updates can break the system if the ZFS module isn't compatible with the new kernel. This tool:

1. **Pins compatible versions** - Auto-detects compatible kernel/ZFS versions from archzfs.com
2. **Creates boot environments** - Takes ZFS snapshots before updates for safe rollback
3. **Smart fallback** - Prefers LTS kernel, falls back to standard if unavailable

## Installation

### From PyPI (build-time use)

```bash
pip install zfspin
```

### From AUR (system installation)

```bash
yay -S zfspin
# or
paru -S zfspin
```

## Usage

### Check current compatibility

```bash
zfspin check
```

### Resolve compatible versions

```bash
zfspin resolve
```

### Perform safe update

```bash
sudo zfspin update
```

### Lock/unlock kernel packages

```bash
sudo zfspin lock enable   # Add kernel to IgnorePkg
sudo zfspin lock disable  # Remove from IgnorePkg
sudo zfspin lock status   # Show current status
```

## Automatic Updates

Enable the systemd timer for weekly safe updates:

```bash
sudo systemctl enable --now zfspin-update.timer
```

## How It Works

1. **Version Detection**: Scrapes archzfs.com to find compatible kernel/ZFS versions
2. **Package Pinning**: Downloads specific kernel from Arch Archive, builds zfs-utils from AUR
3. **Boot Environments**: Creates ZFS snapshot before update, clones for safe testing
4. **Rollback**: If update fails, automatically rolls back to previous snapshot

## Configuration

zfspin uses auto-detection by default. For manual configuration:

```bash
zfspin update --pool zroot --kernel linux-lts
```

## License

MIT License - see [LICENSE](LICENSE)
