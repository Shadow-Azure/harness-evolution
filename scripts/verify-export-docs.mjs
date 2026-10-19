#!/usr/bin/env node
// Gate: 注释即契约——导出面必须带文档注释（蓝本 verify-export-jsdoc 的裁剪移植）。
// 扫描面：apps/*/src/**/*.ts、packages/*/src/**/*.ts。顶层导出的声明须有 JSDoc；
// 导出函数每个形参须有 @param，非 void 返回须有 @returns（推断类型也须标注——
// 契约不靠猜）。门禁只钉"有"，写什么（契约语义：何时触发/边界/失败处置）归评审。

import { readdir, readFile } from "node:fs/promises";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import ts from "typescript";

const SRC_ROOTS = [path.resolve("apps"), path.resolve("packages")];

async function collectTs(dir, out = []) {
  if (!existsSync(dir)) return out;
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) await collectTs(full, out);
    else if (entry.name.endsWith(".ts") || entry.name.endsWith(".tsx")) out.push(full);
  }
  return out;
}

/** 语句的 JSDoc 块（VariableStatement 兜底取声明上的注释）。 */
function jsDocOf(stmt) {
  const docs = ts.getJSDocCommentsAndTags(stmt).filter(ts.isJSDoc);
  if (docs.length || !ts.isVariableStatement(stmt)) return docs;
  return stmt.declarationList.declarations.flatMap((d) =>
    ts.getJSDocCommentsAndTags(d).filter(ts.isJSDoc),
  );
}

function symbolName(stmt) {
  if (ts.isVariableStatement(stmt))
    return stmt.declarationList.declarations[0]?.name.getText();
  return stmt.name?.text;
}

/** 导出函数的 @param / @returns 契约。 */
function checkFunction(rel, fn, docs, errors) {
  const tags = docs.flatMap((doc) => doc.tags ?? []);
  for (const param of fn.parameters) {
    const name = param.name.getText();
    if (!tags.some((t) => ts.isJSDocParameterTag(t) && t.name.getText() === name))
      errors.push(`${rel}: 函数 ${fn.name?.text} 的形参 ${name} 缺 @param`);
  }
  const ret = fn.type?.getText() ?? "推断类型";
  const voidLike = ret === "void" || ret === "Promise<void>" || ret === "never";
  if (!voidLike && !tags.some(ts.isJSDocReturnTag))
    errors.push(`${rel}: 函数 ${fn.name?.text} 返回 ${ret}，缺 @returns`);
}

export default async function verifyExportDocs() {
  const errors = [];

  for (const root of SRC_ROOTS) {
    for (const file of await collectTs(path.join(root, ""))) {
      if (!file.includes(`${path.sep}src${path.sep}`) || file.endsWith(".d.ts")) continue;
      const rel = path.relative("", file);
      const sf = ts.createSourceFile(file, await readFile(file, "utf8"), ts.ScriptTarget.Latest, true);
      for (const stmt of sf.statements) {
        if ((ts.getCombinedModifierFlags(stmt) & ts.ModifierFlags.Export) === 0) continue;
        const docs = jsDocOf(stmt);
        if (docs.length === 0) {
          errors.push(
            `${rel}: 导出 ${symbolName(stmt) ?? "声明"} 缺 JSDoc（写契约语义：何时触发/边界/失败处置）`,
          );
          continue;
        }
        if (ts.isFunctionDeclaration(stmt)) checkFunction(rel, stmt, docs, errors);
      }
    }
  }

  return { ok: errors.length === 0, errors };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const result = await verifyExportDocs();
  if (!result.ok) {
    console.error(`verify-export-docs: FAIL\n  ${result.errors.join("\n  ")}`);
    process.exit(1);
  }
  console.log("verify-export-docs: ok");
}
