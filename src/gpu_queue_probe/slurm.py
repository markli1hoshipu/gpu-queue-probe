from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import getpass
import re
import subprocess
from pathlib import Path


TERMINAL_STATES = {
    "BOOT_FAIL", "CANCELLED", "COMPLETED", "DEADLINE", "FAILED",
    "NODE_FAIL", "OUT_OF_MEMORY", "PREEMPTED", "TIMEOUT",
}


def probe_job_name(config, gpu_count: int) -> str:
    return f"{config.job_prefix}-{config.cluster}-{gpu_count}g"


@dataclass(frozen=True)
class JobStatus:
    job_id: str
    state: str
    submit: str = ""
    eligible: str = ""
    start: str = ""
    end: str = ""
    reason: str = ""
    node_list: str = ""
    exit_code: str = ""


def run(command: list[str], *, timeout: int = 30) -> str:
    result = subprocess.run(
        command, check=True, text=True, capture_output=True, timeout=timeout
    )
    return result.stdout.strip()


def submit_probe(config, gpu_count: int, probe_script: Path) -> str:
    output_path = config.log_dir / f"probe-{gpu_count}g-%j.log"
    gpu_args = config.gpu_sbatch_args.get(
        gpu_count, (config.sbatch_gpu_flag.format(count=gpu_count),)
    )
    command = [
        "sbatch", "--parsable",
        f"--job-name={probe_job_name(config, gpu_count)}",
        f"--qos={config.qos}",
        *gpu_args,
        f"--output={output_path}",
        *config.extra_sbatch_args,
        str(probe_script), str(gpu_count), config.cluster,
    ]
    value = run(command)
    job_id = value.split(";", 1)[0]
    if not re.fullmatch(r"\d+(?:_\d+)?", job_id):
        raise RuntimeError(f"Unexpected sbatch job id: {value!r}")
    return job_id


def find_active_probe(config, gpu_count: int) -> str | None:
    text = run([
        "squeue", "-h", "-u", getpass.getuser(),
        "-n", probe_job_name(config, gpu_count), "-o", "%i",
    ])
    job_ids = [line.strip() for line in text.splitlines() if line.strip()]
    if len(job_ids) > 1:
        raise RuntimeError(
            f"Multiple active probes found for {gpu_count} GPUs: {job_ids}"
        )
    return job_ids[0] if job_ids else None


def query_job(job_id: str) -> JobStatus | None:
    active = run(["squeue", "-h", "-j", job_id, "-o", "%i|%T|%V|%S|%R|%N"])
    if active:
        fields = active.splitlines()[0].split("|")
        fields += [""] * (6 - len(fields))
        actual_start = "" if fields[1] in {"PENDING", "CONFIGURING"} else fields[3]
        return JobStatus(fields[0], fields[1], submit=fields[2], start=actual_start, reason=fields[4], node_list=fields[5])

    accounting = run([
        "sacct", "-n", "-P", "-X", "-j", job_id,
        "--format=JobIDRaw,State,Submit,Eligible,Start,End,Reason,NodeList,ExitCode",
    ])
    for line in accounting.splitlines():
        fields = line.split("|")
        if fields and fields[0] == job_id:
            fields += [""] * (9 - len(fields))
            return JobStatus(
                fields[0], fields[1].split()[0], fields[2], fields[3], fields[4],
                fields[5], fields[6], fields[7], fields[8],
            )
    return None


def parse_gpu_demand(resources: str, nodes: int) -> int:
    matches = re.findall(r"(?:gpu(?::[^:,]+)?[:=])(\d+)", resources, re.I)
    per_node = sum(int(value) for value in matches)
    return per_node * max(nodes, 1)


def queue_snapshot(qos: str) -> dict[str, int | str]:
    # Count every visible GPU job, not only one QoS. Some site job-submit
    # plugins accept a virtual QoS such as "high" but expose it as blank in
    # squeue. %D is needed because GRES is commonly expressed per node.
    text = run(["squeue", "-h", "-o", "%q|%T|%D|%b"])
    pending_jobs = running_jobs = pending_gpu_demand = 0
    for line in text.splitlines():
        fields = line.split("|", 3)
        if len(fields) != 4:
            continue
        _actual_qos, state, node_text, resources = fields
        try:
            nodes = int(node_text)
        except ValueError:
            nodes = 1
        gpu_demand = parse_gpu_demand(resources, nodes)
        if not gpu_demand:
            continue
        if state == "PENDING":
            pending_jobs += 1
            pending_gpu_demand += gpu_demand
        elif state == "RUNNING":
            running_jobs += 1
    return {
        "scope": "all_visible_gpu_jobs",
        "probe_qos": qos,
        "pending_jobs": pending_jobs,
        "pending_gpu_demand": pending_gpu_demand,
        "running_jobs": running_jobs,
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }


def cancel(job_id: str) -> None:
    run(["scancel", job_id])
