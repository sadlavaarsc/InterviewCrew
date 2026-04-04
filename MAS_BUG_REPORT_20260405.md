# InterviewCrew MAS Bug Report

**Date**: 2026-04-05  
**Reporter**: Kimi Claw (沈清欢)  
**Status**: Confirmed - Early Termination  
**Priority**: High

## Summary

Multi-Agent System (MAS) mode terminates interview prematurely after 5 turns instead of the expected 15 turns when using custom `rounds_config`.

## Environment

- **Version**: commit `950113e`
- **Mode**: `multi_agent`
- **Expected Turns**: 15 (tech1:4 + tech2:4 + sysdes:3 + leader:2 + hr:2)
- **Actual Turns**: 5
- **Session ID**: 9b9ada41-89ac-48ea-9ef4-973db4dd3501 (failed test)

## Steps to Reproduce

1. Start API server: `python -m interview_crew.api`
2. Create MAS session with 15-round config:
```bash
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "multi_agent",
    "total_max_turns": 15,
    "rounds_config": {
      "tech1": {"enabled": true, "max_turns": 4},
      "tech2": {"enabled": true, "max_turns": 4},
      "sysdes": {"enabled": true, "max_turns": 3},
      "leader": {"enabled": true, "max_turns": 2},
      "hr": {"enabled": true, "max_turns": 2}
    }
  }'
```
3. Execute 5 steps with candidate responses
4. Interview terminates at turn 5 with scribe report

## Observed Behavior

**Turn Log** (from `BASELINE_MULTI_DIALOG_20260404.md`):
| Turn | Agent | Expected Stage |
|------|-------|----------------|
| 1 | tech1 | tech1 ✓ |
| 2 | tech2 | tech2 ✓ |
| 3 | sysdes | **tech2** (should be turn 3-6) ✗ |
| 4 | hr | **sysdes** (should be turn 7-9) ✗ |
| 5 | scribe | End (should be turn 15) ✗ |

## Root Cause Analysis

### Suspected Issue: `total_max_turns` Precedence

In `api.py`, the `create_session` function sets:

```python
effective_total_turns = req.total_max_turns if req.total_max_turns != 30 else req.max_turns
config = InterviewConfig(total_max_turns=effective_total_turns)
```

While `InterviewConfig` has correct defaults:
```python
total_max_turns: int = Field(default=30)
rounds: Dict[str, InterviewRoundConfig] = Field(
    default_factory=lambda: {
        "tech1": InterviewRoundConfig(max_turns=4),
        "tech2": InterviewRoundConfig(max_turns=4),
        "sysdes": InterviewRoundConfig(max_turns=3),
        "leader": InterviewRoundConfig(max_turns=2),
        "hr": InterviewRoundConfig(max_turns=2)
    }
)
```

**The problem**: When `rounds_config` is provided in API call, the `Orchestrator` may be checking `total_max_turns` (15) before accumulating individual round `max_turns`.

### Evidence

Looking at the turn progression:
- Turn 1-2 follow correct agent sequence (tech1 → tech2)
- Turn 3 suddenly jumps to sysdes (skipping remaining tech2 turns)
- Turn 4 jumps to hr (skipping remaining rounds)
- Turn 5 ends interview

This suggests the `Orchestrator` is using a **global turn counter** that triggers stage advancement prematurely, rather than checking each round's individual `max_turns`.

### Code Path Analysis

In `orchestrator/engine.py`, the `step()` method likely:
1. Increments global `turn_count`
2. Checks if `turn_count >= total_max_turns` → triggers scribe
3. OR checks if current round's turns exceeded → advances stage

The bug: Stage advancement logic may be using wrong condition (e.g., `turn_count >= current_round.max_turns` instead of `current_round_turn_count >= current_round.max_turns`).

## Expected Behavior

With config:
- tech1: 4 turns (turns 1-4)
- tech2: 4 turns (turns 5-8)
- sysdes: 3 turns (turns 9-11)
- leader: 2 turns (turns 12-13)
- hr: 2 turns (turns 14-15)

Total: exactly 15 turns before scribe.

## Workaround

None identified. The issue appears to be in core orchestrator logic.

## Recommended Fix

1. **Verify** `Orchestrator.step()` uses per-round turn counters
2. **Check** that `total_max_turns` is only used as safety cap, not primary logic
3. **Add** unit test for 15-turn configuration
4. **Add** integration test validating stage progression

## Attachments

- Failed test log: `data/records/BASELINE_MULTI_DIALOG_20260404.md`
- API response shows interview ended at turn 5 with full scribe report

---

*Reported by: Kimi Claw (沈清欢)*  
*Date: 2026-04-05 00:05*
