// The build check: the browser never queries Postgres, and never holds a key.
//
// The owner's rule is that the browser never reaches Supabase and never reaches
// R2: the Worker reads the snapshot through a binding and the bucket stays
// private. A page that quietly gained a database client, a connection string, an
// R2 key or a `VITE_` variable carrying a secret would undo that, and it would
// undo it invisibly, because such a build still works.
//
// So the check is on the artifacts: every file under `src/` always, and every
// file under `dist/` when a build has been made.

import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const HERE = dirname(fileURLToPath(import.meta.url));
const WEB = join(HERE, "..");

const FORBIDDEN = [
  "supabase",
  "postgres",
  "DB_URL",
  "r2.cloudflarestorage",
  // A Vite variable is compiled into the bundle, so any of these reaching the
  // page would be a credential in a browser.
  "VITE_",
  "EFB_SUPABASE",
  "EFB_R2_SECRET",
  "EFB_ALPACA",
  "EFB_RESEND",
];

function filesUnder(directory: string): string[] {
  if (!existsSync(directory)) return [];
  return readdirSync(directory).flatMap((entry: string) => {
    const path = join(directory, entry);
    if (statSync(path).isDirectory()) return filesUnder(path);
    return [path];
  });
}

describe("the page carries no data path of its own", () => {
  it.each(FORBIDDEN)("nothing under src/ mentions %s", (needle) => {
    const offenders = filesUnder(join(WEB, "src"))
      .filter((path) => !path.endsWith("bundle.test.ts"))
      .filter((path) => readFileSync(path, "utf8").toLowerCase().includes(needle.toLowerCase()))
      .map((path) => relative(WEB, path));
    expect(offenders).toEqual([]);
  });

  it("nothing under dist/ mentions a credential, when a build exists", () => {
    const built = filesUnder(join(WEB, "dist"));
    if (built.length === 0) {
      // A build must still be checked before deploying: this test is the check,
      // and `npm run deploy` builds first.
      expect(true).toBe(true);
      return;
    }
    for (const needle of FORBIDDEN) {
      const offenders = built
        .filter((path) => readFileSync(path, "utf8").toLowerCase().includes(needle.toLowerCase()))
        .map((path) => relative(WEB, path));
      expect(offenders, `dist/ mentions ${needle}`).toEqual([]);
    }
  });

  it("the Worker reads the snapshot through a binding, never over HTTP", () => {
    const worker = readFileSync(join(WEB, "worker", "index.ts"), "utf8");
    expect(worker).toContain("env.SNAPSHOTS.get");
    expect(worker).not.toContain("fetch(`https://");
    expect(worker).not.toContain("cloudflarestorage");
    expect(worker).not.toContain("SUPABASE");
  });

  it("preview URLs are off, so there is no hostname outside Access", () => {
    const wrangler = readFileSync(join(WEB, "wrangler.jsonc"), "utf8");
    expect(wrangler).toContain('"preview_urls": false');
  });
});
