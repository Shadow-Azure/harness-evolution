# Harness

放置被测 harness 或其适配层。

建议保持一个稳定接口，便于评测器与演化流程复用：

```text
reset(task) -> state
step(state, observation) -> action
run(task) -> trajectory
```

harness 的行为应尽量由配置驱动，例如提示模板、工具白名单、上下文预算和重试策略。这样实验可以只改一个配置项，而不必复制整套实现。
