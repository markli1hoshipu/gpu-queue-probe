# GPU Queue Probe

一个有上限、低干扰的 Slurm GPU 排队延迟探针，以及对应的 GitHub Pages 公共仪表盘。

每个集群始终最多保留两个探针作业：一个请求 1 GPU，另一个请求 2 GPU，均使用 `qos=high`。作业获得资源后只记录启动标记并立即退出；控制器观察终态后才提交替代作业，因此不会无限堆积任务。

## 指标

- 当前所有可见 GPU pending 作业数
- pending 作业声明的 GPU 数量（取决于集群可见性和 GRES 格式）
- 当前所有可见 GPU running 作业数
- 1 GPU 与 2 GPU 探针的提交、可调度、启动和结束时间
- `queue_wait_seconds`：启动时间减提交时间
- `scheduler_delay_seconds`：启动时间减 eligible 时间
- 最近 200 个已完成探针的等待时间序列，用于网页趋势图、中位数和 P95

这些数据反映当前账户、QoS、分区约束和 GPU 数量下的调度体验，不应解释为整个集群的绝对利用率。

## 本地安装

要求 Python 3.9+、Slurm 客户端与 Git。

```bash
./scripts/install.sh
cp config/example.json config/local.json
# 编辑 cluster、repository、metrics_branch 和可能的 sbatch 参数
./scripts/start.sh
```

另一个集群使用相同仓库，但设置不同的 `cluster` 和 `metrics_branch`。推荐分支名：

- `metrics-cluster-a`
- `metrics-gb10`

如果不同 GPU 数量需要不同的 Slurm 参数，可在本地配置中加入：

```json
"gpu_sbatch_args": {
  "1": ["--partition=gb10", "--nodes=1", "--gres=gpu:1"],
  "2": ["--partition=gb10", "--nodes=2", "--gres=gpu:1"]
}
```

发布端必须使用仓库专用、可写的 SSH deploy key。不要把个人 GitHub token 或 SSH 密码复制到集群。

## 运行管理

```bash
./scripts/status.sh
./scripts/stop.sh       # 只取消 state.json 中明确跟踪的探针作业
```

`systemd/gpu-queue-probe.service` 可安装为用户服务。启用前应先运行一次 `once` 并确认 GPU 参数与队列统计符合目标集群的 Slurm 配置。

## GitHub Pages

主分支中的 Actions 工作流发布 `docs/`。网页从各 metrics 分支读取最新快照。每个发布都是一个无父提交并强制更新其专属分支，因此 metrics 分支不会积累无界 Git 历史；最近 200 个完成样本包含在快照内。

如需保护某个集群的指标，可在该集群的本地配置中设置 `encryption_key_file`。发布器会使用 PBKDF2-SHA256 与 AES-256-GCM 生成 `data/latest.enc.json`，GitHub 上不出现明文指标，浏览器输入密码后本地解密。该模式需要 Python `cryptography` 包。

## 安全和限流

- 每个 GPU 规格最多一个未完成探针。
- 默认 60 秒检查一次、5 分钟向 GitHub 发布一次。
- 凭据不进入仓库；metrics 分支不包含用户名、命令或其他用户的作业明细。
- 加密发布密码只保存在目标集群的权限受限文件中，不写入 Git 或网页代码。
- `stop.sh` 不使用宽泛的作业名匹配，只取消本地状态文件记录的 job ID。
