import assert from "node:assert/strict";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(
    new Request("http://localhost/", { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("server-renders the frozen matchup brief", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /Valkyries–Toronto Matchup Intelligence/);
  assert.match(html, /Find more half-court offense/);
  assert.match(html, /Protect the defensive identity/);
  assert.match(html, /Which feasible Golden State lineup adjustments/);
  assert.match(html, /Three bounded lineup experiments/);
  assert.match(html, /4bad26019ec2f6aab85f27a9/);
  assert.doesNotMatch(html, /codex-preview/);
});
