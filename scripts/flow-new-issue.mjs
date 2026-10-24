#!/usr/bin/env node
// 脚手架：新建 flow issue 三件套（中文 base + 英文侧 + 配对记录），状态
// backlog、github 待回填。用法：
//   pnpm flow:new-issue -- --milestone m1 --id m1-02 --priority P0 --slug excel-viewer \
//     --title 中文标题 --title-en "English title" --scope "src/**,docs/**" --depends "m1-01"
// 生成后补齐实施、验证与验收章节（双侧最小修补），流转 ready 前须 flow:sync 回填编号。

import { mkdir, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import { blobHash, pairPaths, renderPairRecord } from "./translation-pairing-lib.mjs";
import { ISSUE_STATUSES, PRIORITIES, loadFlowTree } from "./flow-lib.mjs";

const FENCE = (id, milestone, priority, depends, scopes) => [
  "```yaml flow",
  "kind: issue",
  `id: ${id}`,
  `milestone: ${milestone}`,
  "depends:",
  ...depends.map((d) => `  - ${d}`),
  `priority: ${priority}`,
  `priority: ${priority}`,
  "status: backlog",
  "scope:",
  ...scopes.map((s) => `  - ${s}`),
  "adr: []",
  "github:",
  "  number: null",
  "  url: null",
  "```",
].join("\n");

/** 生成 issue 三件套。返回三件套路径。 */
export async function createIssue({ root = ".", id, milestone, priority, slug, title, titleEn, scopes, depends = [] }) {
  if (!id || !milestone || !slug || !title || !titleEn || !Array.isArray(scopes) || scopes.length === 0)
    throw new Error("id/milestone/slug/title/title-en/scope 均为必填");
  if (!Array.isArray(depends)) throw new Error("depends 必须是逗号分隔或列表");
  if (!new RegExp(`^${milestone}-\\d{2}$`).test(id))
    throw new Error(`id 必须是 ${milestone}-NN 形式的稳定规划编号`);
  if (!PRIORITIES.includes(priority))
    throw new Error(`priority 必须是 ${PRIORITIES.join(" | ")}`);
  if (!/^[a-z0-9-]+$/.test(slug)) throw new Error(`slug 必须是 kebab-case：${slug}`);
  const { tree, errors } = await loadFlowTree(path.join(root, ".agents/flow"));
  if (errors.length > 0) throw new Error(`流程树有错误：${errors.join("；")}`);
  if (!tree.milestones.some((m) => m.data.id === milestone))
    throw new Error(`milestone ${milestone} 不存在于 roadmap 序列`);

  const name = `${milestone}-${slug}`;
  const base = path.join(root, ".agents/flow/issues", `${name}.md`);
  if (existsSync(base)) throw new Error(`issue 已存在：${base}`);
  const fence = FENCE(id, milestone, priority, depends, scopes);
  const details = (locale) => locale === "zh" ? {
    background: "背景", goal: "目标", authority: "设计依据", implementation: "实现内容", steps: "实施步骤",
    boundary: "依赖与交付边界", verify: "独立验证", acceptance: "验收标准", gates: "门禁与 CI", nonGoals: "非目标",
  } : {
    background: "Background", goal: "Goals", authority: "Design authority", implementation: "Implementation",
    steps: "Implementation steps", boundary: "Dependencies and boundary", verify: "Verification",
    acceptance: "Acceptance", gates: "Gates and CI", nonGoals: "Non-goals",
  };
  const d = details("zh");
  const de = details("en");
  const sections = (x) => `## ${x.background}\n\n<待补：为什么做>\n\n## ${x.goal}\n\n- <待补>\n\n## ${x.authority}\n\n- <补 plans/fullstack-design 章节链接>\n\n## ${x.implementation}\n\n- <待补>\n\n## ${x.steps}\n\n1. <待补>\n\n## ${x.boundary}\n\n- 依赖：${depends.join("、") || "无"}\n- 非目标：<待补>\n\n## ${x.verify}\n\n\`\`\`sh\n<验收命令>\n\`\`\`\n\n- <预期输出>\n\n## ${x.acceptance}\n\n- <待补>\n\n## ${x.gates}\n\n- <新增或命中的门禁>\n\n## ${x.nonGoals}\n\n- <待补>\n`;
  const zh = `# ${title}\n\n[English](${name}.en.md) | 中文\n\n${fence}\n\n${sections(d)}`;
  const en = `# ${titleEn}\n\nEnglish | [中文](${name}.md)\n\n${fence}\n\n${sections(de)}`;
  const paths = pairPaths(base);
  await mkdir(path.dirname(base), { recursive: true });
  await writeFile(paths.base, zh);
  await writeFile(paths.en, en);
  await writeFile(
    paths.meta,
    renderPairRecord(paths, { baseHash: blobHash(zh), enHash: blobHash(en) }),
  );
  return paths;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const args = process.argv.slice(2).filter((a) => a !== "--");
  const read = (flag) => {
    const i = args.indexOf(flag);
    return i >= 0 ? args[i + 1] : undefined;
  };
  try {
    const paths = await createIssue({
      id: read("--id"),
      milestone: read("--milestone"),
      priority: read("--priority"),
      slug: read("--slug"),
      title: read("--title"),
      titleEn: read("--title-en"),
      scopes: read("--scope")?.split(",").map((s) => s.trim()).filter(Boolean),
      depends: read("--depends")?.split(",").map((s) => s.trim()).filter(Boolean) ?? [],
    });
    console.log(`flow:new-issue: 已生成 ${paths.base}（三件套）`);
    console.log("下一步：补背景/目标/验收（双侧），流转前 pnpm flow:sync 回填编号");
  } catch (error) {
    console.error(`flow:new-issue: ${error.message}`);
    process.exit(1);
  }
}
