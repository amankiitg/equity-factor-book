# Sprint E13 PRD: Credit Port Design (document only)

Sprint E13, 2026-09-27. Tier 3. The sprint that writes the design note mapping
every EFB module to its corporate-credit counterpart, so that the first weeks of
credit factor-model work start from a plan rather than a blank page. No code, no
live data, no new panels.

## Research framing, copied verbatim from the roadmap

- Academic question: Which assumptions of the equity factor framework (linear exposures, daily liquid prices, diagonal specific risk) hold in corporate credit, and which break?
- Practitioner question: Which parts of this framework transfer directly to credit, and which require fundamentally different treatment before a credit PM would trust them?
- Research question: Which EFB numbers (bias bands, hedge efficacy, cost sensitivity) should be re-estimated first in credit, and what data would they need?

## Deliverable and audience

`docs/credit_port_design.md`. It is written for the risk system lead at a
multi-strategy fixed income fund with institutional data: TRACE prints, an index
membership archive with daily constituent files, a rating and sector reference
set, dealer quotes through a live feed, and a credit risk system of record that
already produces spreads, durations and DTS. It tells that reader which parts of
the framework transfer unchanged, which need re-specifying, and which break, and
it closes with a phased build plan whose exit evidence is a stored number in the
form EFB uses.

The note carries, at minimum: the schematic credit X matrix for three bonds; the
factor mapping table with a column naming what breaks; the module map with a
status per module (F13.1); the open questions for the research team, each tied to
an EFB number; the defect classes this project hit and their credit form; and the
phased build plan. The sections the roadmap's scope list requires are: universe
and identity, survivorship, the return definition, the factor model with DTS as
the core exposure, specific risk at issuer and bond level, hedging with CDX and
Treasury futures, costs from TRACE, and the live loop with staleness and the
pricing of illiquid bonds.

## Pre-registered falsification criteria, copied verbatim from the roadmap

Numeric thresholds written before the numbers are seen; each is evaluated with a
stored number in sprints/E13/RESULTS.json.

- **F13.1**: Every EFB module appears in the port map with a status: unchanged, re-specified, or dropped, with one sentence of reason.
- **What would falsify this?** A module marked unchanged that in fact depends on an equity-only assumption; an open question with no EFB evidence behind it.
- **Exit criteria**: Design note reviewed against the coverage map; nothing unmapped. Research deliverable written and linked from the Methodology tab.

## The two rules this sprint is held to

- **Every EFB number cited is read from a stored file.** The citation form in the
  note is `EFB: <path>`, and `tests/test_e13_design_note.py` fails if any cited
  path does not exist in the repository.
- **F13.1 is about the repository, so it is a test.** The same suite enumerates
  every module and fails if any is missing from the map, and it asserts that the
  count registered in `sprints/E13/RESULTS.json` is the count the suite measures.

## What this sprint is not

- No credit data is used, because none is available. Every credit statement in
  the note is a design statement or a prediction, and the note says so where the
  distinction matters.
- No new dashboard panel. The dashboard increment is the design note linked from
  the Methodology tab, which the roadmap asks for explicitly.
- No change to any E1 to E12 artifact, criterion or stored number. The port map
  cites them; it does not re-measure them.
