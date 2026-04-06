# BUG-002: MAS Sub-stage max_turns Not Enforced Across Stage Transitions

## Status
- **Status**: 🔍 Open
- **Priority**: Medium
- **Created**: 2026-04-06
- **Reporter**: @sadlavaarsc

## Description
The `max_turns` configuration parameter is not properly enforced when a tech transitions between sub-stages (chat → coding → reflect). Each sub-stage appears to maintain its own independent turn counter, allowing a tech to exceed the configured `max_turns` limit by switching stages.

## Observed Behavior

### Configuration
```yaml
max_turns: 6
total_max_turns: 15
```

### Actual Execution Flow
| Round | Stage | Sub-stage | Turn Counter |
|-------|-------|-----------|--------------|
| 1-2 | chat | chat | 1-2 |
| 3-4 | chat | chat | 3-4 |
| 5-7 | coding | coding | 1-3 (reset!) |
| 8-14 | reflect | reflect | 1-7 (reset again!) |
| 15 | scribe | scribe | - |

**Problem**: tech1 in reflect stage executed 8 rounds (turn: 8 to turn: 15), exceeding the `max_turns=6` limit.

### Evidence
From `data/records/BASELINE_MAS_20260406_15turns.json`:
```json
{
  "current_tech": "tech1",
  "sub_stage": "reflect",
  "turn": 8,   // ← Should have transitioned after turn 6
  // ... continues to turn 15
}
```

## Expected Behavior

**Option A - Cross-stage cumulative** (Recommended):
`max_turns` should count across all sub-stages for each tech. If `max_turns=6`, a tech should execute at most 6 rounds total across chat + coding + reflect combined.

**Option B - Per-sub-stage with limit**:
If designed as per-sub-stage, the total should still be bounded. For example, `max_turns=2` per sub-stage would yield max 6 rounds total.

## Root Cause Hypothesis

The turn counter is likely reset or re-initialized when transitioning between sub-stages:

```python
# Pseudo-code showing the likely bug
def run_sub_stage(sub_stage):
    turn = 0  # ← Reset here!
    while turn < max_turns:  # ← Uses local counter
        turn += 1
        # ... execute round
```

The counter should be maintained at the tech/session level:
```python
# Correct approach
def run_sub_stage(sub_stage, tech_state):
    while tech_state.total_turns < max_turns:
        tech_state.total_turns += 1
        # ... execute round
```

## Related Code

Likely locations to investigate:
- `interview_crew/agents/tech_agent.py` - Tech agent turn management
- `interview_crew/core/interview_crew.py` - Stage/sub-stage orchestration
- `interview_crew/core/state_manager.py` - State tracking across transitions

## Impact

- **MAS Mode**: Techs can consume excessive tokens by cycling through sub-stages
- **Fairness**: One tech may dominate the conversation while others don't get turns
- **Cost**: Unexpected API usage when reflect stage runs longer than configured

## Proposed Fix

1. **Investigate**: Confirm whether `max_turns` is meant to be per-sub-stage or cross-stage
2. **Document**: Clarify the intended behavior in configuration docs
3. **Implement**: If cross-stage, move turn counter to tech-level state; if per-sub-stage, add validation
4. **Test**: Add unit test to verify max_turns enforcement across stage transitions

## References

- Previous related bug: `BUG-001-turn-limit-not-enforced.md`
- Test data: `data/records/BASELINE_MAS_20260406_15turns.json`
- Session ID: `a0cd9051-1ac9-48d5-ab76-243de72bca4f`

---

## Discussion

### 2026-04-06 - Initial Report
Found during MAS baseline testing after fixing BUG-001. The `total_max_turns=15` now works correctly (session terminates at round 15), but `max_turns=6` is not limiting individual tech participation.

### Next Steps
- [ ] Review code to confirm root cause
- [ ] Decide on expected behavior (cross-stage vs per-sub-stage)
- [ ] Implement fix
- [ ] Update tests
