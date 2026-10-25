# The public dashboard: what it serves, what it may show, and how to publish it

Status: **the page is public as of 2026-10-25.**
<https://efb-live-book.nutritrack.workers.dev> answers anyone, the Access application that
fronted it is deleted, and the Worker serves the sanitized snapshot to a request with no
token because `PUBLIC` is `"true"` in `web/wrangler.jsonc`. The audit below was written
while the page was still private and is kept as it was, with the two changes since
recorded in sections 6 and 10: the route no longer requires the assertion, and section 8's
check has been run against the public hostname and came back clean. Everything here was
read from the live account and the live bucket, not from a fixture.

## 1. The document, fetched from the bucket

```
npx wrangler r2 object get efb-snapshots/latest.json --file /tmp/latest_snapshot.json --remote
```

`efb-snapshots/latest.json` is byte-identical to `efb-snapshots/snapshots/2026-10-23.json`:

| | |
|---|---|
| bytes | 74,676 |
| `generated_at` | 2026-10-23T22:52:54.807373Z |
| `target_close` | 2026-10-23T00:00:00 |
| `run_status.status` | ok, `cadence.day` rebalance, `cadence.k` 21 |
| top-level keys | 20: `actual_holdings`, `attribution`, `book`, `book_as_of`, `breadth`, `bridge`, `construction`, `dry_run`, `expected_next_by`, `exposures`, `exposures_after_hedge`, `exposures_before_hedge`, `generated_at`, `hedge`, `positions`, `reconciliation`, `run_status`, `schema_version`, `store`, `target_close` |

It is committed as `web/fixtures/snapshot_2026-10-23_evening.json`, declared in
`scripts/make_web_fixtures.DATED_DOCUMENTS`, so the page's tests read the real thing.

## 2. The fields that could be sensitive, by path

Every leaf of that document was scanned for account ids, order ids, emails, hostnames,
absolute paths, identifiers, secrets and error text. What the scan found, and what each
field *could* carry:

| JSON path | what it is | why it is the risk |
|---|---|---|
| `run_status.detail` | the reason a run stopped | **the one field that really leaked.** `web/fixtures/snapshot_2026-10-14_error.json` carries `KeyError: "['dividend', 'split_factor'] not in index"`, published as-is. A psycopg, boto3 or httpx message in the same field can carry a DSN, a bucket name or a request URL |
| `store` | where the run's writes went | the schema says "or why they could not go anywhere": on a failed write it holds a driver message, and the local fixtures hold `local parquet (live/state/supabase)` |
| `positions.note` | the mismatch sentence | generated text; today it names tickers and dollars, and nothing stops a future writer from adding the account it compared |
| `attribution.notes[].text`, `attribution.live.note` | dated notes about the series | writer-authored prose, same shape of risk as above |
| `run_status.worst_input`, `run_status.failing_inputs` | input names | safe as written (`prices`), but they are the only free text left near a failure |
| `actual_holdings.exits.window` | a read window | timestamps only |
| generic key names anywhere | `account_id`, `order_id`, `client_order_id`, `email`, `token`, `api_key`, `secret`, `password`, `dsn`, `bucket`, `endpoint`, `file_path`, `traceback` | none is present today; each is one writer change away |

The 2026-10-23 document itself contains **none** of these values: 1,050 string leaves, 11
of them longer than 30 characters, all descriptive. The risk was never in this document;
it was in the field shapes and in the one historical document that really did carry an
exception string.

## 3. The routes the Worker serves

`web/worker/index.ts`, one handler, before this change:

| path | methods | response |
|---|---|---|
| `/api/snapshot` | any | 403 without a valid Access assertion, else the raw `latest.json`; 404 `{missing:true}` when the object is absent |
| everything else | any | the built page, from the ASSETS binding |

What was wrong with that, and what changed:

| | before | after |
|---|---|---|
| method | any method reached the read | GET and HEAD only, 405 with `Allow: GET, HEAD` otherwise |
| unknown API path | `/api/anything` fell through to the page's SPA fallback | 404 `{error:"not found"}` for `/api` and `/api/*` |
| body | `latest.json` echoed as text | parsed and sanitized; a body that will not parse is a 502, not an echo |
| dated snapshots | **no route serves them**; only `latest.json` is read | unchanged: there is still no dated route, and the sanitizer is the single choke point if one is ever added |
| caching | `no-store` everywhere | the sanitized snapshot is `public, max-age=300`; every refusal stays `no-store` |

No route can reach an environment variable: the only bindings the Worker reads are
`SNAPSHOTS` (R2) and `ASSETS`, and `ACCESS_TEAM_DOMAIN` / `ACCESS_AUD` are used to verify a
token and are never serialized into a response.

## 4. Requests and cost per page load

- **Three R2 reads per page load** today: the Worker reads `latest.json` once per
  `/api/snapshot` request, and the page makes one such request on load. An extra read
  happens only if the reader reloads.
- **One Worker invocation per request**, two per page load (the document and one asset
  request; assets are served from the Workers assets binding, which does not bill as a
  separate R2 read).
- **Cost of a public page at 10,000 views a day**: 10,000 R2 class-B reads and 20,000
  Worker requests. On Cloudflare's published limits that is inside the free tier for
  Workers requests (100,000/day) and far inside R2's free monthly class-B allowance
  (10 million/month), so the page is free at that traffic. The risk is not cost, it is
  bandwidth on the 75 KB document: 1 GB per 13,000 loads.
- **Caching**: the snapshot now carries `public, max-age=300`, so a browser or an
  intermediary may reuse it for five minutes. That is safe *because the body is
  sanitized*; while Access is on, the 403 is `no-store` so a refusal is never reused.

## 5. What the Worker strips

`web/worker/sanitize.ts`, applied to every snapshot the Worker answers with:

1. **Key denylist, at any depth:** `account_id`, `account_number`, `account_uuid`,
   `order_id`, `broker_order_id`, `client_order_id`, `email`, `notify_email`,
   `email_from`, `email_to`, `token`, `api_key`, `api_secret`, `secret`, `password`,
   `dsn`, `connection_string`, `endpoint`, `endpoint_url`, `bucket`, `file_path`,
   `traceback`, `stack`, `raw_error`.
2. **Value redaction, in place**, for anything that looks like an email, a URL, a
   Supabase / R2 / Render / workers.dev / Access / AWS hostname, an absolute path
   (`/Users/`, `/home/`, `/tmp/`, `/var/`, `/srv/`, `/opt/`, `C:\`), a UUID, an `efb-`
   client order id, an Alpaca account id, a JWT, or an `AKIA`/`ASIA` key.
3. **`store` masked** to the enum it should have been: `postgres/...`, `local/...`,
   `memory/...`, or `null` for anything else, including a failure reason.
4. **`run_status.detail` blanked** when it reads like a raised exception (a `SomethingError:`
   prefix, a traceback frame, or a driver/library name); the writer's own prose about the
   calendar and the inputs stays, because that is the page's explanation.

Verified on the real document: sanitizing it changes **nothing** (it is clean as
written), and sanitizing every fixture changes only `store` and `run_status.detail` in the
files that carry a non-enum store or a real exception. `worker/published.test.ts` fails if
any fixture ever gains a field the sanitizer would have to touch, which is the standing
guard on the writer.

## 6. Deployment, versions, and rollback

| | |
|---|---|
| before the sanitizer | `d2de3169-6e99-4079-8642-5a87dfb8f1f7`, created 2026-10-22T23:32:44Z |
| the sanitizer, still requiring Access | `ec18c6ba-b49d-4d4e-a601-3b319baae924`, created 2026-10-25T03:30:20Z, merged `b5e79a2` |
| **the page public** | **`d1db763c-5631-4cbd-9a80-df8c1da9e414`**, created 2026-10-25T12:21:52Z, merged `dcd4443` |
| rollback from public | `cd web && npx wrangler rollback ec18c6ba-b49d-4d4e-a601-3b319baae924` |

**What a rollback does now.** Every version before `d1db763c` still requires a valid
Access assertion, and the Access application this hostname used is gone, so rolling back
to any of them makes `/api/snapshot` answer the Worker's own 403 to everyone. That is the
safe direction: the page fails closed, nothing is served, and no unsanitized body is ever
reachable by rolling back. Do not roll back to `d2de3169` while the page is public unless
Access is put back first: that version echoes `latest.json` with no sanitizer at all.

**To re-lock the page**, in this order: set `"PUBLIC": "false"` in `web/wrangler.jsonc`
and `cd web && npx wrangler deploy` (the route demands the assertion again), then re-add
the Access application as section 8 describes, which also gives a new AUD to put back in
the same file. Setting `PUBLIC` to anything other than the exact string `true` closes the
route, so the deploy is the lock and the application is the door.

## 7. What the Worker serves, checked before the page opened

While Access was still on, the hostname answered a 302 to its login for every path, so the
Worker was never reached from outside:

```
GET /             -> 302
GET /api/snapshot -> 302
GET /api/other    -> 302
```

To see the body the Worker produces, the deployed handler was run locally
against the production bucket (`wrangler dev --remote`, with only the Access decision
injected and no deploy), and the response scanned:

| check | result |
|---|---|
| `GET /api/snapshot` | 200, 69,490 bytes, `content-type: application/json`, `cache-control: public, max-age=300` |
| served body against the raw object | identical **values**; the difference in bytes is only the writer's indentation |
| findings in the served body (account ids, order ids, emails, hosts, paths, identifiers, secrets, error text) | **0** |
| `HEAD /api/snapshot` | 200, headers, no body |
| `POST`, `DELETE /api/snapshot` | 405 with `Allow: GET, HEAD` |
| `GET /api`, `GET /api/other` | 404 `{"error":"not found"}` |
| `GET /` | 200, the page |

## 8. How the page was made public, and the check that was run

This section was written while the page was private; the steps below are the ones that
were taken, and the check is the one that came back clean on 2026-10-25.

**The removal**, by the owner in the dashboard, after the wrangler login here turned out
to have no Access scope and no token existed to create one: Zero Trust, Access,
Applications, the application on `efb-live-book.nutritrack.workers.dev` (AUD
`6d6b4aec421a3a0c13d54d45a7f6a6ad2bd0b1c75602fa88ba4f073b15908620`), Delete.

That left the Worker answering its own 403, which is why the `PUBLIC` switch exists: the
edge no longer asks for a login and the Worker was still demanding the assertion it had
been handed by it. Setting `PUBLIC` to `"true"` is the second half of the change.

**The check, run from this machine with no session and no cookie:**

```
curl -sI https://efb-live-book.nutritrack.workers.dev/api/snapshot
HTTP/2 200
content-type: application/json
content-length: 69490
cache-control: public, max-age=300
```

and the body, scanned with the patterns in this section: 69,490 bytes, parses as JSON, 20
top-level keys, **no email, no URL, no absolute path, no UUID, no Alpaca account id, no
hostname, no error text, no client order id, no JWT, no cloud key, and no denied key name
anywhere in the tree.**

The routes around it, anonymously: `GET /` 200 (the page), `GET /api/other` 404,
`GET /api` 404, `POST /api/snapshot` 405.

## 8a. The steps, kept for the next application

The wrangler login is an OAuth token with no Access scope (`wrangler whoami` lists
workers, R2, KV, D1, pages, zones and more, but no `access`), there is no
`CLOUDFLARE_API_TOKEN` in the environment, wrangler has no Access command at all, and the
dashboard session in the browser is not signed in. Creating a token was out of scope, so
the removal is the owner's.

**Owner steps, in the dashboard:**

1. Open **Zero Trust** (one.dash.cloudflare.com) for the account that owns
   `efb-live-book.nutritrack.workers.dev`.
2. **Access → Applications** and find the application whose domain is
   `efb-live-book.nutritrack.workers.dev`. Its AUD is
   `6d6b4aec421a3a0c13d54d45a7f6a6ad2bd0b1c75602fa88ba4f073b15908620` and its team domain
   is `amankesar.cloudflareaccess.com`, which is how to recognise it.
3. Open it, **Delete** the application (deleting the policy with it), and confirm.
4. Leave `preview_urls: false` in `web/wrangler.jsonc` alone: it is what keeps a second
   hostname from existing outside the policy.
5. Optional, and the safer order: do step 3 only after the check below has been run once
   with a service token, or accept the gap and run it immediately after.

**The check to run afterwards, from a machine with no session:**

```bash
curl -s -D /tmp/h -o /tmp/body https://efb-live-book.nutritrack.workers.dev/api/snapshot
grep -iE "^(HTTP|cache-control|content-type)" /tmp/h
python3 - <<'PY'
import json, re
body = open("/tmp/body").read()
patterns = {
    "email": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    "url": r"https?://", "path": r"(/Users/|/home/|/tmp/)",
    "uuid": r"\b[0-9a-f]{8}-[0-9a-f]{4}-", "account": r"\bPA[A-Z0-9]{6,}\b",
    "host": r"(supabase|r2\.cloudflarestorage|onrender|cloudflareaccess)",
    "error": r"(Traceback|Error:|Exception:)",
}
hits = {name: re.findall(p, body) for name, p in patterns.items() if re.search(p, body)}
print("bytes:", len(body), "| findings:", hits or "none")
json.loads(body)
PY
```

Expect `HTTP/2 200`, `cache-control: public, max-age=300`, and `findings: none`. **If
anything is found, restore Access before doing anything else:**

1. Zero Trust → **Access → Applications → Add an application → Self-hosted**.
2. Name it `efb-live-book`, domain `efb-live-book.nutritrack.workers.dev` (subdomain
   `efb-live-book`, domain `nutritrack.workers.dev`), path empty.
3. Add one policy: **Allow**, rule **Emails**, value the owner's email; set the session
   duration to 24 hours.
4. Save, then copy the new application's **Application Audience (AUD) tag** and update
   `ACCESS_AUD` in `web/wrangler.jsonc`, because the Worker verifies the assertion against
   it: `cd web && npx wrangler deploy`.
5. Re-check with the curl above: it must be a 302 again.

## 9. What the sanitizer does not do

- It does not thin the document. The page renders most fields, so a whitelist would be a
  page change and a schema decision, not a filter; the denylist plus the value rules is
  the boundary that needs no page work.
- It does not stop a future writer from putting a *number* where a name belongs: the
  positions, weights and dollars are the page's content and are published as they are.
  What is public is the book, not the account.
- It does not make the document a market signal: it is a paper book on a null signal, and
  the README says so.
