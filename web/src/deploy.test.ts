// The deploy cannot ship a stale page.
//
// `wrangler deploy` uploads `./dist` as it finds it and bundles only the Worker's own
// TypeScript, so a deploy run without a build puts the new Worker beside the old page
// and nothing fails. That happened on 2026-10-29: the anchored panels were merged,
// deployed, and the live page went on rendering the nightly ones because the bundle was
// three days old. Two checks, because there are two ways to be wrong: the config has no
// build step, or the npm script does not build.

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const WEB = join(dirname(fileURLToPath(import.meta.url)), "..");

/** `wrangler.jsonc` with its `//` comments removed, since JSON has none. */
function config(): Record<string, unknown> {
  const text = readFileSync(join(WEB, "wrangler.jsonc"), "utf8");
  const bare = text
    .split("\n")
    .map((line) => line.replace(/(^|\s)\/\/.*$/, ""))
    .join("\n");
  return JSON.parse(bare) as Record<string, unknown>;
}

describe("the deploy builds the page first", () => {
  it("declares a build command in the Worker config", () => {
    const build = config().build as { command?: string } | undefined;
    expect(build?.command).toBeTruthy();
    // The page is Vite's; a build command that does not run it would leave `dist`
    // exactly as stale as no build at all.
    expect(build?.command).toContain("vite build");
  });

  it("still builds in the npm script, so both doors are covered", () => {
    const scripts = JSON.parse(readFileSync(join(WEB, "package.json"), "utf8")).scripts as Record<
      string,
      string
    >;
    expect(scripts.deploy).toContain("vite build");
    expect(scripts.deploy).toContain("wrangler deploy");
    expect(scripts.deploy.indexOf("vite build")).toBeLessThan(scripts.deploy.indexOf("wrangler"));
  });

  it("serves the directory the build writes", () => {
    const assets = config().assets as { directory?: string } | undefined;
    expect(assets?.directory).toBe("./dist");
  });
});
