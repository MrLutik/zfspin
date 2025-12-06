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

## Contributing

### Branch Naming Convention

| Branch Type | Pattern | Example |
|-------------|---------|---------|
| Feature | `feature/*` | `feature/add-rollback-ui` |
| Bug Fix | `bugfix/*` | `bugfix/fix-snapshot-name` |
| Hotfix | `hotfix/*` | `hotfix/critical-boot-fix` |

### Development Workflow

1. **Fork & Clone**
   ```bash
   git clone https://github.com/YOUR_USERNAME/zfspin.git
   cd zfspin
   ```

2. **Create Branch** (use appropriate prefix)
   ```bash
   git checkout -b feature/my-new-feature
   # or
   git checkout -b bugfix/fix-something
   # or
   git checkout -b hotfix/urgent-fix
   ```

3. **Make Changes & Push**
   ```bash
   git add .
   git commit -m "Add my new feature"
   git push origin feature/my-new-feature
   ```

   On push, CI automatically:
   - Runs linter and tests
   - Creates a Pull Request to `main`

4. **Merge Pull Request**
   - Review and merge PR to `main`
   - Creates a **pre-release** with:
     - Python wheel and source packages
     - AUR package (`.pkg.tar.zst`)
     - Debian package (`.deb`)

### Creating a Release

Pre-releases are created automatically on merge to `main`. To create an **official release**:

```bash
# Create and push a version tag
git checkout main
git pull
git tag v1.0.0
git push origin v1.0.0
```

This triggers the release workflow which:
- Runs all tests
- Builds Python, AUR, and Debian packages
- Creates a GitHub Release with all artifacts

### Local Development

```bash
# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run linter
ruff check .

# Build packages locally (requires Docker)
./packaging/arch/build.sh    # Build AUR package
./packaging/debian/build.sh  # Build Debian package
```

## License

MIT License - see [LICENSE](LICENSE)
