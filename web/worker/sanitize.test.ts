import { describe, expect, it } from "vitest";

import { REDACTED, sanitizeSnapshot, scanForSensitive } from "./sanitize";

/** A document with one of everything that must never be published. */
const PLANTED = {
  schema_version: 1,
  store: "postgresql://efb:secret@db.abcdefgh.supabase.co:5432/postgres",
  account_id: "PA1ABCDEF2345",
  generated_at: "2026-10-23T22:52:54Z",
  run_status: {
    status: "error",
    detail: "KeyError: \"['dividend', 'split_factor'] not in index\"",
    worst_input: "prices",
    contact: "the owner at amank.iitg@gmail.com",
    order_id: "0f8fad5b-d9cb-469f-a165-70867728950e",
  },
  positions: {
    source: "alpaca paper account",
    note: "read at https://paper-api.alpaca.markets/v2/positions from 0f8fad5b-d9cb-469f-a165-70867728950e and cached in /Users/amankesarwani/PycharmProjects/equity-factor-book/live/state",
    client_order_id: "efb-2026-10-23-KO-B-74dec662b6e0",
  },
  book: {
    n_kept: 196,
    names: [
      {
        ticker: "KO",
        weight: 0.0155,
        note: "bucket efb-snapshots at abc123.r2.cloudflarestorage.com, account PA1ABCDEF2345",
      },
    ],
  },
  attribution: {
    notes: [
      {
        date: "2026-10-20",
        text: "rebuild triggered by AKIAIOSFODNN7EXAMPLE from amankesar.cloudflareaccess.com",
      },
      {
        date: "2026-10-21",
        text: "the hedge removed 7.9 points of volatility",
      },
    ],
  },
  note: "the session carried eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signaturepart",
  feed: {
    api_key: "sk-live-abcdefghijklmnop",
    token: "a-token-that-is-dropped-by-its-key",
  },
};

describe("what the sanitizer removes", () => {
  it("finds every planted field before it is cleaned", () => {
    const kinds = new Set(
      scanForSensitive(PLANTED).map((finding) => finding.kind),
    );
    for (const kind of [
      "dropped-key",
      "email",
      "url",
      "host",
      "path",
      "uuid",
      "account",
      "store",
      "error-text",
      "jwt",
    ]) {
      expect(kinds, `the scan should see a ${kind}`).toContain(kind);
    }
  });

  it("leaves nothing behind that the scan can find", () => {
    expect(scanForSensitive(sanitizeSnapshot(PLANTED))).toEqual([]);
  });

  it("drops a key that names an identity, an order or a credential, at any depth", () => {
    const clean = sanitizeSnapshot(PLANTED) as Record<string, any>;
    expect(clean).not.toHaveProperty("account_id");
    expect(clean.run_status).not.toHaveProperty("order_id");
    expect(clean.positions).not.toHaveProperty("client_order_id");
    expect(clean.feed).not.toHaveProperty("api_key");
    expect(clean.feed).not.toHaveProperty("token");
    expect(clean.note).not.toContain("eyJhbGciOiJSUzI1NiJ9");
  });

  it("redacts a host, a url, a path, an email and an account id inside free text", () => {
    const clean = sanitizeSnapshot(PLANTED) as Record<string, any>;
    expect(clean.positions.note).toContain(REDACTED);
    expect(clean.positions.note).not.toContain("alpaca.markets");
    expect(clean.positions.note).not.toContain("/Users/");
    expect(clean.positions.note).not.toContain("0f8fad5b");
    expect(clean.run_status.contact).toContain(REDACTED);
    expect(clean.run_status.contact).not.toContain("@");
    expect(clean.book.names[0].note).not.toContain("r2.cloudflarestorage.com");
    expect(clean.attribution.notes[0].text).not.toContain("AKIA");
    expect(clean.attribution.notes[0].text).not.toContain(
      "cloudflareaccess.com",
    );
  });

  it("blanks an error text rather than publishing the exception", () => {
    const clean = sanitizeSnapshot(PLANTED) as Record<string, any>;
    expect(clean.run_status.detail).toBe("");
  });

  it("keeps the writer's own prose, which is the page's explanation", () => {
    const clean = sanitizeSnapshot(PLANTED) as Record<string, any>;
    expect(clean.attribution.notes[1].text).toBe(
      "the hedge removed 7.9 points of volatility",
    );
    expect(clean.run_status.worst_input).toBe("prices");
    expect(clean.book.n_kept).toBe(196);
    expect(clean.generated_at).toBe("2026-10-23T22:52:54Z");
  });

  it("keeps a store identifier that says where writes went and nothing more", () => {
    const clean = sanitizeSnapshot({ store: "postgres/efb" }) as Record<
      string,
      unknown
    >;
    expect(clean.store).toBe("postgres/efb");
    expect(
      (
        sanitizeSnapshot({ store: "offline: no connection string" }) as Record<
          string,
          unknown
        >
      ).store,
    ).toBe(null);
  });

  it("does not mutate the document it was given", () => {
    const copy = structuredClone(PLANTED);
    sanitizeSnapshot(PLANTED);
    expect(PLANTED).toEqual(copy);
  });
});
