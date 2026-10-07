# rulai-distill · The Distillation Factory

[中文版](./README.md) · [Install & Usage Guide](./GUIDE.md)

Turn **a book, a long video, a podcast, an interview, or a person** into an executable,
verifiable, traceable Agent Skill — not a summary, not a book report.

```
"Distill this book into a skill"     → the agent runs the whole pipeline itself
```

**Status: beta.** The *machinery* is tested (66 regression tests). The *cards it produces*
are not yet publishable quality. Those are two different claims with very different
evidence, and we keep them apart on purpose. See [Honest limitations](#honest-limitations).

---

## Install (works with every major agent)

`SKILL.md` follows the [Agent Skills open standard](https://agentskills.io/specification)
(Anthropic, Oct 2025 — now under the Linux Foundation). Every agent reads the **same file**;
they only differ in *where* they look for it.

```bash
git clone https://github.com/yihexiang/rulai-distill.git && cd rulai-distill
./install.sh              # symlink into every agent directory it finds
./install.sh --copy       # real copies (Windows / no symlink support)
./install.sh --list       # show targets, change nothing
./install.sh --uninstall  # remove them
```

| Agent | Directory |
|---|---|
| Claude Code | `~/.claude/skills/` |
| **Codex CLI** | `~/.codex/skills/`, **`~/.agents/skills/`** (the universal bus) |
| Cursor ≥ 2.4 | `~/.cursor/skills/` |
| Gemini CLI | `~/.gemini/skills/` |
| GitHub Copilot | `.github/skills/` |
| OpenCode | `~/.config/opencode/skills/` |
| OpenClaw | `~/.openclaw/skills/` |
| Hermes | `~/.hermes/skills/` |
| WorkBuddy | `~/.workbuddy/skills/` |

Prefer no script? It is one directory placement:

```bash
git clone https://github.com/yihexiang/rulai-distill.git ~/.codex/skills/rulai-distill
```

**Requirements: Python ≥ 3.10, zero third-party dependencies.** PyYAML / tiktoken /
jsonschema are all optional — the toolchain degrades gracefully without them.

> DeepSeek is a *model*, not an agent — it has no skills directory. Any agent that uses
> DeepSeek as its backend can load this skill, as long as it reads `SKILL.md`. Your local
> `~/.hermes/skills/` already qualifies.

---

## What makes this different from a summarizer

Most distillation tools solve *generation*. This one builds **proof** into the pipeline:

**No release without a passing dual-agent QA gate, and an agent never grades itself.**

```
init → chunk / transcript / research → write skill cards → validate
      → gate (FIDELITY, two independent graders)
      → strategy → compile (atomic) → trigger tests
```

| Stage | What it does |
|---|---|
| `chunk` / `index` | structure-aware chunking; search covers headings **and** body text |
| `transcript` | SRT/VTT → timestamped transcript, fully offline |
| `research` | six-lane persona research skeleton; conflicts are flagged, never silently resolved |
| `validate` | static checks: banned explicit steps, missing failure modes, missing success criteria |
| `gate` | five-dimension scoring; **refuses to publish** on self-graded runs |
| `cross-review` | grading-score spread across independent graders, >10 points → human review |
| `anchor` | verifies a quote is in the **exact paragraph** it claims (not just somewhere) |
| `verify-quotes` | verifies every quote really exists in the corpus |
| `audit-coverage` | exhaustively lists paragraphs the card never covers |
| `overlap` | proves two corpora are non-overlapping (8-gram containment + duplicate sentences) |
| `trigger` | builds trigger-pressure tests; an agent answers, a script grades P/R/F1 |
| `compile` | atomic publish with snapshot + rollback |

Only `fetch-subtitle` touches the network, and it is **dry-run by default**.

---

## Why the paragraph-level anchor exists

Mechanical verification can prove a quote **exists**. It cannot prove the quote
**belongs to the paragraph it is filed under**.

Real case from this repo: a card claimed *"§232 mentions `except with Uber`"*.
The string does exist in the corpus — so `verify-quotes` passed it. What actually
sat at §233 was `except with Uber Lilith`, a boss from *Diablo*, continuing a joke
about a video game. **A fabricated citation had cleared every mechanical check we had.**

That is why `anchor` exists, and why it is a required step for any card that files
quotes by paragraph number.

---

## Quick start

```bash
python3 scripts/td.py doctor                      # environment + capability matrix
python3 scripts/td.py init my-book                # scaffold a bundle
python3 scripts/td.py chunk book.md --max-chars 4000
python3 scripts/td.py index book.md.td --grep "keyword"
python3 scripts/td.py validate my-book
python3 scripts/td.py gate <fidelity-report.md>   # refuses to pass self-graded runs
python3 scripts/td.py compile my-book --out ~/skills/my-bundle
```

Full walkthrough with real captured output: **[GUIDE.md](./GUIDE.md)**.

---

## Honest limitations

1. **Beta.** 66 regression tests prove the machinery. They do **not** prove the produced
   cards are good enough to publish.
2. **The QA isolation is half-done.** Independent *grading* agents work and have caught
   real fabrications. An independent *answering* agent has not been run yet, so
   "the answerer is not the author" currently holds only on the grading side.
3. **Three corpora only** (a book, a person, one video). Everything is verified against
   those, not against a population.
4. **Docs are the weak point in this repo, not the code** — see the roadmap below.

---

## Documentation

| File | What it is |
|---|---|
| [GUIDE.md](./GUIDE.md) | Install + usage, with real command output, command tables, troubleshooting |
| [CAPABILITIES.md](./CAPABILITIES.md) | Which capability came from which upstream project |
| [CONSTRAINTS.md](./CONSTRAINTS.md) | The hard rules, and a ledger of **50 known self-defects** |
| [OPEN-SOURCE-ASSESSMENT.md](./OPEN-SOURCE-ASSESSMENT.md) | Licensing/inheritance assessment |
| [NOTICE](./NOTICE) | Per-upstream attribution |

`CONSTRAINTS.md` publishes our own defects on purpose. A defect that isn't in the
ledger with a regression test attached is not allowed to merge.

---

## Lineage and license

MIT.

- Vendored from [`kangarooking/cangjie-skill`](https://github.com/kangarooking/cangjie-skill) (MIT) —
  19 files copied verbatim, licence retained at `scripts/vendor/cangjie/LICENSE`,
  per-file provenance in `scripts/vendor/PROVENANCE.md`, sha256 baseline in
  `scripts/vendor/VENDOR.sha256` enforced by CI.
- Methodology only (no code vendored) from
  [`alchaincyf/nuwa-skill`](https://github.com/alchaincyf/nuwa-skill) (MIT) and
  [`Yeadon8888/cangjie-skill`](https://github.com/Yeadon8888/cangjie-skill) (MIT).

MIT covers code, not ideas. FIDELITY's five dimensions and the seven-stage pipeline are
this project's own expression.