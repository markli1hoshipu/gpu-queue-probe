from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import tempfile


def _encrypted_payload(snapshot_path: Path, password: str) -> bytes:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        from cryptography.hazmat.primitives import hashes
    except ImportError as error:
        raise RuntimeError(
            "Encrypted publication requires the Python cryptography package"
        ) from error

    salt = os.urandom(16)
    nonce = os.urandom(12)
    iterations = 310_000
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations
    )
    key = kdf.derive(password.encode("utf-8"))
    ciphertext = AESGCM(key).encrypt(nonce, snapshot_path.read_bytes(), None)
    envelope = {
        "version": 1,
        "algorithm": "AES-256-GCM",
        "kdf": "PBKDF2-SHA256",
        "iterations": iterations,
        "salt": base64.b64encode(salt).decode("ascii"),
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
    }
    return (json.dumps(envelope, separators=(",", ":")) + "\n").encode("utf-8")


def _git(args: list[str], cwd: Path, env: dict[str, str]) -> None:
    subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True, timeout=60)


def publish_snapshot(config, snapshot_path: Path) -> None:
    """Force-publish one parentless snapshot commit to this cluster's branch.

    The branch intentionally contains no history. Each cluster uses a unique
    branch, so concurrent publishers cannot conflict.
    """
    env = os.environ.copy()
    env.setdefault("GIT_AUTHOR_NAME", "GPU Queue Probe")
    env.setdefault("GIT_AUTHOR_EMAIL", "gpu-queue-probe@users.noreply.github.com")
    env.setdefault("GIT_COMMITTER_NAME", env["GIT_AUTHOR_NAME"])
    env.setdefault("GIT_COMMITTER_EMAIL", env["GIT_AUTHOR_EMAIL"])
    if config.ssh_key_path:
        key = shlex.quote(str(config.ssh_key_path))
        env["GIT_SSH_COMMAND"] = (
            f"ssh -i {key} -o IdentitiesOnly=yes "
            "-o StrictHostKeyChecking=accept-new"
        )
    with tempfile.TemporaryDirectory(prefix="gpuqprobe-publish-") as temp:
        directory = Path(temp)
        _git(["init", "-q"], directory, env)
        _git(["remote", "add", "origin", config.repository], directory, env)
        data_dir = directory / "data"
        data_dir.mkdir()
        if config.encryption_key_file:
            password = config.encryption_key_file.read_text(encoding="utf-8").strip()
            if len(password) < 16:
                raise RuntimeError("The publication password must be at least 16 characters")
            target = data_dir / "latest.enc.json"
            target.write_bytes(_encrypted_payload(snapshot_path, password))
        else:
            target = data_dir / "latest.json"
            shutil.copy2(snapshot_path, target)
        _git(["add", str(target.relative_to(directory))], directory, env)
        _git(["commit", "-q", "-m", f"Update {config.cluster} metrics"], directory, env)
        _git(["push", "--force", "origin", f"HEAD:{config.metrics_branch}"], directory, env)
