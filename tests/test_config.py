"""Basic tests for zfspin configuration."""
import pytest

from zfspin.config import PinningConfig, CompatibilityResult


def test_pinning_config_defaults():
    """Test PinningConfig default values."""
    config = PinningConfig()
    assert config.kernel_package == "linux-lts"
    assert config.kernel_version is None
    assert config.zfs_utils_version is None
    assert config.arch_archive_url == "https://archive.archlinux.org/packages"


def test_pinning_config_validate_empty():
    """Test validation with defaults."""
    config = PinningConfig()
    errors = config.validate()
    assert len(errors) == 0


def test_pinning_config_validate_short_commit():
    """Test validation catches short commit hashes."""
    config = PinningConfig(zfs_utils_commit="abc")
    errors = config.validate()
    assert any("7 characters" in e for e in errors)


def test_pinning_config_zfs_module_package():
    """Test ZFS module package name derivation."""
    config = PinningConfig(kernel_package="linux-lts")
    assert config.zfs_module_package == "zfs-linux-lts"

    config = PinningConfig(kernel_package="linux")
    assert config.zfs_module_package == "zfs-linux"

    config = PinningConfig(kernel_package="linux-zen")
    assert config.zfs_module_package == "zfs-linux-zen"


def test_compatibility_result_str():
    """Test CompatibilityResult string representation."""
    result = CompatibilityResult(
        compatible=True,
        current_kernel="6.12.29-1",
        required_kernel="6.12.29",
    )
    assert "compatible" in str(result).lower()

    result = CompatibilityResult(
        compatible=False,
        current_kernel="6.11.0-1",
        required_kernel="6.12.29",
        action_needed="update_kernel",
    )
    assert "incompatible" in str(result).lower()
