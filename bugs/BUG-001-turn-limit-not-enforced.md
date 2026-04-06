# Bug Report: MAS Mode Turn Limit Not Enforced

**Date**: 2026-04-06
**Reporter**: Kimi Claw
**Status**: Open
**Priority**: High

## Issue Summary

MAS (Multi-Agent System) mode does not correctly enforce the `total_max_turns` limit, causing interviews to run longer than configured.

## Expected Behavior

When `total_max_turns=15` is configured, the interview should terminate after exactly 15 turns.

## Actual Behavior

The interview ran for **20 turns** despite `total_max_turns=15` being configured.

## Evidence

From test data: `data/records/BASELINE_RAW_MAS_20260405.json`

```json
{
  "total_max_turns": 15,
  "max_turns": 6,
  "turn": 20,  // <-- Exceeded limit by 5 turns
  "status": "finished"
}
```

## Additional Observations

1. **Duplicate turn numbers**: In `competency_history`, turn 13 appears twice, turn 14 appears twice
2. **Transfer queue**: Shows 14 completed rounds (`round_completed: 1` through `14`)
3. **Config mismatch**: There are two turn-related configs:
   - `total_max_turns: 15` (global limit - not enforced)
   - `max_turns: 6` (per-agent limit - possibly being used instead)

## Root Cause Hypothesis

The orchestrator's termination logic may be checking `turn >= max_turns` instead of `turn >= total_max_turns`, causing it to use the per-agent default (6) rather than the global configuration (15).

## Steps to Reproduce

1. Configure MAS mode with `total_max_turns=15` and rounds_config:
   ```json
   {
     "tech1": {"max_turns": 4},
     "tech2": {"max_turns": 4},
     "sysdes": {"max_turns": 3},
     "leader": {"max_turns": 2},
     "hr": {"max_turns": 2}
   }
   ```
2. Run interview
3. Observe that interview continues beyond turn 15

## Impact

- Interviews run longer than expected, consuming unnecessary tokens
- Breaks the contract with users who configure specific turn limits
- Makes A/B testing between MAS and SAS unreliable

## Suggested Fix

Review `orchestrator/engine.py` step() method to ensure it checks against `total_max_turns` (from config) rather than `max_turns` (per-agent default).

## Related Files

- `interview_crew/orchestrator/engine.py` - Step logic and termination check
- `interview_crew/api.py` - Config parsing (lines 238-239)
- `data/records/BASELINE_RAW_MAS_20260405.json` - Evidence data

---
*Generated from analysis of baseline test data*
