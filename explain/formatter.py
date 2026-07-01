from __future__ import annotations

import json
from typing import Any


class ExplanationFormatter:
    """Format explanation reports for downstream consumers."""

    def to_json(self, report: dict[str, Any]) -> str:
        return json.dumps(report, ensure_ascii=False, indent=2)

    def to_markdown(self, report: dict[str, Any]) -> str:
        lines = [
            f"# ADE 설명 리포트: {report.get('ticker', 'UNKNOWN')}",
            "",
            f"- 최종 판단: **{report.get('decision', 'UNKNOWN')}**",
            f"- 신뢰도: **{float(report.get('confidence', 0.0)):.2%}**",
            "",
            f"> {report.get('summary', '')}",
            "",
            "## 근거",
        ]
        for item in report.get("evidence", []):
            lines.append(f"- **{item.get('category')} / {item.get('label')}**: {item.get('value')} ({item.get('impact')})")
        if report.get("warnings"):
            lines.extend(["", "## 주의사항"])
            for warning in report["warnings"]:
                lines.append(f"- {warning}")
        return "\n".join(lines)
