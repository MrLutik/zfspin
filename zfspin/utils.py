"""Utility functions for zfspin package."""
from __future__ import annotations

import fcntl
import logging
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator

# Module logger
log = logging.getLogger("zfspin")


def setup_logging(log_file: str | Path | None = None, level: int = logging.INFO) -> None:
    """Configure logging for zfspin.

    Args:
        log_file: Optional path to log file
        level: Logging level (default: INFO)
    """
    log.setLevel(level)

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    log.addHandler(console)

    # File handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file, mode='a')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        log.addHandler(file_handler)


@contextmanager
def acquire_lock(lock_file: str | Path) -> Generator[None, None, None]:
    """Context manager to acquire an exclusive file lock.

    Args:
        lock_file: Path to the lock file

    Raises:
        RuntimeError: If lock cannot be acquired
    """
    lock_path = Path(lock_file)
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    fd = open(lock_path, 'w')
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        log.debug(f"Acquired lock: {lock_path}")
        yield
    except BlockingIOError:
        fd.close()
        raise RuntimeError(f"Could not acquire lock: {lock_path}")
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        fd.close()


def run_command(
    cmd: list[str],
    check: bool = True,
    capture_output: bool = True,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: int | None = None,
    text: bool = True,
) -> subprocess.CompletedProcess:
    """Run a command with logging.

    Args:
        cmd: Command and arguments as list
        check: Raise exception on non-zero exit (default: True)
        capture_output: Capture stdout/stderr (default: True)
        cwd: Working directory
        env: Environment variables (merged with current env)
        timeout: Command timeout in seconds
        text: Decode output as text (default: True). Set False for binary.

    Returns:
        CompletedProcess instance

    Raises:
        subprocess.CalledProcessError: If check=True and command fails
        subprocess.TimeoutExpired: If timeout is exceeded
    """
    import os

    cmd_str = ' '.join(cmd)
    log.debug(f"Running: {cmd_str}")

    # Merge environment
    run_env = os.environ.copy()
    if env:
        run_env.update(env)

    result = subprocess.run(
        cmd,
        check=False,
        capture_output=capture_output,
        text=text,
        cwd=cwd,
        env=run_env,
        timeout=timeout,
    )

    if result.returncode != 0:
        log.warning(f"Command failed (exit {result.returncode}): {cmd_str}")
        if result.stderr and text:
            for line in result.stderr.strip().split('\n')[:10]:
                log.warning(f"  stderr: {line}")

    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, cmd, result.stdout, result.stderr
        )

    return result


def download_file(url: str, dest: Path, timeout: int = 300, show_progress: bool = True) -> Path:
    """Download a file using curl.

    Args:
        url: URL to download
        dest: Destination path
        timeout: Download timeout in seconds
        show_progress: Show download progress bar

    Returns:
        Path to downloaded file

    Raises:
        RuntimeError: If download fails
    """
    log.info(f"Downloading: {url}")

    dest.parent.mkdir(parents=True, exist_ok=True)

    # Use --progress-bar for visible progress, run without capturing output
    curl_cmd = ["curl", "-fL", "--progress-bar", "-o", str(dest), url]

    try:
        # Run directly without capturing to show progress
        subprocess.run(
            curl_cmd,
            check=True,
            timeout=timeout,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to download {url}") from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"Download timed out after {timeout}s: {url}") from e

    if not dest.exists():
        raise RuntimeError(f"Download completed but file not found: {dest}")

    log.info(f"Downloaded: {dest.name} ({dest.stat().st_size / 1024 / 1024:.1f} MB)")
    return dest


def fetch_url(url: str, timeout: int = 30) -> str:
    """Fetch URL content as string.

    Args:
        url: URL to fetch
        timeout: Request timeout in seconds

    Returns:
        Response body as string
    """
    result = run_command(
        ["curl", "-fsSL", url],
        timeout=timeout,
    )
    return result.stdout
