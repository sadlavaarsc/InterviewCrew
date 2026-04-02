from interview_crew.orchestrator.conflict_arbitrator import ConflictArbitrator


def test_conflict_detected_when_variance_high():
    evaluations = [
        {"dimension": "coding", "score": 0.9},
        {"dimension": "coding", "score": 0.4},
    ]
    result = ConflictArbitrator.detect_conflict(evaluations)
    assert result is not None
    assert "coding" in result


def test_conflict_not_detected_when_variance_low():
    evaluations = [
        {"dimension": "coding", "score": 0.7},
        {"dimension": "coding", "score": 0.8},
    ]
    result = ConflictArbitrator.detect_conflict(evaluations)
    assert result is None


def test_conflict_ignored_for_single_evaluation():
    evaluations = [
        {"dimension": "coding", "score": 0.2},
    ]
    result = ConflictArbitrator.detect_conflict(evaluations)
    assert result is None
