// The Worker that serves the live book monitor.
//
// One read route and one static page. `GET /api/snapshot` reads `latest.json`
// through an R2 binding, so no credential exists in the Worker and the bucket
// stays private; every other path is the built page. Access protects the
// hostname, and the Worker checks the Access assertion itself rather than
// trusting the edge alone: an Access policy is a routing decision and this is a
// data decision, and the page shows positions.
//
// **Every snapshot the Worker answers with is sanitized first** (`./sanitize`), so
// the document can be served to anyone without a second review: the fields that
// name an account, an order, a credential, an email or a host are removed or
// masked at this boundary, whichever run wrote the document. That is a property of
// the route rather than of the Access policy in front of it, which is what makes
// the page publishable at all. The only cacheable response is that sanitized
// snapshot; a refusal is never cached.
//
// The JWT check is injectable so the tests can drive both outcomes without
// minting a real token, and `verifyAccess` is exported so the test that matters
// most - a request with no token, and a request with a token nothing signed - can
// assert the real implementation rather than a stub.

import { createRemoteJWKSet, jwtVerify } from "jose";

import { sanitizeSnapshot } from "./sanitize";

export interface Env {
  SNAPSHOTS: {
    get: (key: string) => Promise<{ text: () => Promise<string> } | null>;
  };
  ASSETS: { fetch: (request: Request) => Promise<Response> };
  ACCESS_TEAM_DOMAIN?: string;
  ACCESS_AUD?: string;
}

export interface Deps {
  verify?: (token: string | null, env: Env) => Promise<boolean>;
}

export const SNAPSHOT_KEY = "latest.json";
export const SNAPSHOT_PATH = "/api/snapshot";

const NO_STORE = "no-store";
/**
 * The sanitized snapshot is the one response that may be cached: it holds nothing
 * personal, and five minutes is inside the page's own staleness window for a book
 * that changes twice a day.
 */
const SNAPSHOT_CACHE = "public, max-age=300";
/** The API namespace, so an unknown read is a 404 rather than the page's HTML. */
const API_ROOT = "/api";

function json(
  body: unknown,
  status: number,
  cacheControl: string = NO_STORE,
): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json",
      "cache-control": cacheControl,
    },
  });
}

/** Whether the request carries a valid Access assertion for this application. */
export async function verifyAccess(
  token: string | null,
  env: Env,
  deps: Deps = {},
): Promise<boolean> {
  if (!token) return false;
  if (deps.verify) return deps.verify(token, env);
  if (!env.ACCESS_TEAM_DOMAIN || !env.ACCESS_AUD) return false;
  try {
    const issuer = `https://${env.ACCESS_TEAM_DOMAIN}`;
    const jwks = createRemoteJWKSet(new URL(`${issuer}/cdn-cgi/access/certs`));
    await jwtVerify(token, jwks, { issuer, audience: env.ACCESS_AUD });
    return true;
  } catch {
    // A token that cannot be verified is not a token: never a caught-and-sent.
    return false;
  }
}

/** The document as the route serves it, or null when the object is not JSON. */
export function servedSnapshot(raw: string): unknown | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    // A body the worker cannot read is not a body it republishes: echoing the text
    // would serve whatever the bucket happened to hold, unsanitized.
    return null;
  }
  return sanitizeSnapshot(parsed);
}

export async function handle(
  request: Request,
  env: Env,
  deps: Deps = {},
): Promise<Response> {
  const url = new URL(request.url);
  if (url.pathname !== SNAPSHOT_PATH) {
    // The page, and the only other thing this Worker serves. A read under the API
    // namespace that is not the snapshot is a 404 rather than the SPA fallback, so
    // no route can answer JSON by accident.
    return url.pathname === API_ROOT || url.pathname.startsWith(`${API_ROOT}/`)
      ? json({ error: "not found" }, 404)
      : env.ASSETS.fetch(request);
  }
  // One read, one method. A HEAD is the same read without a body, which a health
  // check uses; anything else is refused rather than treated as a read.
  const method = request.method.toUpperCase();
  if (method !== "GET" && method !== "HEAD") {
    const refused = json({ error: "method not allowed" }, 405);
    refused.headers.set("allow", "GET, HEAD");
    return refused;
  }
  if (
    !(await verifyAccess(
      request.headers.get("Cf-Access-Jwt-Assertion"),
      env,
      deps,
    ))
  ) {
    return json({ error: "forbidden" }, 403);
  }
  const object = await env.SNAPSHOTS.get(SNAPSHOT_KEY);
  if (object === null) {
    // A missing object is a state the page renders as a failure, not an error
    // the page cannot see: the run has not written a snapshot yet.
    return json({ missing: true }, 404);
  }
  const document = servedSnapshot(await object.text());
  if (document === null) {
    return json({ error: "snapshot unreadable" }, 502);
  }
  const body = JSON.stringify(document);
  return new Response(method === "HEAD" ? null : body, {
    status: 200,
    headers: {
      "content-type": "application/json",
      "cache-control": SNAPSHOT_CACHE,
      "content-length": String(body.length),
    },
  });
}

export default {
  fetch: (request: Request, env: Env) => handle(request, env),
};
