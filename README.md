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

This project uses [Semantic Versioning](https://semver.org/) with automatic version bumping based on branch naming.

### Branch Naming Convention

| Branch Type | Pattern | Version Bump | Example |
|-------------|---------|--------------|---------|
| Feature | `feature/*` | Minor (0.X.0) | `feature/add-rollback-ui` |
| Bug Fix | `bugfix/*` | Patch (0.0.X) | `bugfix/fix-snapshot-name` |
| Hotfix | `hotfix/*` | Patch (0.0.X) | `hotfix/critical-boot-fix` |

### Contribution Workflow

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

4. **Create Pull Request**
   - Open PR against `main` branch
   - CI will run lint, tests, and build checks
   - Wait for review and approval

5. **Merge & Auto-Release**
   - Once merged to `main`, the release workflow automatically:
     - Detects the branch type from merge commit
     - Bumps version accordingly (minor for features, patch for bugfix/hotfix)
     - Updates `pyproject.toml` with new version
     - Creates git tag
     - Publishes to PyPI
     - Builds AUR package
     - Creates GitHub Release

### Local Development

```bash
# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run linter
ruff check .
```

## License

MIT License - see [LICENSE](LICENSE)
