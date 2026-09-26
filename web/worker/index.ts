// The Worker that serves the live book monitor.
//
// One read route and one static page. `GET /api/snapshot` reads `latest.json`
// through an R2 binding, so no credential exists in the Worker and the bucket
// stays private; every other path is the built page. Access protects the
// hostname, and the Worker checks the Access assertion itself rather than
// trusting the edge alone: an Access policy is a routing decision and this is a
// data decision, and the page shows positions.
//
// The JWT check is injectable so the tests can drive both outcomes without
// minting a real token, and `verifyAccess` is exported so the test that matters
// most - a request with no token, and a request with a token nothing signed - can
// assert the real implementation rather than a stub.

import { createRemoteJWKSet, jwtVerify } from "jose";

export interface Env {
  SNAPSHOTS: { get: (key: string) => Promise<{ text: () => Promise<string> } | null> };
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

function json(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", "cache-control": NO_STORE },
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

export async function handle(
  request: Request,
  env: Env,
  deps: Deps = {},
): Promise<Response> {
  const url = new URL(request.url);
  if (url.pathname !== SNAPSHOT_PATH) {
    return env.ASSETS.fetch(request);
  }
  if (!(await verifyAccess(request.headers.get("Cf-Access-Jwt-Assertion"), env, deps))) {
    return json({ error: "forbidden" }, 403);
  }
  const object = await env.SNAPSHOTS.get(SNAPSHOT_KEY);
  if (object === null) {
    // A missing object is a state the page renders as a failure, not an error
    // the page cannot see: the run has not written a snapshot yet.
    return json({ missing: true }, 404);
  }
  return new Response(await object.text(), {
    status: 200,
    headers: { "content-type": "application/json", "cache-control": NO_STORE },
  });
}

export default {
  fetch: (request: Request, env: Env) => handle(request, env),
};
