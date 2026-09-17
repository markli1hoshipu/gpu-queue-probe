from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import signal
import time

from . import slurm
from .config import Config
from .publisher import publish_snapshot
from .storage import append_jsonl, load_json, read_jsonl_tail, save_json


LOG = logging.getLogger(__name__)


def _parse_time(value: str) -> datetime | None:
    if not value or value in {"Unknown", "N/A", "None"}:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _observation(config: Config, gpu_count: int, status: slurm.JobStatus) -> dict:
    submitted = _parse_time(status.submit)
    started = _parse_time(status.start)
    eligible = _parse_time(status.eligible)
    return {
        "cluster": config.cluster,
        "job_id": status.job_id,
        "gpu_count": gpu_count,
        "qos": config.qos,
        "state": status.state,
        "submitted_at": status.submit,
        "eligible_at": status.eligible,
        "started_at": status.start,
        "ended_at": status.end,
        "queue_wait_seconds": (started - submitted).total_seconds() if submitted and started else None,
        "scheduler_delay_seconds": (started - eligible).total_seconds() if eligible and started else None,
        "reason": status.reason,
        "node_list": status.node_list,
        "exit_code": status.exit_code,
    }


class Controller:
    def __init__(self, config: Config, root: Path):
        self.config = config
        self.root = root
        self.state_path = config.state_dir / "state.json"
        self.history_path = config.state_dir / "observations.jsonl"
        self.latest_path = config.state_dir / "latest.json"
        self.state = load_json(self.state_path, {"jobs": {}, "last_publish": 0})
        self.stopping = False

    def stop(self, *_args) -> None:
        self.stopping = True

    def reconcile(self) -> None:
        jobs = self.state.setdefault("jobs", {})
        current_probes = {}
        last_observations = self.state.setdefault("last_observations", {})
        for gpu_count in self.config.gpu_counts:
            key = str(gpu_count)
            job_id = jobs.get(key)
            if job_id:
                status = slurm.query_job(job_id)
                if status and status.state in slurm.TERMINAL_STATES:
                    item = _observation(self.config, gpu_count, status)
                    append_jsonl(self.history_path, item)
                    last_observations[key] = item
                    jobs.pop(key, None)
                elif status:
                    current_probes[key] = _observation(self.config, gpu_count, status)
                else:
                    LOG.warning("Job %s disappeared; allowing a replacement", job_id)
                    jobs.pop(key, None)

            if key not in jobs and not self.stopping:
                new_id = slurm.find_active_probe(self.config, gpu_count)
                if new_id:
                    LOG.info("Adopted existing %s-GPU probe %s", gpu_count, new_id)
                else:
                    new_id = slurm.submit_probe(
                        self.config, gpu_count, self.root / "jobs" / "probe.sh"
                    )
                    LOG.info("Submitted %s-GPU probe %s", gpu_count, new_id)
                jobs[key] = new_id
                # Persist immediately: a later queue-snapshot or publication
                # failure must not cause the next cycle to submit a duplicate.
                save_json(self.state_path, self.state)
                current_probes[key] = {
                    "cluster": self.config.cluster,
                    "job_id": new_id,
                    "gpu_count": gpu_count,
                    "qos": self.config.qos,
                    "state": "SUBMITTED",
                }

        snapshot = {
            "schema_version": 1,
            "cluster": self.config.cluster,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "queue": slurm.queue_snapshot(self.config.qos),
            "probes": current_probes,
            "last_completed": last_observations,
            "wait_history": read_jsonl_tail(self.history_path),
        }
        save_json(self.latest_path, snapshot)
        save_json(self.state_path, self.state)

    def maybe_publish(self, force: bool = False) -> None:
        now = time.time()
        last = float(self.state.get("last_publish", 0))
        if not force and now - last < self.config.publish_seconds:
            return
        if self.config.repository:
            publish_snapshot(self.config, self.latest_path)
            self.state["last_publish"] = now
            save_json(self.state_path, self.state)

    def run_forever(self) -> None:
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)
        while not self.stopping:
            try:
                self.reconcile()
                self.maybe_publish()
            except Exception:
                LOG.exception("Probe cycle failed")
            for _ in range(self.config.poll_seconds):
                if self.stopping:
                    break
                time.sleep(1)

    def cancel_owned(self) -> None:
        for job_id in list(self.state.get("jobs", {}).values()):
            slurm.cancel(job_id)
        self.state["jobs"] = {}
        save_json(self.state_path, self.state)
