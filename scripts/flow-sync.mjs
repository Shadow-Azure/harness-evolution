#!/usr/bin/env node
// 开发工具：把 .agents/flow/ 流程树写到 GitHub 的唯一入口。对 github.number
// 为 null 的 milestone / issue 建远端对象（milestone 先行，issue 按 title
// 归属），回填两侧围栏的 number/url（配对门禁要求围栏两侧逐字节一致，两侧
// 同样替换）并重录配对记录；随后把已有编号对象的状态映射同步到 GitHub
// （done ↔ closed，其余 ↔ open），并同步详细中文正文。显式
// --retire-missing 只关闭不在本地树的开放远端对象，从不物理删除。需要 gh 已登录；CI 在线
// lane（verify-flow-online）只校验，写操作全部走这里。

import { readFile, writeFile } from "node:fs/promises";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { blobHash, pairPaths, renderPairRecord } from "./translation-pairing-lib.mjs";
import { loadFlowTree } from "./flow-lib.mjs";

/**
 * 同步计划：哪些 milestone / issue 需要建远端对象。
 * @returns {{milestones: Array, issues: Array}}
 */
export function planSync(tree) {
  return {
    milestones: tree.milestones.filter((m) => m.data.github?.number === null),
    issues: tree.issues.filter((i) => i.data.github?.number === null),
  };
}

/** 把围栏内 github 段的 number/url 从 null 回填为实值（字符串变换，两侧共用）。 */
export function applyGithubRef(content, number, url) {
  const next = content
    .replace("  number: null", `  number: ${number}`)
    .replace("  url: null", `  url: ${url}`)
    // bootstrap 只服务于编号回填前的自举；回填后同一事务移除，避免残留豁免。
    .replace(/^bootstrap: true\n/m, "");
  if (next === content)
    throw new Error("回填失败：未找到 github 段的 null 占位（编号已回填过？）");
  return next;
}

/** 回填一个文件的两侧围栏并重录配对记录。 */
async function backfill(file, number, url) {
  const paths = pairPaths(file);
  for (const side of [paths.base, paths.en]) {
    const content = await readFile(side, "utf8");
    await writeFile(side, applyGithubRef(content, number, url));
  }
  const baseContent = await readFile(paths.base, "utf8");
  const enContent = await readFile(paths.en, "utf8");
  await writeFile(
    paths.meta,
    renderPairRecord(paths, { baseHash: blobHash(baseContent), enHash: blobHash(enContent) }),
  );
}

/**
 * 生成 GitHub issue 正文：保留完整中文实施契约，移除机读围栏并修正设计链接。
 * @param {string} content 本地 issue 中文 Markdown。
 * @param {string} repo owner/name 仓库名。
 * @returns {string} 可发布到 GitHub 的详细正文。
 */
export function renderIssueBody(content, repo) {
  return content
    .replace(/^\[English\]\([^\n]+\) \| 中文\n+/m, "")
    .replace(/```yaml flow\n[\s\S]*?```\n*/m, "")
    .replace(/\]\(\.\.\/\.\.\/\.\.\/plans\/fullstack-design\//g, `](https://github.com/${repo}/blob/main/plans/fullstack-design/`)
    .trim();
}

/**
 * 计算退休计划：只选择远端仍开放且已不在本地流程树中的对象。
 * @param {object} tree 当前本地流程树。
 * @param {{milestones: Array<{number: number, state: string}>, issues: Array<{number: number, state: string}>}} remote 远端对象。
 * @returns {{milestones: number[], issues: number[]}} 待关闭编号。
 */
export function planRetirements(tree, remote) {
  const localMilestones = new Set(tree.milestones.map((m) => m.data.github?.number));
  const localIssues = new Set(tree.issues.map((i) => i.data.github?.number));
  return {
    milestones: remote.milestones.filter((m) => m.state === "open" && !localMilestones.has(m.number)).map((m) => m.number),
    issues: remote.issues.filter((i) => i.state === "OPEN" && !localIssues.has(i.number)).map((i) => i.number),
  };
}

function gh(args) {
  return execFileSync("gh", args, { encoding: "utf8" }).trim();
}

/** issue 的中文标题 = base 侧 H1。 */
function titleOf(content) {
  const m = /^# (.+)$/m.exec(content);
  if (!m) throw new Error("缺 H1 标题");
  return m[1].trim();
}

/**
 * 执行同步计划：milestone 先行、issue 随后。milestone 的编号必须回填到内存树
 * 上——issue 归属校验读的是内存字段，只写文件的话首次同步一轮跑不完。创建与
 * 回填完成后，再对全部已有编号对象做状态映射同步；远端状态已一致时不发 PATCH。
 * @param {{milestones: Array, issues: Array}} tree 流程树
 * @param {{createMilestone: Function, createIssue: Function, backfill: Function,
 *   readMilestoneState: Function, updateMilestoneState: Function,
 *   readIssueState: Function, updateIssueState: Function}} io 远端与文件副作用
 * @returns {Promise<{milestones: number, issues: number, stateUpdates: number}>} 新建与状态更新数量
 */
export async function runSync(tree, io) {
  const plan = planSync(tree);
  for (const milestone of plan.milestones) {
    const { number, url } = await io.createMilestone(milestone);
    await io.backfill(milestone.file, number, url);
    milestone.data.github = { number, url };
    console.log(`flow:sync: milestone ${milestone.data.id} → #${number}`);
  }
  for (const issue of plan.issues) {
    const milestone = tree.milestones.find((m) => m.data.id === issue.data.milestone);
    if (!Number.isInteger(milestone?.data.github?.number))
      throw new Error(`${issue.file}: 所属 milestone ${issue.data.milestone} 尚未同步——重跑本命令`);
    const { number, url } = await io.createIssue(issue, milestone);
    await io.backfill(issue.file, number, url);
    issue.data.github = { number, url };
    console.log(`flow:sync: issue ${issue.name} → #${number}`);
  }
  let stateUpdates = 0;
  for (const milestone of tree.milestones) {
    const number = milestone.data.github?.number;
    if (!Number.isInteger(number)) continue;
    const desired = milestone.data.status === "done" ? "closed" : "open";
    if ((await io.readMilestoneState(milestone)) === desired) continue;
    await io.updateMilestoneState(milestone, desired);
    stateUpdates += 1;
    console.log(`flow:sync: milestone ${milestone.data.id} → ${desired}`);
  }
  for (const issue of tree.issues) {
    const number = issue.data.github?.number;
    if (!Number.isInteger(number)) continue;
    const desired = issue.data.status === "done" ? "CLOSED" : "OPEN";
    if ((await io.readIssueState(issue)) === desired) continue;
    await io.updateIssueState(issue, desired);
    stateUpdates += 1;
    console.log(`flow:sync: issue ${issue.name} → #${number} ${desired}`);
  }
  let bodyUpdates = 0;
  if (io.issueBody) {
    for (const issue of tree.issues) {
      const desired = io.issueBody(issue);
      if ((await io.readIssueBody(issue)) === desired) continue;
      await io.updateIssueBody(issue, desired);
      bodyUpdates += 1;
      console.log(`flow:sync: issue ${issue.data.id ?? issue.name} 正文已同步`);
    }
  }
  return { milestones: plan.milestones.length, issues: plan.issues.length, stateUpdates, bodyUpdates };
}

async function main() {
  const repoUrl = execFileSync("git", ["remote", "get-url", "origin"], { encoding: "utf8" }).trim();
  const repo = /github\.com(?::\d+)?[:/]([^/]+\/[^/]+?)(?:\.git)?$/.exec(repoUrl)?.[1];
  if (!repo) throw new Error(`无法从 origin 推导 GitHub 仓库：${repoUrl}`);
  const { tree, errors } = await loadFlowTree();
  if (errors.length > 0) {
    console.error(`flow:sync: 流程树有错误，先修到 verify:flow 绿\n  ${errors.join("\n  ")}`);
    process.exit(1);
  }
  const created = await runSync(tree, {
    createMilestone(milestone) {
      const out = gh(["api", `repos/${repo}/milestones`, "-f", `title=${milestone.data.title}`, "-f", "state=open"]);
      const { number } = JSON.parse(out);
      return { number, url: `https://github.com/${repo}/milestone/${number}` };
    },
    createIssue(issue, milestone) {
      const url = gh([
        "issue", "create", "--repo", repo,
        "--title", titleOf(readFileSync(issue.file, "utf8")),
        "--milestone", milestone.data.title,
        "--body", renderIssueBody(readFileSync(issue.file, "utf8"), repo),
      ]);
      const number = Number.parseInt(url.match(/\/issues\/(\d+)/)?.[1] ?? "", 10);
      if (!Number.isInteger(number)) throw new Error(`无法从 gh 输出解析 issue 编号：${url}`);
      return { number, url };
    },
    backfill,
    readMilestoneState(milestone) {
      return gh(["api", `repos/${repo}/milestones/${milestone.data.github.number}`]).state;
    },
    updateMilestoneState(milestone, state) {
      return gh([
        "api", "-X", "PATCH", `repos/${repo}/milestones/${milestone.data.github.number}`,
        "-f", `state=${state}`,
      ]);
    },
    readIssueState(issue) {
      return gh(["issue", "view", String(issue.data.github.number), "--repo", repo, "--json", "state"]).state;
    },
    updateIssueState(issue, state) {
      return gh([
        "api", "-X", "PATCH", `repos/${repo}/issues/${issue.data.github.number}`,
        "-f", `state=${state.toLowerCase()}`,
      ]);
    },
    issueBody: (issue) => renderIssueBody(readFileSync(issue.file, "utf8"), repo),
    readIssueBody(issue) {
      return gh(["issue", "view", String(issue.data.github.number), "--repo", repo, "--json", "body", "--jq", ".body"]);
    },
    updateIssueBody(issue, body) {
      return gh(["api", "-X", "PATCH", `repos/${repo}/issues/${issue.data.github.number}`, "-f", `body=${body}`]);
    },
  });
  if (process.argv.includes("--retire-missing")) {
    const remote = {
      milestones: JSON.parse(gh(["api", `repos/${repo}/milestones?state=open&per_page=100`])),
      issues: JSON.parse(gh(["issue", "list", "--repo", repo, "--state", "open", "--limit", "1000", "--json", "number,state"])),
    };
    const retire = planRetirements(tree, remote);
    for (const number of retire.issues) {
      gh(["api", "-X", "PATCH", `repos/${repo}/issues/${number}`, "-f", "state=closed"]);
      console.log(`flow:sync: retired issue #${number} → closed`);
    }
    for (const number of retire.milestones) {
      gh(["api", "-X", "PATCH", `repos/${repo}/milestones/${number}`, "-f", "state=closed"]);
      console.log(`flow:sync: retired milestone #${number} → closed`);
    }
  }
  console.log(
    `flow:sync: 完成（新建 milestone ${created.milestones}、issue ${created.issues}；状态更新 ${created.stateUpdates}；正文更新 ${created.bodyUpdates}）`,
  );
}

if (import.meta.url === `file://${process.argv[1]}`) await main();
