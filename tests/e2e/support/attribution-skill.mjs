import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";

/**
 * Upload a synthetic attribution Skill to the workspace resource library.
 * @param {string} python Project Python executable.
 * @param {string} url Workspace package endpoint.
 * @param {string} token Administrator access token.
 * @param {string} name Skill key.
 * @returns {Promise<object>} Uploaded package metadata.
 */
export async function uploadSkill(python, url, token, name) {
  const archive = spawnSync(python, ["-c", [
    "import io, sys, zipfile",
    "buf = io.BytesIO()",
    "with zipfile.ZipFile(buf, 'w') as z:",
    "    z.writestr('SKILL.md', sys.stdin.buffer.read())",
    "sys.stdout.buffer.write(buf.getvalue())",
  ].join("\n")], { input: `---\nname: ${name}\n---\nReview each case.` });
  assert.equal(archive.status, 0, archive.stderr.toString());
  const form = new FormData();
  form.set("file", new Blob([archive.stdout]), `${name}.zip`);
  const response = await fetch(url, {
    method: "POST", headers: { authorization: `Bearer ${token}` }, body: form,
  });
  assert.equal(response.status, 201, await response.clone().text());
  return response.json();
}
