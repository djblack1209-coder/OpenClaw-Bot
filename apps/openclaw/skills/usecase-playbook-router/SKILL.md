---
name: usecase-playbook-router
description: Route requests to the best local OpenClaw Bot playbook under the workspace usecases folder.
metadata: {"openclaw":{"emoji":"🧭"}}
---

# Usecase Playbook Router

Use this skill when 严总 asks for a workflow, blueprint, system design, or "how should we run this" question.

## Source of truth

- Playbooks live at `{baseDir}/../../usecases`.
- Always open relevant playbook files before proposing execution.

## Routing steps

1. Classify intent into one of these tracks:
   - Profit operations
   - Research and signal generation
   - Multi-channel command and notifications
   - Self-healing infrastructure
   - Daily briefing and cadence
2. Select one primary playbook and up to two supporting playbooks.
3. Return an execution plan with:
   - Objective
   - Inputs and dependencies
   - Step-by-step workflow
   - Success metrics
   - Abort conditions

## Output rule

- Never give vague advice. Always map output to concrete steps from local playbooks.
- If no playbook fits, explicitly propose creating a new playbook file in `usecases/` and provide a first draft.
