# How we work: token-lean workflow

**Rule 0: Claude tokens are the scarce resource. Codex, Gemini and Antigravity are not.**
Claude plans, decides, reviews and talks to the user. Cheap agents do bulk work. Claude only reads their *diff and test result*, never their whole exploration.

---

## 1. Who does what

**Local Superpower: Parallel Subagents.** This project uses the `freellmapi` proxy (`http://127.0.0.1:31415`). In Biostack, we ignore global "don't spawn subagents" limits and instead fan out tasks across independent models (e.g. `llama-3.3-70b`, `qwen3.6-27b`, `command-a`) to keep context small and execution fast.

| Job | Who | How |
|---|---|---|
|---|---|---|
| Decide, design, review, final merge | **Claude** | normal session |
| Small edits (rename, i18n strings, lint fixes, boilerplate, docs, test scaffolds) | **Codex** | `codex exec "<brief>"` from repo root |
| Read-heavy research, summarizing logs/CSVs/docs, large-file digestion | **Gemini** | `gemini -p "<brief>"` |
| Parallel or long agent tasks, UI/browser work | **Subagents (parallel)** | freellmapi proxy |
| Multi-file audits, bulk tests, sliceable edits | **Subagents (parallel)** | Spawn 4-8 agents in one turn |
| Anything risky: migrations, deploy, real DB, auth | **Claude** (or Claude reviews line by line) | never delegate blind |

Shell note: `codex`, `gemini` and `agy` are wrapped by `aisw workspace check`, so they only run in an allowed workspace. If one refuses, run it from the repo root.

### Delegation brief template (keep it short, this is what saves tokens)
```
Goal: <one sentence>
Files you may touch: <exact paths>
Do NOT touch: biostack.db, data/, ports 3000/8000, anything not listed
Done when: <command that must pass, e.g. cd apps/api && pytest -q path>
Output: reply with only a summary of changes plus the test result
```
Then Claude runs `git diff --stat` and the test command. Claude does not re-read what the agent read.

Fallback: when Claude hits its 5-hour limit, the same briefs go to Codex/Gemini so work never stalls.

---

## 2. Navigate with indexes, not file reads

**Parallel study:** Use subagents for heavy reading or summarization.

Order of attack for "where/how does X work?", cheapest first:

1. **Repowise** (`.claude/CLAUDE.md` already holds the summary: modules, entry points, bug magnets)
   - `get_answer`: how X flows end to end
   - `get_context ... include=["references"]`: callers before a rename
   - `get_risk`: what breaks if a file changes
   - `get_change_risk` + `get_health`: before finishing a multi-file change
   - Status: the MCP server **failed to connect this session**. Restart it first. The `repowise` CLI is at `~/.local/bin/repowise`.
2. **Parallel subagents:** use freellmapi proxy to slice reading across independent models. Split reading-heavy research or large-file digestion into parts (e.g. a section per agent, each on a different model). E.g. study `lib/types.ts` section by section, or grep across the codebase in independent slices.
   - Spec example: each subagent reads one slice of `apps/web/components/` (e.g. 5-10 files), greps for 'bug' or given patterns, and produces a concise finding or a bulleted summary.
   - Then Claude synthesizes, writes a short report, and decides next steps.
3. **Subagent readings:** subsequent calls can read results from other subagents via messages.
   - See below: `docs/WORKFLOW.md`, "Parallel subagent execution patterns".
4. **Grep/Glob** for exact identifiers and file names (faster than either index).
5. **Read** only the lines you will edit (`offset`/`limit`), never whole big files.

Noisy output (tests, builds, `git log`/`diff`): `repowise distill <cmd>`; restore omitted parts with `repowise expand <ref>`. Don't re-run the command.

Files that need extra care (from the index): `context_builder.py`, `lib/types.ts`, `samsung_import.py`, `wearable_derive.py`. Check `get_risk` before editing them.

---

## 3. What the ECC harness changed

ECC adds hooks, agents and skills on top of plain Claude Code.

- **GateGuard hook**: the first Bash command and the first edit or write to a file are blocked until Claude states the facts the gate asks for (request, purpose, duplicates, where it is linked). This is expected, not a bug. Escape hatches: `ECC_GATEGUARD=off`, `GATEGUARD_BASH_ROUTINE_DISABLED=1` (routine Bash only), or `GATEGUARD_EXEMPT_GLOBS` (path-based).
- **Specialist agents** (they keep file dumps out of Claude's context): `ecc:python-reviewer`, `ecc:fastapi-reviewer`, `ecc:typescript-reviewer`, `ecc:react-reviewer`, `ecc:database-reviewer`, `ecc:healthcare-reviewer` (PHI and clinical safety, relevant here), `ecc:security-reviewer`, `ecc:build-error-resolver`, `ecc:tdd-guide`, `ecc:refactor-cleaner`, `ecc:doc-updater`.
- **Token and cost skills**: `ecc:token-budget-advisor`, `ecc:context-budget`, `ecc:strategic-compact`, `ecc:model-route`, `ecc:cost-report`, `ecc:token-card`, `ecc:parallel-execution-optimizer`, `ecc:search-first`.
- **Quality gates**: `ecc:verification-loop`, `ecc:quality-gate`, `ecc:code-review`, `ecc:security-scan`, `ecc:harness-audit`.
- **Discovery**: `/ecc-guide` (menus), `/ecc-guide find: <query>`.

Habit changes:
1. Skills are checked before acting (brainstorming before features, systematic-debugging before fixes, verification-before-completion before saying "done").
2. Reviews go to a reviewer agent, not to Claude re-reading the diff.
3. We compact context deliberately (`ecc:strategic-compact`) between phases instead of letting it bloat.

---

## 4. Standard loop for a task

1. **Locate**: Repowise/Graphify, then targeted Grep. No wide file reading.
2. **Plan** (Claude, short): list steps and mark each `claude` or `codex/gemini`.
3. **Delegate**: send the small tasks with the brief template. Run independent ones in parallel.
4. **Verify**: `git diff --stat`, run the named tests, lint (`ruff`, `tsc`, `eslint`). Use `distill` for noisy output.
5. **Review**: language-specific reviewer agent, plus `get_change_risk` and `get_health` on touched files.
6. **Commit** only when asked. Compact context before the next task.

### Quick decision rule
- Can it be described in 5 lines with a test as the finish line? **Delegate it.**
- Does it need judgement, trade-offs or user context? **Claude.**
- Is it only reading and summarizing? **Gemini** (large context, cheap).
- Is it risky (real data, deploy, migrations)? **Claude does it or reviews every line.**

---

## 5. Guardrails (always)
- Never point agents at the real `biostack.db` or `data/`. Use scratch copies.
- Don't use ports 3000 or 8000 in agent runs.
- Agent output is untrusted until tests pass and the diff is read.
- Deploy only via `scripts/deploy.sh` from `main`, only when the user says so.

## 6. Open items
- [x] Repowise CLI was broken (mixed-version install, ImportError in `doctor_cmd`). Fixed 2026-11-13 with `python3.11 -m pip install --user --force-reinstall --no-deps repowise`; CLI now runs.
- [ ] Repowise MCP: restart Claude Code and confirm it connects (`/mcp`). If not, run `repowise doctor`.
- [ ] Repowise has no model on this index, so `get_answer` is low confidence. Open its `candidate_files`.

Done: `AGENTS.md` (Codex) and `GEMINI.md` (Gemini/Antigravity) now carry the worker rules.

## 7. Ponytail (lazy-minimal coding)
Installed for Gemini/Antigravity at `~/.gemini/config/skills/ponytail` (source: github.com/DietrichGebert/ponytail). It makes the agent climb a ladder: does it need to exist, is it already in the repo, stdlib, native feature, installed dependency, one line, only then minimal code. Levels: `/ponytail lite|full|ultra`, off with "normal mode".
- Worker agents follow it via `AGENTS.md`, so delegated diffs stay small and cheap for Claude to review.
- Not installed on the Claude side; only add it there if Claude's own output starts bloating.
