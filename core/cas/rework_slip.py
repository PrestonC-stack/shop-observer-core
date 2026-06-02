"""
core/cas/rework_slip.py
Callahan Auto & Diesel — Rework Slip Generator

Produces printable plain text and HTML rework slips from a DVIReview.
No AI. No API calls. Pure output formatting.
"""

from datetime import datetime
from core.cas.dvi_schema import DVIReview, ReviewStatus, FlagSeverity


def generate_text_slip(review: DVIReview) -> str:
    """
    Generate plain text rework slip for printing or display.
    Simple, shop-floor readable format.
    """
    if review.review_status == ReviewStatus.PASS:
        return f"RO {review.ro} — DVI PASSED. No rework required."

    lines = []
    lines.append("=" * 55)
    lines.append(f"DVI REWORK REQUIRED — RO {review.ro}")
    lines.append("=" * 55)
    lines.append(f"Tech:     {review.technician or 'Unknown'}")
    lines.append(f"Vehicle:  {review.vehicle}")
    lines.append(f"Customer: {review.customer}")
    lines.append(f"Time:     {datetime.utcnow().strftime('%m/%d/%Y %I:%M %p')} UTC")
    lines.append("")

    # Separate critical from important
    critical = [f for f in review.flags if f.severity == FlagSeverity.CRITICAL]
    important = [f for f in review.flags if f.severity == FlagSeverity.IMPORTANT]

    if critical:
        lines.append("MUST FIX BEFORE VEHICLE LEAVES RACK:")
        lines.append("-" * 40)
        for i, flag in enumerate(critical, 1):
            lines.append(f"{i}. [{flag.section}] {flag.item_name}")
            lines.append(f"   Issue:  {flag.message}")
            lines.append(f"   Needed: {flag.recommended_action}")
            lines.append("")

    if important:
        lines.append("ALSO REVIEW BEFORE ESTIMATE:")
        lines.append("-" * 40)
        for i, flag in enumerate(important, len(critical) + 1):
            lines.append(f"{i}. [{flag.section}] {flag.item_name}")
            lines.append(f"   Issue:  {flag.message}")
            lines.append(f"   Needed: {flag.recommended_action}")
            lines.append("")

    lines.append("=" * 55)
    lines.append("Return to advisor when corrected.")
    lines.append("=" * 55)

    return "\n".join(lines)


def generate_html_slip(review: DVIReview) -> str:
    """
    Generate printable HTML rework slip.
    Clean, minimal, printer-friendly.
    """
    if review.review_status == ReviewStatus.PASS:
        return f"""
        <html><body style="font-family: monospace; padding: 20px;">
        <h2 style="color: green;">✓ DVI PASSED — RO {review.ro}</h2>
        <p>No rework required. Cleared for estimate.</p>
        </body></html>
        """

    critical = [f for f in review.flags if f.severity == FlagSeverity.CRITICAL]
    important = [f for f in review.flags if f.severity == FlagSeverity.IMPORTANT]

    def flag_rows(flags, start_index=1):
        rows = ""
        for i, flag in enumerate(flags, start_index):
            rows += f"""
            <tr>
                <td style="padding: 8px; font-weight: bold; vertical-align: top;">{i}.</td>
                <td style="padding: 8px; vertical-align: top;">
                    <strong>[{flag.section}] {flag.item_name}</strong><br>
                    <span style="color: #555;">Issue: {flag.message}</span><br>
                    <span style="color: #c00;"><strong>Needed: {flag.recommended_action}</strong></span>
                </td>
            </tr>
            """
        return rows

    critical_section = ""
    if critical:
        critical_section = f"""
        <h3 style="color: #c00; border-bottom: 2px solid #c00; padding-bottom: 4px;">
            ⚠ MUST FIX BEFORE VEHICLE LEAVES RACK
        </h3>
        <table style="width: 100%; border-collapse: collapse;">
            {flag_rows(critical, 1)}
        </table>
        """

    important_section = ""
    if important:
        important_section = f"""
        <h3 style="color: #e67e00; border-bottom: 1px solid #e67e00; padding-bottom: 4px; margin-top: 20px;">
            ◆ ALSO REVIEW BEFORE ESTIMATE
        </h3>
        <table style="width: 100%; border-collapse: collapse;">
            {flag_rows(important, len(critical) + 1)}
        </table>
        """

    timestamp = datetime.utcnow().strftime("%m/%d/%Y %I:%M %p")

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>DVI Rework Slip — RO {review.ro}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            font-size: 13px;
            padding: 24px;
            max-width: 700px;
            margin: 0 auto;
            color: #111;
        }}
        .header {{
            border: 2px solid #c00;
            padding: 12px 16px;
            margin-bottom: 20px;
        }}
        .header h1 {{
            margin: 0;
            font-size: 18px;
            color: #c00;
        }}
        .meta {{
            margin-top: 8px;
            color: #444;
            font-size: 12px;
        }}
        .footer {{
            margin-top: 24px;
            border-top: 2px solid #111;
            padding-top: 12px;
            font-weight: bold;
            font-size: 13px;
        }}
        @media print {{
            body {{ padding: 12px; }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>DVI REWORK REQUIRED — RO {review.ro}</h1>
        <div class="meta">
            Tech: <strong>{review.technician or "Unknown"}</strong> &nbsp;|&nbsp;
            Vehicle: <strong>{review.vehicle}</strong> &nbsp;|&nbsp;
            Customer: <strong>{review.customer}</strong><br>
            Generated: {timestamp} UTC
        </div>
    </div>

    {critical_section}
    {important_section}

    <div class="footer">
        Return to advisor when corrected. Do not move vehicle from rack until items are resolved.
    </div>

    <script>
        // Auto-print when opened directly
        if (window.location.search.includes('autoprint=1')) {{
            window.print();
        }}
    </script>
</body>
</html>"""


def save_slip(review: DVIReview, output_dir: str = "state/dvi_reviews") -> str:
    """Save HTML rework slip to file. Returns file path."""
    import os
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"rework_slip_{review.ro}.html")
    with open(path, "w") as f:
        f.write(generate_html_slip(review))
    return path
