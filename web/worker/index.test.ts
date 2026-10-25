import { describe, expect, it } from "vitest";

import { handle, SNAPSHOT_PATH, verifyAccess, type Env } from "./index";

const PAYLOAD = { schema_version: 1, target_close: "2026-09-21" };
const TOKEN = {
  "Cf-Access-Jwt-Assertion": "a-token-the-injected-verifier-decides-on",
};

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
    const env = envWith(PAYLOAD, {
      ACCESS_TEAM_DOMAIN: undefined,
      ACCESS_AUD: undefined,
    });
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

  it("serves the snapshot, sanitized, with a five minute cache when Access allowed it", async () => {
    const response = await handle(
      request(SNAPSHOT_PATH, TOKEN),
      envWith(PAYLOAD),
      {
        verify: async () => true,
      },
    );
    expect(response.status).toBe(200);
    expect(response.headers.get("cache-control")).toBe("public, max-age=300");
    expect(await response.json()).toEqual(PAYLOAD);
  });

  it("never caches a refusal, whatever the reason", async () => {
    const forbidden = await handle(request(SNAPSHOT_PATH), envWith(PAYLOAD), {
      verify: async () => false,
    });
    expect(forbidden.headers.get("cache-control")).toBe("no-store");
    const missing = await handle(request(SNAPSHOT_PATH, TOKEN), envWith(null), {
      verify: async () => true,
    });
    expect(missing.headers.get("cache-control")).toBe("no-store");
  });

  it("serves the page for every other path", async () => {
    const response = await handle(request("/"), envWith(PAYLOAD));
    expect(response.status).toBe(200);
    expect(await response.text()).toBe("the page");
  });
});

describe("what the route does with a document it should not publish", () => {
  const DIRTY = {
    schema_version: 1,
    store: "postgres/efb, writes went to db.abcdefgh.supabase.co",
    run_status: {
      status: "error",
      detail: "KeyError: the frame had no such column",
    },
    positions: {
      note: "read from https://paper-api.alpaca.markets on /Users/operator/efb",
    },
    account_id: "PA1ABCDEF2345",
  };

  it("strips it before the body leaves the Worker", async () => {
    const response = await handle(
      request(SNAPSHOT_PATH, TOKEN),
      envWith(DIRTY),
      {
        verify: async () => true,
      },
    );
    expect(response.status).toBe(200);
    const served = (await response.json()) as Record<string, any>;
    expect(JSON.stringify(served)).not.toContain("supabase");
    expect(JSON.stringify(served)).not.toContain("PA1ABCDEF2345");
    expect(JSON.stringify(served)).not.toContain("KeyError");
    expect(JSON.stringify(served)).not.toContain("/Users/operator");
    expect(served.account_id).toBeUndefined();
    expect(served.run_status.detail).toBe("");
    expect(served.store).toBe(null);
  });

  it("answers 502 rather than republishing a body it cannot parse", async () => {
    const env = envWith(PAYLOAD, {
      SNAPSHOTS: {
        get: async () => ({
          text: async () =>
            "not json at all, and it names a host: db.abcdefgh.supabase.co",
        }),
      },
    });
    const response = await handle(request(SNAPSHOT_PATH, TOKEN), env, {
      verify: async () => true,
    });
    expect(response.status).toBe(502);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(await response.text()).not.toContain("supabase");
  });
});

describe("the routes that are not the snapshot", () => {
  it("refuses a method that is not a read", async () => {
    for (const method of ["POST", "PUT", "DELETE", "PATCH"]) {
      const response = await handle(
        new Request(`https://book.example.com${SNAPSHOT_PATH}`, {
          method,
          headers: TOKEN,
        }),
        envWith(PAYLOAD),
        { verify: async () => true },
      );
      expect(response.status).toBe(405);
      expect(response.headers.get("allow")).toBe("GET, HEAD");
      expect(response.headers.get("cache-control")).toBe("no-store");
    }
  });

  it("answers a HEAD with the headers and no body", async () => {
    const response = await handle(
      new Request(`https://book.example.com${SNAPSHOT_PATH}`, {
        method: "HEAD",
        headers: TOKEN,
      }),
      envWith(PAYLOAD),
      { verify: async () => true },
    );
    expect(response.status).toBe(200);
    expect(response.headers.get("cache-control")).toBe("public, max-age=300");
    expect(await response.text()).toBe("");
  });

  it("answers 404 under the API namespace instead of the page", async () => {
    for (const path of ["/api", "/api/other", "/api/snapshot/2026-10-23"]) {
      const response = await handle(request(path), envWith(PAYLOAD));
      expect(response.status, path).toBe(404);
      expect(await response.json()).toEqual({ error: "not found" });
    }
  });
});
