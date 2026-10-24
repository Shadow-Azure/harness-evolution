import { useEffect, useState } from "react";
import type { HealthResponse } from "@harness/contracts";

const plannedModules = [
  {
    index: "01",
    title: "轨迹导入",
    description: "读取 Codex rollout JSONL，增量导入并保留原始事件。"
  },
  {
    index: "02",
    title: "Session 浏览",
    description: "按轮次查看消息、工具调用、错误、token 与耗时。"
  },
  {
    index: "03",
    title: "AI 诊断",
    description: "让模型定位目标偏移、重复重试、验证缺口等问题。"
  },
  {
    index: "04",
    title: "问题看板",
    description: "把问题回链到轨迹，并沉淀为 skill / agent 改进项。"
  }
];

/**
 * 应用根组件：展示服务连接状态与已规划的垂直切片。
 * @returns 轨迹诊断台的页面骨架。
 */
export function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/health")
      .then(async (response) => {
        const payload = (await response.json()) as HealthResponse;
        if (!response.ok && response.status !== 503) {
          throw new Error(`HTTP ${response.status}`);
        }
        setHealth(payload);
      })
      .catch((error: unknown) => {
        setConnectionError(error instanceof Error ? error.message : String(error));
      });
  }, []);

  const databaseLabel = health?.db.dialect === "mysql" ? "MySQL" : "SQLite";
  const status = health?.db.ok
    ? `API 已连接 · ${databaseLabel}`
    : health
      ? "数据库异常"
    : connectionError
      ? "API 未连接"
      : "连接中…";
  const statusClass = health?.db.ok ? "ok" : health || connectionError ? "error" : "";

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">HL</span>
          <div>
            <strong>Harness Lens</strong>
            <span>Agent 轨迹诊断台</span>
          </div>
        </div>
        <div className={`status-pill ${statusClass}`}>
          <span className="status-dot" />
          {status}
        </div>
      </header>

      <main>
        <section className="hero">
          <span className="eyebrow">SCAFFOLD · M1</span>
          <h1>
            看清 agent 每一步，
            <br />
            再决定怎么进化。
          </h1>
          <p>
            面向 Codex 等 coding agent 的轨迹查看与问题诊断服务。当前只初始化了前后端骨架，
            业务能力会按功能切片逐步接入。
          </p>
          <div className="hero-meta">
            <span>React + Vite</span>
            <span>FastAPI + Python</span>
            <span>{databaseLabel} · {health?.db.ok ? "已连接" : "连接状态检查中"}</span>
          </div>
        </section>

        <section className="module-grid" aria-label="计划模块">
          {plannedModules.map((module) => (
            <article className="module-card" key={module.index}>
              <span className="module-index">{module.index}</span>
              <h2>{module.title}</h2>
              <p>{module.description}</p>
              <span className="module-state">未实现</span>
            </article>
          ))}
        </section>

        <section className="architecture-note">
          <div>
            <span className="note-label">当前边界</span>
            <h2>先有壳，再接肉</h2>
          </div>
          <p>
            前端负责浏览与诊断交互；后端负责导入、存储和分析编排；共享协议放在
            <code> packages/contracts</code>。数据层会先使用 SQLite，但业务只依赖
            repository 接口，后续可替换为 Postgres。
          </p>
        </section>
      </main>

      <footer>
        <span>Harness Evolution</span>
        <span>localhost demo · 本地优先</span>
      </footer>
    </div>
  );
}
