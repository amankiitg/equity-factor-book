// The page's own measuring stick: what the layout actually is, rather than what a
// screenshot looks like.
//
// Screenshots are for a person; they are not evidence a script can check, and this
// batch is judged on four numbers a reader of the page would feel rather than see:
// how tall the page is at each width, whether anything makes the phone scroll
// sideways, whether a table scrolls sideways on its own, and whether the answer to
// "is anything wrong today?" is inside the first screen. So this script builds
// nothing and looks at nothing: it serves an already-built `dist/` with one fixture
// behind the snapshot endpoint, opens it at each width, and prints those numbers.
//
// It lives under `web/scripts/` rather than the repository's `scripts/` on purpose:
// the batch's gate is that the diff touches only `web/`, `docs/` and `artifacts/`,
// and a measuring tool is part of the page's own suite.
//
// Usage:
//   node scripts/measure.mjs --dist dist --fixture fixtures/snapshot_2026-10-14_morning.json
//   node scripts/measure.mjs --dist dist --smoke fixtures/a.json fixtures/b.json
//
// Playwright is resolved from this package, from `PLAYWRIGHT_MODULE`, or from the
// newest `~/.npm/_npx/*/node_modules/playwright`, which is where `npx playwright`
// leaves it. Nothing here reaches the network.

import { createRequire } from "node:module";
import { createServer } from "node:http";
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { extname, join, resolve } from "node:path";
import { homedir } from "node:os";

const WIDTHS = [
  { name: "1440", width: 1440, height: 900 },
  { name: "390", width: 390, height: 844 },
];

/** The first screen at the phone width, in CSS pixels. */
const FIRST_SCREEN = 844;

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
};

function parseArgs(argv) {
  const args = {
    dist: "dist",
    fixture: null,
    smoke: [],
    port: 8799,
    out: null,
    shots: null,
    now: null,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const flag = argv[index];
    if (flag === "--dist") args.dist = argv[++index];
    else if (flag === "--fixture") args.fixture = argv[++index];
    else if (flag === "--smoke") {
      while (argv[index + 1] && !argv[index + 1].startsWith("--")) args.smoke.push(argv[++index]);
    } else if (flag === "--port") args.port = Number(argv[++index]);
    else if (flag === "--out") args.out = argv[++index];
    else if (flag === "--shots") args.shots = argv[++index];
    else if (flag === "--now") args.now = argv[++index];
  }
  return args;
}

/**
 * Where Playwright is: this package, the environment, or npx's own cache.
 *
 * Playwright is CommonJS, so it is loaded with `createRequire` rather than an
 * `import`: importing its `index.js` as ESM yields a namespace whose `chromium` is
 * undefined, and a measuring script that silently measures nothing is worse than one
 * that says it could not find its browser.
 */
async function loadPlaywright() {
  const require = createRequire(import.meta.url);
  const tried = [];
  const candidates = [
    "playwright",
    process.env.PLAYWRIGHT_MODULE,
  ].filter(Boolean);
  const cache = join(homedir(), ".npm", "_npx");
  if (existsSync(cache)) {
    for (const entry of readdirSync(cache)) {
      candidates.push(join(cache, entry, "node_modules", "playwright"));
    }
  }
  for (const candidate of candidates) {
    tried.push(candidate);
    try {
      const loaded = require(candidate);
      if (loaded?.chromium) return loaded;
    } catch {
      // the next candidate
    }
  }
  throw new Error(`playwright not found; tried ${tried.join(", ")}`);
}

/** A local server: the built page, and the fixture behind `/api/snapshot`. */
function serve(dist, fixture, port) {
  const body = readFileSync(fixture);
  const server = createServer((request, response) => {
    const url = new URL(request.url ?? "/", "http://localhost");
    if (url.pathname === "/api/snapshot") {
      response.writeHead(200, { "content-type": TYPES[".json"], "cache-control": "no-store" });
      response.end(body);
      return;
    }
    const path = url.pathname === "/" ? "/index.html" : url.pathname;
    try {
      const file = readFileSync(join(dist, path));
      response.writeHead(200, {
        "content-type": TYPES[extname(path)] ?? "application/octet-stream",
      });
      response.end(file);
    } catch {
      response.writeHead(404, { "content-type": "text/plain" });
      response.end("not found");
    }
  });
  return new Promise((ready) => server.listen(port, "127.0.0.1", () => ready(server)));
}

/**
 * What the page looks like, as numbers.
 *
 * The table list excludes anything inside the attribution section on purpose: a
 * table of nine columns of numbers cannot fit a phone, and the brief allows exactly
 * that one to scroll sideways inside its own box. Every other table is a finding if
 * it does.
 */
const PROBE = (firstScreen) => {
  const box = (selector) => {
    const element = document.querySelector(selector);
    if (!element) return null;
    const rect = element.getBoundingClientRect();
    return {
      top: Math.round(rect.top + window.scrollY),
      bottom: Math.round(rect.bottom + window.scrollY),
      height: Math.round(rect.height),
    };
  };
  const attribution = document.querySelector("[data-section='attribution']");
  const tables = Array.from(document.querySelectorAll("table"))
    .filter((table) => !attribution || !attribution.contains(table))
    .map((table) => {
      const container = table.parentElement?.clientWidth ?? window.innerWidth;
      return {
        name: table.getAttribute("aria-label") ?? (table.textContent ?? "").slice(0, 24),
        width: table.scrollWidth,
        container,
        overflows: table.scrollWidth > container + 1,
      };
    });
  const wide = Array.from(document.querySelectorAll("body *"))
    .map((element) => ({
      tag: element.tagName.toLowerCase(),
      right: Math.round(element.getBoundingClientRect().right),
    }))
    .filter((row) => row.right > document.documentElement.clientWidth + 1);
  const headline = box("[data-alert='reconciliation'] p");
  const text = document.body.textContent ?? "";
  return {
    viewport: { width: window.innerWidth, height: window.innerHeight },
    scrollHeight: document.body.scrollHeight,
    scrollWidth: document.body.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
    sideways: document.body.scrollWidth > document.documentElement.clientWidth,
    tables,
    overflowingTables: tables.filter((table) => table.overflows).map((table) => table.name),
    widestElements: wide.slice(0, 6),
    sections: Array.from(document.querySelectorAll("section[data-section]")).map((element) =>
      element.getAttribute("data-section"),
    ),
    headline,
    headlineInFirstScreen: headline === null ? null : headline.bottom <= firstScreen,
    suspects: ["NaN", "undefined", "-$0", "T00:00:00"].filter((needle) => text.includes(needle)),
    runPanel: {
      text: (document.querySelector("[data-alert='run']")?.textContent ?? "").slice(0, 240),
      tone: document.querySelector("[data-alert='run']")?.getAttribute("data-tone") ?? null,
    },
  };
};

async function measure({ chromium }, args, fixture, width, screenshot) {
  const server = await serve(args.dist, fixture, args.port);
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: width.width, height: width.height },
    deviceScaleFactor: 1,
  });
  const errors = [];
  const page = await context.newPage();
  // The clock the page reads: a fixture is a document from one morning, and a page
  // opened days later correctly calls it stale. Pinning the clock to the morning the
  // fixture was written for is what makes a before and an after comparable.
  if (args.now) {
    const fixed = new Date(args.now).getTime();
    await context.addInitScript(`(() => {
      const fixed = ${fixed};
      const Real = Date;
      function MockDate(...args) { return args.length === 0 ? new Real(fixed) : new Real(...args); }
      MockDate.prototype = Real.prototype;
      MockDate.now = () => fixed;
      MockDate.parse = Real.parse;
      MockDate.UTC = Real.UTC;
      window.Date = MockDate;
    })();`);
  }
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(String(error)));
  await page.goto(`http://127.0.0.1:${args.port}/`, { waitUntil: "networkidle" });
  await page.waitForTimeout(250);
  const probe = await page.evaluate(PROBE, FIRST_SCREEN);
  if (screenshot) {
    mkdirSync(screenshot.dir, { recursive: true });
    await page.screenshot({ path: join(screenshot.dir, screenshot.name), fullPage: true });
  }
  await context.close();
  await browser.close();
  server.close();
  return { ...probe, consoleErrors: errors, fixture: resolve(fixture) };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const { chromium } = await loadPlaywright();
  const fixtures = args.smoke.length > 0 ? args.smoke : [args.fixture];
  if (fixtures.some((fixture) => !fixture)) throw new Error("no fixture given");
  const report = {};
  for (const [index, fixture] of fixtures.entries()) {
    const name = resolve(fixture).split("/").pop();
    report[name] = {};
    for (const [widthIndex, width] of WIDTHS.entries()) {
      args.port = 8799 + index * 4 + widthIndex;
      const shot = args.shots
        ? { dir: resolve(args.shots), name: `${name.replace(/\.json$/, "")}-${width.name}.png` }
        : null;
      report[name][width.name] = await measure({ chromium }, args, resolve(fixture), width, shot);
    }
  }
  const text = JSON.stringify(report, null, 1);
  if (args.out) {
    writeFileSync(resolve(args.out), text);
  }
  console.log(text);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
