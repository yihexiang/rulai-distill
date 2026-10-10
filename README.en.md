# rulai-distill · The Distillation Factory v1.6.0

[中文版](./README.md) · [Install & Usage Guide](./GUIDE.md) · [Capability inventory](./CAPABILITIES.md)

Turn **a book, a long video, a podcast, an interview, or a person** into an executable,
verifiable, traceable Agent Skill — not a summary, not a book report.

[![pipeline-check](https://github.com/yihexiang/rulai-distill/actions/workflows/pipeline-check.yml/badge.svg)](https://github.com/yihexiang/rulai-distill/actions/workflows/pipeline-check.yml)
[![Artifact checks](https://github.com/yihexiang/rulai-distill/actions/workflows/artifact-check.yml/badge.svg)](https://github.com/yihexiang/rulai-distill/actions/workflows/artifact-check.yml)
[![Docs freshness](https://github.com/yihexiang/rulai-distill/actions/workflows/docs-check.yml/badge.svg)](https://github.com/yihexiang/rulai-distill/actions/workflows/docs-check.yml)
[![Contract & vendor](https://github.com/yihexiang/rulai-distill/actions/workflows/contract-check.yml/badge.svg)](https://github.com/yihexiang/rulai-distill/actions/workflows/contract-check.yml)
![license](https://img.shields.io/badge/license-MIT-blue)
![python](https://img.shields.io/badge/python-%E2%89%A53.10-blue)
![regression](https://img.shields.io/badge/regression-103%20passing-brightgreen)

> ### Most distillation tools solve *generation*. This one builds **proof**.
> **No release without a passing gate — and an agent never grades itself.**

---

## ⚡ 30-second start

```bash
git clone https://github.com/yihexiang/rulai-distill.git && cd rulai-distill
./install.sh                  # symlink into every agent directory it finds
python3 scripts/td.py doctor  # zero-dependency self-check + capability matrix
```

Zero third-party dependencies. **Python ≥ 3.10** is all you need (PyYAML / tiktoken /
jsonschema are optional — the toolchain degrades gracefully without them).

`SKILL.md` follows the [Agent Skills open standard](https://agentskills.io/specification),
so the **same directory** works for Claude Code, Codex CLI, Cursor, Gemini CLI, GitHub
Copilot, OpenCode, Hermes and WorkBuddy. Then just say: *"distill this book into a skill."*

---

## Why it is worth trying: three things most skills don't do

### 1️⃣ The gate is **enforced by code**, not by a paragraph of documentation

```
validate       →  structure / dead links / success criteria / failure modes   (0 errors to continue)
verify-quotes  →  every quote traced back to the corpus, word for word        (does it EXIST?)
anchor         →  is the quote inside the paragraph it claims?                (does it BELONG there?)
lint-quotes    →  mixed scripts / ellipsis / suspicious attribution           (WHY can't it be verified?)
gate           →  requires ≥2 independent graders by default; otherwise REFUSES
```

`compile` refuses to ship a card below the FIDELITY threshold. Self-graded runs
(`fallback-self`) are **not** accepted by default. Failed evaluations carry
`verdict: "fail"` — renaming the file does **not** get it past `gate`.

### 2️⃣ Independence is **structural**: answerer ≠ grader ≠ author

`td.py eval-kit` turns independent QA into a set of JSON files plus one command:

| Role | Who | Constraint |
|---|---|---|
| Question author | human + seed template | `edge_honesty` (the only dimension that catches fabrication) **cannot** be machine-generated — a human must write those |
| Answerer | a separate agent | gets the card only, no author memory; identity must differ from the author's |
| Graders | **≥2** separate agents | cannot see each other; two identical grader IDs do not count as two people |
| Aggregator | `eval-kit check` | score spread >10 → human review; empty set / single grader → **never** a pass |

### 3️⃣ Defects live in a **ledger**, and the ledger is enforced by tests

All **70** self-found defects are published in `CONSTRAINTS.md` and mirrored as
machine-checkable failure cases (`td.py failure list`) — each with *what went wrong /
what it should have been / severity / the regression test that pins it*.
**Ledger rows, category counts and the regression count are asserted equal by tests —
a wrong number turns CI red.**

70 of the 70 are defects **in our own verification and measurement tools** (78%).
That ratio is itself the finding: **what is most often wrong is not the thing — it's the ruler.**

---

## 🧪 Real results (every number is reproducible)

| Artifact | Material | Score | How it was produced |
|---|---|---|---|
| `five-affairs-seven-questions` | Book (*The Art of War*, 計篇) | **93 / A** | independent answerer agent + 2 independent grader agents (90 / 98, spread 8); the report ships with the sample: `examples/sample-bundle/skills/five-affairs-seven-questions/FIDELITY.json` |
| `musk-decisions` | Person (three long interviews, 44,630 words) | **90 / A** | same protocol (92 / 89, spread 3); **replaces the old 60/C single-grader result** |
| 9 real cards (bazi / name-study / I-Ching / video / persona / book …) | mixed | — | `validate` + `output-eval` + `lint-quotes` actually run: **0 errors, no crashes, no false reds** |

**The boundaries of those numbers, stated up front**: independence is **structural**
(separate sub-agents), *not* organizational (no second human reviewer); `musk-decisions`
was probed with only 3 human-written questions; the sample card is a polished showcase and
**does not represent open-ended material in general**.

### Open-material arm (P0-2 · added 2026-10-10)

The 9 cards above cover **closed / semi-closed material** (book excerpts, interviews, TED video).
P0-2 adds the "**large public-domain corpus**" category, proving the toolchain is not limited to
small samples — it also ingests ~252 KB of public-domain classics:

| Role | Content | Status |
|---|---|---|
| Fetch — normalize — chunk | 4 public-domain classics: *Zizhi Tongjian* (Wei), *Mencius*, *Hanfeizi*, *Analects* — **252,492 raw bytes / 90,288 clean chars / 226 fetch segments** total | `fetch_wikisource` → `corpus-anchor` ran, no crashes |
| End-to-end card | `lunyu-conduct` (Analects → conduct & reading-people framework) | `validate` + `lint-quotes` pass; `eval-kit init` produced the grading kit |
| Independent cross-review | `lunyu-conduct` | **pending** (independent answerer sub-agent file-write reliability, see below) |
| Remaining 3 corpora | Tongjian / Mencius / Hanfeizi | fetch—normalize—chunk ready; carding is the next increment |

Per-corpus evidence and known boundaries:
[`docs/scale-evidence-open-material-2026-10-10.md`](./docs/scale-evidence-open-material-2026-10-10.md)
(same workspace as this repo).

**Boundaries of the open-material arm (also stated up front)**:

- **Chunk granularity depends on headings.** `corpus-anchor` splits on markdown headings;
  *Hanfeizi* / *Analects* bodies use traditional numbering (chapter / `一之一`) instead of headings,
  so they collapse to 3 chunks. This **does not block carding** (carding reads the fine-grained
  segment markers after anchoring), but it means the P0-3 token-savings baseline (from
  headed corpora) understates savings for heading-less long prose.
- **Open material is not yet independently cross-reviewed.** `lunyu-conduct` is built but the
  independent answerer + dual grader run has not happened — so "the toolchain can eat large
  corpora" **does not equal** "cards on large corpora are independently verified". This is the
  same boundary as above ("6 cross-reviews ≠ 6 material kinds") extended to open material.

---

## 🚦 Status: beta — read this first

**The machinery is verified; the cards it produces are not yet publishable quality.**
These are two claims with very different evidence, and we keep them apart on purpose.

| Dimension | Status | Evidence |
|---|---|---|
| **Mechanical reliability** | ✅ trustworthy | 103 regression tests green; `gate` requires a cross-review record (verified live); `verify-quotes` / `anchor` / `lint-quotes` have each caught real problems on real material; the toolchain runs on **9 real cards** with zero crashes and zero false reds |
| **Output correctness** | ⚠️ **closed loop proven, still material-dependent** | `eval-kit` has run a **real cross-review** on **6 cards** (independent answerer + 2 independent graders): sample card **93/A**, `musk-decisions` **90/A**, `bazi-paipan` **93/A**, `geju-yunshi` **95/A**, `quming-xue` **96/A**, `zhouyi-yili` **96/A**. ⚠️ All are **structurally** independent, not organizationally; the sample card is a showcase, **not** the average of open-ended material; the four guoxue cards share one corpus-prep style, so four passes is **not** four kinds of material validated. Per-claim evidence: [`docs/CLAIMS.md`](./docs/CLAIMS.md) |

Concretely, what this project currently **cannot** do:

1. **It cannot guarantee a quote is filed under the right paragraph.** In a 2026-10-05 run an
   independent grader caught a fabricated citation (a *Diablo* boss name presented as evidence
   for a methodology claim) that had passed all three mechanical checks available at the time.
   `anchor` and `lint-quotes` now exist — but **the boundary of what verification can catch
   has to be redrawn by experiment, not by hope**.
2. **Independence holds structurally, not organizationally.** The loop has genuinely run
   (`eval-kit`: separate answerer sub-agent + 2 separate grader sub-agents), but they are still
   sub-agents on the same machine — **no second human has reviewed them**, and sub-agent
   file-writes remain unreliable on long tasks (historically, 1 of 4 dispatches landed reliably).
3. **The open-material card is not yet independently cross-reviewed.** Cross-review has only run
   on **6** closed / semi-closed cards (`musk-decisions` with just 3 questions). The open public-domain
   card (`lunyu-conduct`, Analects) is built and passes `validate` / `lint-quotes`, but the independent
   answerer + dual grader run has not happened (sub-agent file-write reliability).
   The 9 real cards (closed / semi-closed) + 1 open-material card prove *the tools run* — **not**
   that the cards are good.

**Good for**: the pipeline skeleton and the gate design — validation, gating, snapshots,
rollback, contract-checked artifacts are solid and reusable as-is.
**Not for**: "feed it raw material, get a high-quality card" automation.

This section sits at the top on purpose. It is what the project's own methodology demands:
`gate` once rejected a 60-point report whose author (me) wanted to make it look nicer.
**An honest score matters more than a pretty one.**

---

## 🗺️ The seven-stage pipeline

| Stage | What happens | Artifact |
|---|---|---|
| 0 | Holistic understanding (Adler) + chunking | `BOOK_OVERVIEW.md` + `*.td/` |
| 1 | Five parallel extraction lanes | candidate unit pool |
| 1.5 | Triple verification (source / executable / useful) | surviving units |
| 1.6 | Promotion gate (five independence checks) | `promoted` / `router` |
| 2 | RIA++ capability construction / persona implants | capability card / persona card |
| 3 | Zettelkasten linking (with confusable-pair analysis) | relation graph |
| 4 | Trigger stress tests + FIDELITY QA | test suite / `FIDELITY.md` |
| 5 | Output-mode decision → compile → atomic publish | `out/` + `BUILD_MANIFEST.json` |
| 6 | Registry, diff / impact / patch, continuous evolution | `registry/<slug>.json` |

---

## 📦 Full workflow (copy-paste)

```bash
# 0. self-check (works with zero dependencies)
python3 scripts/td.py doctor

# 1. scaffold a bundle, then write cards from templates/CAPABILITY.md.template
python3 scripts/td.py init books/my-book
vim books/my-book/skills/*.md

# 2. long material: chunk (>50k chars is mandatory) and search headings + body
python3 scripts/td.py chunk book.md --max-chars 4000
python3 scripts/td.py index book.md.td --grep "keyword"

# 3. video / podcast: subtitles (dry-run by default) → transcript → chunks
python3 scripts/td.py fetch-subtitle "<URL>" --out subs/ --execute
python3 scripts/td.py transcript subs/<id>.srt

# 4. person: six-lane research (skeleton + conflict flags + first-hand ratio)
python3 scripts/td.py research init books/my-person --person "Someone"
python3 scripts/td.py research merge books/my-person/references/research/*.md \
        --out books/my-person/references/research-merged.md

# 5. the three gates
python3 scripts/td.py validate books/my-book
python3 scripts/td.py lint-quotes books/my-book/skills/x/SKILL.md --corpus corpus/src-01.md
python3 scripts/td.py eval-kit init books/my-book/skills/x/SKILL.md --out kit/
#    → an independent answerer fills answers.json; 2 independent graders fill scores-*.json
python3 scripts/td.py eval-kit check --answers kit/answers.json \
        --scores kit/scores-1.json kit/scores-2.json --out FIDELITY.json
python3 scripts/td.py gate FIDELITY.json --min B

# 6. publish and roll back (atomic + snapshot + manual-edit detection)
python3 scripts/td.py compile books/my-book --out ~/.workbuddy/skills/my-book --with-reports
python3 scripts/td.py rollback ~/.workbuddy/skills/my-book --to latest
```

**Regression suite**: `python3 tests/e2e.py` (103 tests, covering every command and the
vendored upstreams).

---

## 🔗 Lineage: what came from where

Fuses three MIT projects and promotes their **contracts** to authoritative standards.

| Upstream | What it contributes | Where it lives here |
|---|---|---|
| [`kangarooking/cangjie-skill`](https://github.com/kangarooking/cangjie-skill) | chunking + FTS5 lexical index + run provenance + write locks + atomic publish + evolution scripts (17 scripts, **vendored verbatim**) | `scripts/vendor/cangjie/` → `td.py upstream run …`; thin wrappers in `td.py` |
| [`alchaincyf/nuwa-skill`](https://github.com/alchaincyf/nuwa-skill) | FIDELITY scorecard + cross-review ("third iron law") + subtitle pipeline + six-lane research (methodology only, no code) | `tdlib/fidelity.py`, `tdlib/evalkit.py`, `td.py fetch-subtitle` / `transcript` / `research` |
| [`Yeadon8888/cangjie-skill`](https://github.com/Yeadon8888/cangjie-skill) | cognitive-implant persona structure + explicit-step ban + single-file prompt compile | `extractors/persona-extractor.md`, `validate` checks, `td.py prompt` |

**Upstream code is never modified**: `scripts/vendor/cangjie/` is the MIT original
(licence retained, per-file provenance in `scripts/vendor/PROVENANCE.md`,
sha256 baseline in `scripts/vendor/VENDOR.sha256`, enforced by CI).
Our own layer (`scripts/tdlib/`) is "a zero-dependency unified entry point + the parts
upstreams don't have": FIDELITY gating, the eval-kit loop, three-layer quote verification,
the subtitle pipeline, six-lane research, conflict flagging, prompt compilation.

---

## 📜 Honest disclaimers

1. **Semantic extraction is done by an agent, not by a script.** `td.py` only performs
   deterministic file operations.
2. **A FIDELITY score is not self-evidence.** Without an independent sub-agent the run is
   labelled `fallback-self`; `gate` **refuses it by default** (`--allow-fallback` required),
   and it is discounted to 80% with the style dimension voided.
3. **Only `fetch-subtitle` touches the network**, and it is dry-run by default. The other
   36 subcommands are fully local. If you already have subtitle files, no network is needed.
4. **`--force` publishing is technical debt.** The manifest records `forced: true`; auditable.
5. **Trigger evaluation makes no LLM calls** (zero network): an agent answers, a script grades.
6. **Scale measured, savings not.** Long-material runs measured **corpus size** (up to a
   1.13M-character tweet collection) and chunking behaviour — but **"chunked retrieval vs
   stuffing the whole book" token savings have not been quantified yet**.
7. **"Verified" is not "correct."** The tools prove only the faces they check:
   `verify-quotes` proves existence, `anchor` proves paragraph attribution, `lint-quotes`
   proves character-level consistency. Passing all three means *those three classes of
   error were not detected* — nothing more.

---

## ⚖️ License

MIT. Vendored upstream code keeps its original licence and copyright
(see `scripts/vendor/PROVENANCE.md` and `NOTICE`).

> ⚠️ **Do not `git init` inside a working directory that holds raw material** — real
> interview transcripts and subtitles are copyrighted and would be published with it.
