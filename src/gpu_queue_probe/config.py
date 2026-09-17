from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path


@dataclass(frozen=True)
class Config:
    cluster: str
    qos: str = "high"
    gpu_counts: tuple[int, ...] = (1, 2)
    poll_seconds: int = 15
    publish_seconds: int = 300
    job_timeout_seconds: int = 86400
    job_prefix: str = "gpuqprobe"
    state_dir: Path = Path("var/data")
    log_dir: Path = Path("var/logs")
    repository: str = ""
    metrics_branch: str = ""
    ssh_key_path: Path | None = None
    encryption_key_file: Path | None = None
    sbatch_gpu_flag: str = "--gpus={count}"
    gpu_sbatch_args: dict[int, tuple[str, ...]] = field(default_factory=dict)
    extra_sbatch_args: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        config_path = Path(path)
        with config_path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        base = config_path.parent.parent.resolve()
        state_dir = Path(raw.get("state_dir", "var/data"))
        log_dir = Path(raw.get("log_dir", "var/logs"))
        if not state_dir.is_absolute():
            state_dir = base / state_dir
        if not log_dir.is_absolute():
            log_dir = base / log_dir
        ssh_key_path = raw.get("ssh_key_path")
        encryption_key_file = raw.get("encryption_key_file")
        return cls(
            cluster=str(raw["cluster"]),
            qos=str(raw.get("qos", "high")),
            gpu_counts=tuple(int(v) for v in raw.get("gpu_counts", [1, 2])),
            poll_seconds=max(5, int(raw.get("poll_seconds", 15))),
            publish_seconds=max(60, int(raw.get("publish_seconds", 300))),
            job_timeout_seconds=max(60, int(raw.get("job_timeout_seconds", 86400))),
            job_prefix=str(raw.get("job_prefix", "gpuqprobe")),
            state_dir=state_dir,
            log_dir=log_dir,
            repository=str(raw.get("repository", "")),
            metrics_branch=str(raw.get("metrics_branch", f"metrics-{raw['cluster']}")),
            ssh_key_path=Path(ssh_key_path).expanduser() if ssh_key_path else None,
            encryption_key_file=(
                Path(encryption_key_file).expanduser()
                if encryption_key_file else None
            ),
            sbatch_gpu_flag=str(raw.get("sbatch_gpu_flag", "--gpus={count}")),
            gpu_sbatch_args={
                int(count): tuple(str(arg) for arg in args)
                for count, args in raw.get("gpu_sbatch_args", {}).items()
            },
            extra_sbatch_args=tuple(str(v) for v in raw.get("extra_sbatch_args", [])),
        )
