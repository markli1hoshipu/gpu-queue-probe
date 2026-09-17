from gpu_queue_probe.controller import _parse_time
from gpu_queue_probe.slurm import parse_gpu_demand


def test_parse_slurm_time():
    value = _parse_time("2026-09-17T12:30:00")
    assert value is not None
    assert value.year == 2026


def test_parse_unknown_time():
    assert _parse_time("Unknown") is None


def test_parse_gpu_demand_across_nodes():
    assert parse_gpu_demand("gres/gpu:1", 2) == 2
    assert parse_gpu_demand("gres/gpu:model:2", 1) == 2
    assert parse_gpu_demand("N/A", 8) == 0
