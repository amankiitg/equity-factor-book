// What may leave the Worker, and nothing else.
//
// The page was private behind Cloudflare Access, and this module is what makes it
// safe to serve to anyone: every snapshot the Worker answers with passes through
// `sanitizeSnapshot` first, so a field that should not be public is removed or
// masked once, at the boundary, rather than being absent by luck.
//
// Two rules, and both are cheap:
//
// 1. A key whose name says it holds an identity, an order, a credential, an email or
//    a location is dropped at any depth. The document the writer produces today
//    carries none of them, so this is the rule that keeps it that way when a future
//    writer adds a field.
// 2. A string that still contains a URL, a hostname, an absolute path, an email, a
//    broker account or order id, a JWT or a cloud key is redacted in place, because
//    those arrive inside free text: `run_status.detail` carries the message of
//    whatever exception stopped a run, and an exception message is written by a
//    library that has no opinion about being published.
//
// `scanForSensitive` is the same rules in read-only form. The tests assert that the
// real published document has nothing to find, and that the sanitized copy of a
// document with each pattern planted in it has nothing left.

export const REDACTED = "[redacted]";

/** A key whose value is never public, at any depth. */
const DROP_KEYS = new Set([
  "account_id",
  "account_number",
  "account_uuid",
  "order_id",
  "broker_order_id",
  "client_order_id",
  "email",
  "notify_email",
  "email_from",
  "email_to",
  "token",
  "api_key",
  "api_secret",
  "secret",
  "password",
  "dsn",
  "connection_string",
  "endpoint",
  "endpoint_url",
  "bucket",
  "file_path",
  "traceback",
  "stack",
  "raw_error",
]);

/** A string value that has to be redacted, by the thing it looks like. */
const REDACT: ReadonlyArray<readonly [string, RegExp]> = [
  ["email", /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g],
  ["url", /https?:\/\/[^\s"'<>)\]]+/g],
  [
    "host",
    /\b[a-z0-9-]+\.(?:supabase\.(?:co|com)|r2\.cloudflarestorage\.com|onrender\.com|workers\.dev|cloudflareaccess\.com|amazonaws\.com|r2\.dev)\b/gi,
  ],
  [
    "path",
    /(?:\/Users\/|\/home\/|\/tmp\/|\/var\/|\/srv\/|\/opt\/|[A-Za-z]:\\\\|\blive\/state\b)[^\s"',;)\]]*/g,
  ],
  [
    "uuid",
    /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi,
  ],
  [
    "client_order_id",
    /\befb-\d{4}-\d{2}-\d{2}-[A-Za-z.-]+-[BS]-[0-9a-f]{12}\b/g,
  ],
  ["account", /\bPA[A-Z0-9]{6,}\b/g],
  ["jwt", /\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b/g],
  ["cloud_key", /\b(?:AKIA|ASIA)[A-Z0-9]{16}\b/g],
];

/** A stack trace, which is not a message: the whole string goes. */
const TRACEBACK = /Traceback \(most recent call last\)|File "[^"]+", line \d+/;

/**
 * Error text, which is not an explanation either.
 *
 * `run_status.detail` is where the writer puts the reason a run stopped, and the
 * reasons it writes itself are prose about the calendar and the input ("the clock
 * resumed after two missed evenings"). A reason that came from an exception is a
 * different kind of thing: it is written by whichever library raised it, and it can
 * carry a class name, a frame, a driver message or a bound value. Those are blanked
 * rather than published, and the page falls back to its own wording for the state,
 * which it already does when a run recorded no reason at all.
 */
const EXCEPTION_LIKE =
  /(?:^|\b)[A-Z]\w*(?:Error|Exception|Warning):|Traceback|File "[^"]+", line \d+|\b(?:psycopg\w*|boto3|botocore|httpx|yfinance|jose)\b/;

/** The one free-text field with a length of its own, kept short and scrubbed. */
const DETAIL_LIMIT = 240;

/** A store identifier that says where writes went without saying to what. */
const STORE_OK = /^(?:postgres|local|memory)\/[a-z0-9_]+$/;

export interface Finding {
  /** The JSON path, with `[]` where the value sits in an array. */
  path: string;
  /** What it looked like: an email, a url, a dropped key, and so on. */
  kind: string;
  example: string;
}

function keyDropped(key: string): boolean {
  return DROP_KEYS.has(key.trim().toLowerCase());
}

/** Every redaction a string needs, in order. */
function redactionsOf(value: string): string[] {
  const kinds: string[] = [];
  for (const [kind, pattern] of REDACT) {
    pattern.lastIndex = 0;
    if (pattern.test(value)) kinds.push(kind);
    pattern.lastIndex = 0;
  }
  if (TRACEBACK.test(value)) kinds.push("traceback");
  return kinds;
}

function scrub(value: string): string {
  if (TRACEBACK.test(value)) {
    return "the run failed; the detail is in the operator's log";
  }
  let out = value;
  for (const [, pattern] of REDACT) {
    pattern.lastIndex = 0;
    out = out.replace(pattern, REDACTED);
  }
  return out;
}

function maskStore(value: unknown): unknown {
  if (typeof value !== "string") return null;
  return STORE_OK.test(value.trim()) ? value.trim() : null;
}

/**
 * The document as it may be served: the same shape, with nothing in it that names a
 * person, an account, an order, a credential or a place.
 */
export function sanitizeSnapshot(document: unknown): unknown {
  return walk(document, "");
}

function walk(node: unknown, path: string): unknown {
  if (Array.isArray(node)) {
    return node.map((item, index) => walk(item, `${path}[${index}]`));
  }
  if (node === null || typeof node !== "object") {
    if (typeof node !== "string") return node;
    const clean = scrub(node);
    return clean.length > DETAIL_LIMIT && path.endsWith("detail")
      ? `${clean.slice(0, DETAIL_LIMIT)}...`
      : clean;
  }
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(node as Record<string, unknown>)) {
    if (keyDropped(key)) continue;
    const childPath = path ? `${path}.${key}` : key;
    if (key === "store") {
      out[key] = maskStore(value);
      continue;
    }
    if (key === "detail" && typeof value === "string") {
      // Prose the writer wrote is kept, scrubbed; anything that reads like a raised
      // exception is dropped and the page says its own sentence for the state.
      out[key] = EXCEPTION_LIKE.test(value) ? "" : scrub(value);
      continue;
    }
    out[key] = walk(value, childPath);
  }
  return out;
}

/** Everything a public document must not contain, without changing it. */
export function scanForSensitive(document: unknown): Finding[] {
  const found: Finding[] = [];
  scan(document, "", found);
  return found;
}

function scan(node: unknown, path: string, found: Finding[]): void {
  if (Array.isArray(node)) {
    node.forEach((item, index) => scan(item, `${path}[]`, found));
    return;
  }
  if (node === null || typeof node !== "object") {
    if (typeof node !== "string") return;
    for (const kind of redactionsOf(node)) {
      found.push({ path, kind, example: node.slice(0, 80) });
    }
    return;
  }
  for (const [key, value] of Object.entries(node as Record<string, unknown>)) {
    const childPath = path ? `${path}.${key}` : key;
    if (keyDropped(key)) {
      found.push({ path: childPath, kind: "dropped-key", example: key });
      continue;
    }
    if (
      key === "store" &&
      typeof value === "string" &&
      !STORE_OK.test(value.trim())
    ) {
      found.push({
        path: childPath,
        kind: "store",
        example: value.slice(0, 80),
      });
      continue;
    }
    if (
      key === "detail" &&
      typeof value === "string" &&
      EXCEPTION_LIKE.test(value)
    ) {
      found.push({
        path: childPath,
        kind: "error-text",
        example: value.slice(0, 80),
      });
      continue;
    }
    scan(value, childPath, found);
  }
}
