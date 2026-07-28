import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
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

test("server-renders the PetDressed upload experience", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /<title>PetDressed/);
  assert.match(html, /Build your/);
  assert.match(html, /Access your wardrobe/);
  assert.match(html, /your photos never leave your account/);
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton/);
});

test("links a stylesheet into the document", async () => {
  const response = await render();
  const html = await response.text();
  assert.match(html, /<link[^>]+rel="stylesheet"[^>]+\.css"/);
});

test("compiles the brutalist theme with a reduced-motion escape hatch", async () => {
  // The design system carries the mobile layout, so verify the emitted CSS
  // rather than trusting that the build wired the stylesheet up correctly.
  const cssDir = new URL("../dist/client/assets/", import.meta.url);
  const sheets = (await readdir(cssDir)).filter((name) => name.endsWith(".css"));
  assert.ok(sheets.length > 0, "expected at least one compiled stylesheet");

  const css = (
    await Promise.all(sheets.map((name) => readFile(new URL(name, cssDir), "utf8")))
  ).join("\n");

  assert.match(css, /--acid:/, "brutalist palette should be present");
  assert.match(css, /prefers-reduced-motion/, "motion must be opt-out");

  // Mobile-first means layout scales up from the base rules, never down. The
  // minifier rewrites `min-width: 600px` to the range form `(width>=600px)`,
  // so accept either spelling.
  const scalesUp = /@media\s*\((?:min-width:|width\s*>=)/;
  const scalesDown = /@media\s*\((?:max-width:|width\s*<=)/;
  assert.match(css, scalesUp, "expected min-width breakpoints");
  assert.doesNotMatch(css, scalesDown, "max-width breakpoints are not mobile-first");
});
