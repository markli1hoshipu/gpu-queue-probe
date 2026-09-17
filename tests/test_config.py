from pathlib import Path

from gpu_queue_probe.config import Config


def test_load_example():
    config = Config.load(Path("config/example.json"))
    assert config.cluster == "cluster-a"
    assert config.gpu_counts == (1, 2)
    assert config.gpu_sbatch_args == {}
    assert config.publish_seconds >= 60
