# Claude Code Delegation: Break Large Audits into Smaller Pieces

## Problem
When delegating a complex audit task (code review + plan update + bug fix in one goal), Claude Code may time out at 600s before completing all work. Even if partial work is saved, the session terminates mid-task.

## Pattern (observed in susieR GPU-ification, 2026-06-17)

Task: "Audit susieR_gpu.py against original C++ IBSS, update plan.md, write test_accuracy.R"

Result: 12 tool calls, timeout at 600s. Partial output saved (plan.md updated, test_accuracy.R written, susieR_gpu.py modified) but audit was incomplete.

## Fix: Split into sequential delegations

**Instead of:**
```
delegate_task(goal="Audit all code + update plan + write test + fix bugs")
```

**Do:**
```
# Step 1: Audit only
delegate_task(goal="Audit susieR_gpu.py against original susieR C++ IBSS algorithm. Return list of bugs found, no code changes.")

# Step 2: Fix bugs + update plan
delegate_task(goal="Fix bugs identified in previous audit. Update plan.md with GPFS-first strategy. Write test_accuracy.R.")
```

## When to split
- Combined tasks with >3 distinct deliverables
- Code audits that require reading original source + comparing multiple files
- Any task that involves both "analysis" and "code generation" phases

## When NOT to split
- Single-deliverable tasks (just write a script, just fix a bug)
- Tasks where the analysis is trivial (known bug, known fix)
