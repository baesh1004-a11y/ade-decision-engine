from __future__ import annotations

import json
from typing import Any


class ReportRenderer:
    """Render ADE reports into JSON and Markdown."""

    def to_json(self, report: dict[str, Any]) -> str:
        return json.dumps(report, ensure_ascii=False, indent=2)

    def to_markdown(self, report: dict[str, Any]) -> str:
        lines = [
            f"# {report.get('title', 'ADE Report')}",
            "",
            f"**Ticker:** {report.get('ticker', 'UNKNOWN')}",
            "",
            f"> {report.get('summary', '')}",
            "",
        ]
        for section in report.get("sections", []):
            lines.append(f"## {section.get('title', '')}")
            lines.append("")
            lines.append(section.get("summary", ""))
            lines.append("")
            for item in section.get("items", []):
                lines.append(f"- {item}")
            lines.append("")
        return "\n".join(lines).strip() + "\n"
