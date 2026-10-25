// The documents the page actually serves, and the promise that they stay clean.
//
// Two different guarantees, because the fixtures are two different things:
//
// 1. The **live** document - `snapshot_2026-10-23_evening.json`, fetched from the
//    snapshot bucket for this audit - is the shape the writer produces today, so it
//    has to be clean as written: the sanitizer must change nothing in it. A writer
//    that starts putting an account id or a stack trace in the document fails here,
//    by path, rather than being silently masked forever.
// 2. The other fixtures are historical states, and one of them is the record of a
//    night the run died on an exception: `snapshot_2026-10-14_error.json` carries
//    `KeyError: "['dividend', 'split_factor'] not in index"` in `run_status.detail`,
//    exactly as the published document did on 2026-10-14. That is what the Worker's
//    sanitizer is for, so these are asserted the other way round: after sanitizing,
//    nothing is left for the scan to find, and a second pass changes nothing.

import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { sanitizeSnapshot, scanForSensitive } from "./sanitize";

const FIXTURES = join(process.cwd(), "fixtures");
const DOCUMENTS = readdirSync(FIXTURES)
  .filter((name) => name.startsWith("snapshot_") && name.endsWith(".json"))
  .sort();
const LIVE = "snapshot_2026-10-23_evening.json";

function load(name: string): unknown {
  return JSON.parse(readFileSync(join(FIXTURES, name), "utf8"));
}

const findings = (document: unknown): string[] =>
  scanForSensitive(document).map(
    (finding) => `${finding.path} (${finding.kind})`,
  );

describe("the live document from the snapshot bucket", () => {
  const live = load(LIVE) as Record<string, any>;

  it("is the 2026-10-23 evening, the first monthly rebalance", () => {
    expect(live.target_close).toBe("2026-10-23T00:00:00");
    expect(live.generated_at).toBe("2026-10-23T22:52:54.807373Z");
    expect(live.run_status.cadence.day).toBe("rebalance");
    expect(live.run_status.cadence.k).toBe(21);
    expect(live.run_status.status).toBe("ok");
  });

  it("has nothing in it that may not be published, as the writer wrote it", () => {
    expect(
      findings(live),
      "a field the sanitizer would have to touch is a field the writer should not write",
    ).toEqual([]);
  });

  it("is served unchanged, because there was nothing to change", () => {
    expect(sanitizeSnapshot(live)).toEqual(live);
  });
});

describe("every snapshot the page can be served", () => {
  it("has documents to check, and they include the live one", () => {
    expect(DOCUMENTS.length).toBeGreaterThan(10);
    expect(DOCUMENTS).toContain(LIVE);
  });

  it.each(DOCUMENTS)(
    "%s sanitizes to a document with nothing left to find",
    (name) => {
      expect(findings(sanitizeSnapshot(load(name)))).toEqual([]);
    },
  );

  it.each(DOCUMENTS)("%s is unchanged by a second pass", (name) => {
    const once = sanitizeSnapshot(load(name));
    expect(sanitizeSnapshot(once)).toEqual(once);
  });

  it.each(DOCUMENTS)(
    "%s keeps its shape, and only its audited places change",
    (name) => {
      const document = load(name) as Record<string, any>;
      const clean = sanitizeSnapshot(document) as Record<string, any>;
      // The sanitizer removes fields and masks values; it never removes the structure
      // the page renders.
      expect(Object.keys(clean).sort()).toEqual(Object.keys(document).sort());
      // And whatever it did touch is one of the two places the audit named: the store
      // identifier and the run's own detail. A change anywhere else is a finding.
      const touched = Object.keys(document).filter(
        (key) => JSON.stringify(clean[key]) !== JSON.stringify(document[key]),
      );
      expect(
        touched.every((key) => key === "store" || key === "run_status"),
      ).toBe(true);
    },
  );
});

describe("the error the page used to publish", () => {
  it("was a real exception message in a real document, and is blanked now", () => {
    const document = load("snapshot_2026-10-14_error.json") as Record<
      string,
      any
    >;
    expect(document.run_status.detail).toContain("KeyError");
    const clean = sanitizeSnapshot(document) as Record<string, any>;
    expect(clean.run_status.detail).toBe("");
    // The rest of the document is what the page explains the state with, and it stays.
    expect(clean.run_status.status).toBe(document.run_status.status);
    expect(clean.book.n_kept).toBe(document.book.n_kept);
  });
});
