# Q-CacheFlow Pipeline

本目录实现论文中的核心系统路径：

```text
用户提交 job
  -> Circuit Profiler
  -> Compiler Cache
  -> Backend Estimator
  -> SLO-aware Scheduler
  -> Event-driven Simulator
```

## 设计重点

Q-CacheFlow 将 compiler cache state 当作云调度的一等资源，而不是只把 cache 当作单程序编译加速器。

三级 cache 状态会进入 backend estimate：

- Level 1 Template Cache：参数无关 circuit 结构。
- Level 2 Backend-Structural Cache：backend topology/basis/compiler version 下的 layout/routing 结果。
- Level 3 Calibration-Metadata Cache：当前 calibration epoch 下的 fidelity 和 execution-time metadata。

调度器使用这些状态做：

- backend selection；
- admission/rejection；
- deadline/fidelity SLO 判断；
- batch grouping；
- invalidation-aware metadata refresh。

