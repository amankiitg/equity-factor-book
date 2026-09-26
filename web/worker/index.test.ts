import { describe, expect, it } from "vitest";

import { handle, SNAPSHOT_PATH, verifyAccess, type Env } from "./index";

const PAYLOAD = { schema_version: 1, target_close: "2026-09-21" };
const TOKEN = { "Cf-Access-Jwt-Assertion": "a-token-the-injected-verifier-decides-on" };

function envWith(object: unknown, overrides: Partial<Env> = {}): Env {
  return {
    SNAPSHOTS: {
      get: async (key: string) =>
        key === "latest.json" && object !== null
          ? { text: async () => JSON.stringify(object) }
          : null,
    },
    ASSETS: { fetch: async () => new Response("the page", { status: 200 }) },
    ACCESS_TEAM_DOMAIN: "efb.cloudflareaccess.com",
    ACCESS_AUD: "aud-for-the-tests",
    ...overrides,
  };
}

function request(path: string, headers: Record<string, string> = {}): Request {
  return new Request(`https://book.example.com${path}`, { headers });
}

describe("the snapshot route", () => {
  it("refuses a request with no Access assertion, without asking the verifier", async () => {
    let asked = false;
    const response = await handle(request(SNAPSHOT_PATH), envWith(PAYLOAD), {
      verify: async () => {
        asked = true;
        return true;
      },
    });
    expect(response.status).toBe(403);
    expect(await response.json()).toEqual({ error: "forbidden" });
    expect(asked).toBe(false);
  });

  it("refuses a token that nothing signed", async () => {
    // The real implementation, not the stub: a random string is not a JWT.
    const response = await handle(
      request(SNAPSHOT_PATH, { "Cf-Access-Jwt-Assertion": "not-a-jwt" }),
      envWith(PAYLOAD),
    );
    expect(response.status).toBe(403);
  });

  it("refuses when the team domain or the audience is unset", async () => {
    const env = envWith(PAYLOAD, { ACCESS_TEAM_DOMAIN: undefined, ACCESS_AUD: undefined });
    expect(await verifyAccess("a-token", env)).toBe(false);
  });

  it("answers 404 with missing when the object is absent", async () => {
    const env = envWith(null);
    const response = await handle(request(SNAPSHOT_PATH, TOKEN), env, {
      verify: async () => true,
    });
    expect(response.status).toBe(404);
    expect(await response.json()).toEqual({ missing: true });
    expect(response.headers.get("cache-control")).toBe("no-store");
  });

  it("serves the snapshot with no-store when Access allowed it", async () => {
    const response = await handle(request(SNAPSHOT_PATH, TOKEN), envWith(PAYLOAD), {
      verify: async () => true,
    });
    expect(response.status).toBe(200);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(await response.json()).toEqual(PAYLOAD);
  });

  it("serves the page for every other path", async () => {
    const response = await handle(request("/"), envWith(PAYLOAD));
    expect(response.status).toBe(200);
    expect(await response.text()).toBe("the page");
  });
});
