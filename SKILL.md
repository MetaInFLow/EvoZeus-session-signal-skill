---
name: evozeus-session-signal-skill
description: Use when analyzing Codex or agent chat sessions with EvoZeus session signal factors to produce evidence-backed review signals, route reviewed sessions toward the right artifact type, diagnose dissatisfaction, repeated requests, tool failures, task completion, resource usage, or generate/review a High-Quality Session Review Page.
---

# EvoZeus Session Signal Skill

Use this as the Session Signal SKILL for finding AI collaboration history that is worth summarizing, preserving, or turning into reusable SKILL instructions.

Core model:

```text
chat records -> scanner normalization -> factor signals -> ledger read model -> proposed verdict -> artifact route -> presentation
```

`factor.py` is the analysis component for chat records. `FACTOR.xml` declares each factor's inputs, outputs, evidence policy, quality notes, and presentations. This `SKILL.md` only explains how to combine those outputs into a reviewable conclusion.

The method layer is for finding sessions that deserve human review and the right artifact route. It is not a final scoring model, not a raw transcript archive, not a default Skill generator, and not a replacement for human review.

## Operating Rules

1. Use real scanner, runner, ledger, or source session data for current-result requests; do not use fixture or mock factor outputs unless the user explicitly asks for a sample.
2. Separate active gates, diagnostics, and deprecated factors:
   - Active gates: `official.task-completion`, `official.user-input-sentiment`, `official.repeated-request`.
   - Diagnostics: `official.tool-failure-frequency`, `official.session-resource-usage`, `official.key-sentence-trends`.
   - Deprecated candidates: `official.usage-sentence-cloud`.
3. Do not let diagnostics create a high-value conclusion by themselves. Resource count, key-sentence density, long session length, or tool volume explain a case; they do not prove quality.
4. Prefer a conclusion supported by one strong direct gate plus concrete event evidence, or two weaker direct gates that point to the same lesson.
5. Keep coverage explicit. A scanned-but-not-analyzed session has no quality judgment.
6. Store and display compact evidence: `session_id`, `event_id`, source locator, short previews, factor statistics, evidence refs, and derived labels. Do not store raw chat bodies as factor datasets.
7. Treat factor labels as proposed signals. Human review decides whether a case becomes a Case, Factor, Pattern, Habit, Environment Rule, Skill, Rejected Pattern, or remains Open.

## Signal Review Rubric Gate

Use the rubric as a review gate, not as a productized agent score.

| Rating | Use When | Default Route |
| --- | --- | --- |
| `Strong` | At least one direct gate is backed by `E3` evidence or better, the route is clear, and the lesson can change the next session | Candidate Review or accepted artifact proposal |
| `Medium` | Evidence is useful but route, boundary, repeatability, or counterexamples still need work | `Open Case` or `Preserve` |
| `Weak` | Signal is mostly observation, preference, or low-grade evidence | Draft Case only |
| `Blocked` | Evidence locator is missing, privacy is unresolved, or claim/evidence do not match | Fix evidence before public review |

Do not promote a session to Skill just because it is high-signal. Prefer the smallest artifact that changes the next-use path.

## SKILL Candidate Synthesis Method

Start neutral, then apply direct gates. Use diagnostics only to explain or downgrade. These labels are compatibility labels for existing review pages; the final artifact route can be non-Skill.

| Label | Use When |
| --- | --- |
| `success_skill_candidate` | Task is completed and the evidence shows a reusable workflow, acceptance pattern, or implementation process. |
| `problem_skill_candidate` | User shows dissatisfaction, correction, problem report, or scope mismatch that can become a guardrail or interaction rule. |
| `failure_skill_candidate` | The final state is truly `blocked` / `not_completed`, or tool failures clearly caused unrecovered task failure. |
| `repeat_skill_candidate` | User repeats the same unresolved intent after the assistant response; show the first/repeat event pair. |
| `workflow_skill_candidate` | Use sparingly: only when completed work has transferable steps and concrete output evidence. Never assign it from key-sentence/resource volume alone. |
| `review_needed` | Signals are mixed, incomplete, or useful but not strong enough to call high-value. |
| `not_skill_candidate` | Normal completion, low signal, no user correction, no unresolved repeat, no meaningful failure, no transferable process. |

Pruning rules:

- `completed` with no other direct gate usually becomes `not_skill_candidate`.
- `blocked` or `not_completed` must come from explicit final failure/blocking semantics, not interim progress text.
- Recovered tool failures are diagnostics unless they reveal a reusable environment rule.
- Deprecated factors must never create or upgrade a high-value conclusion.
- A `high_quality_session` is a review candidate, not an accepted SKILL artifact.
- A correction or dissatisfaction event should remain searchable, but it should not automatically become high-value without enough context to learn from.
- `workflow_skill_candidate` should be rare; it needs concrete "what changed / what was produced / what pattern transfers" evidence.

## Required Output: High-Quality Session Review Page

When the user asks for results, produce a visual High-Quality Session Review Page rather than a prose-only conclusion.

The page must show:

- `scanned_sessions_total`
- `analysis_scope`
- `analyzed_sessions_total`
- `not_analyzed_sessions_total`
- `high_quality_sessions` and `low_quality_sessions`, counted only inside `analyzed_sessions_total`

If `not_analyzed_sessions_total > 0`, state that those sessions have no quality judgment yet.

every analyzed session must receive one of these labels:

| Page Label | Meaning |
| --- | --- |
| `high_quality_session` | Strong direct gate evidence suggests a reusable workflow, correction, failure, rework, or troubleshooting lesson. |
| `low_quality_session` | Normal, low-signal, insufficiently supported, diagnostic-only, or still requiring review. |

Each high-quality row must let the reviewer verify the judgment. Include:

- human-readable title, raw `session_id`, `source_ref`, and factor result source path
- localized labels for internal tags
- short real snippets for "what the user asked", "what the assistant did", and "which tools/resources were used"
- why this session is currently judged high-quality
- which factor results support that judgment
- `factor_result_reasons`: factor id, signal summary, score/statistics, confidence, evidence refs
- supporting and contradicting factor results
- `human_quality_review`: `unreviewed`, `accepted`, `rejected`, or `needs_more_evidence`

Long review surfaces must use a paginated review queue. Pagination controls must show current page, total pages, and the visible record count.

Use native static components only when useful, especially `ui.native-static.table.v1` for evidence tables. Factor-specific component recommendations belong in each `FACTOR.xml`, not in this file.

## Factor Reading Notes

- `official.user-input-sentiment`: Keep late dissatisfaction, correction, and problem reports visible at event level.
- `official.task-completion`: Treat as closure evidence. A final `task_complete` or verified completion can override earlier failures; later explicit blockers can override earlier progress.
- `official.repeated-request`: Ignore filler such as "ok", "继续", or "开始" unless attached to a stable unresolved request.
- `official.tool-failure-frequency`: Do not count wrapper text as a tool name. Wrapper success is not command success; use structured status, exit code, stderr, and call/result pairing.
- `official.session-resource-usage`: Verified skills must come from explicit fields or clear assistant declaration. Environment variables and placeholders are diagnostics.
- `official.key-sentence-trends`: Interpret by role. User intent and assistant output are different evidence types.
- `official.usage-sentence-cloud`: Use for batch phrase discovery only; filter paths, JSON keys, environment variables, and system fragments.

## Updating Session Signal Factors

When adding or changing a factor:

1. Update `factors/<factor-slug>/FACTOR.xml` first.
2. Keep `factor.py`, `spec.json`, and tests aligned with the contract.
3. Update this `SKILL.md` only if candidate interpretation or required presentation changes.
4. Run contract tests and spec validation.
