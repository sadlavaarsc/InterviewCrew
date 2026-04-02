from typing import List, Dict, Any, Optional


class ConflictArbitrator:
    @staticmethod
    def detect_conflict(evaluations: List[Dict[str, Any]]) -> Optional[str]:
        """检测不同 Agent 对同一维度的评价差异。"""
        scores_by_dimension: Dict[str, List[float]] = {}
        for ev in evaluations:
            dim = ev.get("dimension")
            score = ev.get("score")
            if dim is not None and score is not None:
                scores_by_dimension.setdefault(dim, []).append(float(score))

        for dim, scores in scores_by_dimension.items():
            if len(scores) >= 2:
                variance = max(scores) - min(scores)
                if variance > 0.4:
                    return f"维度 '{dim}' 的评分方差过大 (variance={variance:.2f})"
        return None
