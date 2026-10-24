"""Regenerate the three README screenshots from the built page.

    .venv/bin/python scripts/readme_screenshots.py

The script builds `web/`, serves the built `dist/` with one snapshot document behind
`/api/snapshot`, and captures three PNGs into `docs/img/`:

    book.png          the book view at 1280 px: status strip, headline metrics, the
                      bridge, the hedge and exposures panels, trades by reason, the
                      sector split and the largest longs and shorts
    attribution.png   the attribution view at 1280 px: the four P&L terms, the cost
                      split, predicted volatility before and after the hedge, the
                      variance path, the factor table and realized against forecast
    book_phone.png    the top of the book at 390 px, which is the first two screens

It is the same harness the 390 px checks use (`web/scripts/measure.mjs`): the same
fixture behind the same endpoint, and the same pinned clock, because a snapshot
document is a document from one morning and a page opened days later is right to call
it stale. Playwright is resolved from the page's own package, from `PLAYWRIGHT_MODULE`,
or from the npx cache, exactly as `measure.mjs` resolves it; nothing here reaches the
network and nothing here writes to the store, the bucket or the broker.

The default snapshot is `web/fixtures/snapshot_2026-10-13_evening.json`, the most recent
real published document kept in the repository (generated 2026-10-13T22:53:47Z by the
evening run). `--snapshot` takes any other document; the clock defaults to seventeen
minutes after whichever one is given, which is what makes the page read "ok" rather than
"expired".

`--check` captures nothing and prints what would be captured, which is what a CI job
wants if the page's own measuring stick ever runs the layout.

Every saved image is checked against a 400 KB ceiling. A capture over it is quantized to
an adaptive 256-colour palette, which on these flat, text-heavy pages costs nothing
visible and typically halves the file.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "web" / "dist"
OUT = ROOT / "docs" / "img"
DEFAULT_SNAPSHOT = ROOT / "web" / "fixtures" / "snapshot_2026-10-13_evening.json"
SIZE_CEILING = 400 * 1024
VIEWPORT_WIDTH = 1280
PHONE_WIDTH = 390
PHONE_VIEWPORT_HEIGHT = 844

TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
}


class Harness(BaseHTTPRequestHandler):
    """`dist/`, and the snapshot document behind `/api/snapshot`."""

    snapshot_bytes = b""

    def do_GET(self) -> None:  # noqa: N802 - the base class names it
        path = self.path.split("?", 1)[0]
        if path == "/api/snapshot":
            self.send_response(200)
            self.send_header("content-type", TYPES[".json"])
            self.send_header("cache-control", "no-store")
            self.end_headers()
            self.wfile.write(self.snapshot_bytes)
            return
        target = DIST / ("index.html" if path == "/" else path.lstrip("/"))
        try:
            body = target.read_bytes()
        except OSError:
            self.send_response(404)
            self.send_header("content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"not found")
            return
        self.send_response(200)
        self.send_header(
            "content-type", TYPES.get(target.suffix, "application/octet-stream")
        )
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: object) -> None:
        """Silent: a screenshot run is not a request log."""


CAPTURE = r"""
// The capture half: one page, three crops. It prints the boxes it framed so a reader
// can see what an image holds rather than trusting a filename.
import { createRequire } from "node:module";
import { existsSync, mkdirSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";

const args = { port: 0, out: "docs/img", now: null };
for (let index = 2; index < process.argv.length; index += 1) {
  const flag = process.argv[index];
  if (flag === "--port") args.port = Number(process.argv[++index]);
  else if (flag === "--out") args.out = process.argv[++index];
  else if (flag === "--now") args.now = process.argv[++index];
}

/** Playwright, from the page's package, the environment, or npx's own cache. */
async function loadPlaywright() {
  const require = createRequire(import.meta.url);
  const candidates = ["playwright", process.env.PLAYWRIGHT_MODULE].filter(Boolean);
  const cache = join(homedir(), ".npm", "_npx");
  if (existsSync(cache)) {
    for (const entry of readdirSync(cache)) {
      candidates.push(join(cache, entry, "node_modules", "playwright"));
    }
  }
  for (const candidate of candidates) {
    try {
      const loaded = require(candidate);
      if (loaded?.chromium) return loaded;
    } catch {
      // the next candidate
    }
  }
  throw new Error(`playwright not found; tried ${candidates.join(", ")}`);
}

/** The clock the page reads: a fixture is a document from one morning. */
const fixClock = (iso) => {
  const fixed = new Date(iso).getTime();
  return `(() => {
    const fixed = ${fixed};
    const Real = Date;
    function MockDate(...a) {
      return a.length === 0 ? new Real(fixed) : new Real(...a);
    }
    MockDate.prototype = Real.prototype;
    MockDate.now = () => fixed;
    MockDate.parse = Real.parse;
    MockDate.UTC = Real.UTC;
    window.Date = MockDate;
  })();`;
};

const boxes = () => {
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
  return {
    pageHeight: document.documentElement.scrollHeight,
    columns: box("[data-columns]"),
    attribution: box('[data-section="attribution"]'),
    drawer: box('[data-section="drawer"]'),
  };
};

const base = `http://127.0.0.1:${args.port}/`;
const { chromium } = await loadPlaywright();
mkdirSync(args.out, { recursive: true });
const browser = await chromium.launch();
const report = {};

// The book at desktop width. The crop ends with the detail drawer's tab bar, so the
// frame says where the full table lives instead of implying it is absent.
{
  const context = await browser.newContext({
    viewport: { width: 1280, height: 1000 },
    deviceScaleFactor: 1,
  });
  await context.addInitScript(fixClock(args.now));
  const page = await context.newPage();
  await page.goto(base, { waitUntil: "networkidle" });
  await page.waitForTimeout(400);
  const first = await page.evaluate(boxes);
  const height = Math.min(first.pageHeight, first.drawer.bottom + 12);
  await page.setViewportSize({ width: 1280, height });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(150);
  await page.screenshot({ path: join(args.out, "book.png") });
  report.book = { width: 1280, height, columns: first.columns, drawer: first.drawer };

  // The attribution tab, framed on its own section: the four terms, the cost split,
  // the two risk charts and the realized-against-forecast panel, each with its legend
  // and its notes.
  await page.click('[data-view="attribution"]');
  await page.waitForTimeout(500);
  const second = await page.evaluate(boxes);
  const section = second.attribution;
  await page.setViewportSize({ width: 1280, height: section.height + 8 });
  await page.evaluate((top) => window.scrollTo(0, top - 4), section.top);
  await page.waitForTimeout(200);
  await page.screenshot({ path: join(args.out, "attribution.png") });
  report.attribution = { width: 1280, top: section.top, height: section.height };
  await context.close();
}

// One phone view: the first two screens at 390 px, twice the pixel density.
{
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
  });
  await context.addInitScript(fixClock(args.now));
  const page = await context.newPage();
  await page.goto(base, { waitUntil: "networkidle" });
  await page.waitForTimeout(400);
  const measured = await page.evaluate(boxes);
  const height = Math.min(measured.pageHeight, measured.columns.top + 8);
  await page.setViewportSize({ width: 390, height });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(150);
  await page.screenshot({ path: join(args.out, "book_phone.png") });
  report.phone = { width: 390, height, pageHeight: measured.pageHeight };
  await context.close();
}

await browser.close();
console.log(JSON.stringify(report));
"""


STAMP = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})")


# The document's own write times: `generated_at`, and any `*_at` or `*_as_of` stamp the
# writer put on a block. Deliberately not every date it mentions - `expected_next_by` is
# a deadline twenty-four hours out, and a clock set to it is a clock set past the
# document's staleness window.
WRITE_KEY = re.compile(r"(?:^generated_at$|^as_of$|^close$|_at$|_as_of$)")


def _timestamps(node: object, key: str = "") -> list[datetime]:
    """Every moment at which the document says something was written."""
    found: list[datetime] = []
    if isinstance(node, dict):
        for name, value in node.items():
            if name == "expected_next_by":
                continue
            found.extend(_timestamps(value, name))
    elif isinstance(node, list):
        for value in node:
            found.extend(_timestamps(value, key))
    elif isinstance(node, str) and WRITE_KEY.search(key):
        match = STAMP.match(node)
        if match:
            try:
                found.append(datetime.fromisoformat(match.group(1)).replace(tzinfo=UTC))
            except ValueError:
                pass
    return found


def build(dist: Path) -> None:
    if not (ROOT / "web" / "node_modules").is_dir():
        raise SystemExit("web/node_modules is missing: run `npm install` in web/ first")
    print("building web/ ...", flush=True)
    subprocess.run(["npm", "run", "build"], cwd=ROOT / "web", check=True)


def serve(snapshot: Path):
    Harness.snapshot_bytes = snapshot.read_bytes()
    server = ThreadingHTTPServer(("127.0.0.1", 0), Harness)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def capture(now: str, out: Path, port: int) -> dict:
    with tempfile.TemporaryDirectory(prefix="efb-shots-") as scratch:
        program = Path(scratch) / "capture.mjs"
        program.write_text(CAPTURE)
        proc = subprocess.run(
            [
                "node",
                str(program),
                "--port",
                str(port),
                "--out",
                str(out),
                "--now",
                now,
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)
    return json.loads(proc.stdout)


def optimize(path: Path) -> tuple[int, int]:
    """Keep every image under the ceiling by quantizing an adaptive palette."""
    from PIL import Image

    before = path.stat().st_size
    if before <= SIZE_CEILING:
        return before, before
    image = Image.open(path).convert("RGB")
    image.quantize(
        colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE
    ).save(path, optimize=True)
    after = path.stat().st_size
    if after > SIZE_CEILING:
        raise SystemExit(
            f"{path.name} is {after / 1024:.0f} KB after quantizing: crop it"
        )
    return before, after


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument(
        "--now", default=None, help="the clock the page reads, ISO 8601"
    )
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument(
        "--check", action="store_true", help="print the plan, capture nothing"
    )
    args = parser.parse_args()

    snapshot = args.snapshot.resolve()
    if not snapshot.is_file():
        raise SystemExit(f"no snapshot at {snapshot}")
    document = json.loads(snapshot.read_text())
    generated = datetime.fromisoformat(
        str(document.get("generated_at") or "2026-01-01T00:00:00+00:00").replace(
            "Z", "+00:00"
        )
    )
    # A document can carry a later write than its own `generated_at` - the morning's
    # reconciliation is stamped into the evening's document - and a clock set before
    # that write makes the page read "just now" about a timestamp in its future. So
    # the clock is the newest moment the document mentions, plus ten minutes.
    newest = max(_timestamps(document), default=generated)
    now = args.now or (newest + timedelta(minutes=10)).astimezone(UTC).isoformat()
    out = args.out if args.out.is_absolute() else ROOT / args.out

    print(f"snapshot : {snapshot.relative_to(ROOT)}")
    print(f"generated: {generated.isoformat()}")
    print(f"clock    : {now}")
    print(f"output   : {out.relative_to(ROOT)}")
    if args.check:
        return 0

    if not args.skip_build:
        build(DIST)
    if not DIST.is_dir():
        raise SystemExit("no web/dist: build it or drop --skip-build")

    server = serve(snapshot)
    try:
        port = server.server_address[1]
        report = capture(now, out, port)
    finally:
        server.shutdown()
        server.server_close()

    print(json.dumps(report, indent=1))
    for name in ("book.png", "attribution.png", "book_phone.png"):
        path = out / name
        if not path.is_file():
            raise SystemExit(f"{name} was not written")
        before, after = optimize(path)
        note = "" if before == after else f" (quantized from {before / 1024:.0f} KB)"
        print(f"{name:20s} {after / 1024:7.1f} KB{note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
