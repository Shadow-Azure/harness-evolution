# Experiments

每次实验使用一个独立目录，命名格式为 `YYYY-MM-DD-<slug>`。

```bash
cp -R experiments/_template experiments/2026-10-19-example
```

约定：

- 一次实验只验证一个主要变量。
- baseline 与 treatment 使用相同任务集、环境和随机种子。
- 先写假设与决策规则，再运行实验。
- 结果、异常和回滚方式都必须记录。
- 不提交 `runs/` 下的原始产物，只提交摘要与必要的复现实验信息。
