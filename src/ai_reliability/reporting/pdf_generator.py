"""Professional PDF report generator for the AI Reliability Checker."""

import io
from datetime import datetime, timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from ai_reliability.investigation.models import InvestigationReport


def generate_investigation_pdf(report: InvestigationReport | dict) -> bytes:
    """Generate a publication-quality PDF report from an InvestigationReport using Burgundy & Peach palette."""
    if isinstance(report, dict):
        report_data = report
    else:
        report_data = report.model_dump()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=40,
        rightMargin=40,
        topMargin=40,
        bottomMargin=40,
    )

    styles = getSampleStyleSheet()

    # Palette Constants:
    # Deep Burgundy: #59171B
    # Warm Peach: #FED7B8
    # Rose/Wine: #8B263E, #A84252
    # Off-white / Cream: #FFFBF8, #FDF4ED
    
    # Custom Typography Styles
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#59171B"),
    )
    
    subtitle_style = ParagraphStyle(
        "ReportSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#7A3E45"),
    )
    
    h2_style = ParagraphStyle(
        "ReportH2",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        textColor=colors.HexColor("#3D0E12"),
        spaceBefore=12,
        spaceAfter=6,
    )

    body_style = ParagraphStyle(
        "ReportBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#2D1518"),
    )

    bold_label_style = ParagraphStyle(
        "BoldLabel",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#3D0E12"),
    )

    quote_style = ParagraphStyle(
        "QuoteText",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#5C2B30"),
    )

    link_style = ParagraphStyle(
        "LinkText",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#8B263E"),
    )

    story = []

    # 1. Header Banner
    story.append(Paragraph("VERITY AI &mdash; AI Reliability Analysis", title_style))
    story.append(Paragraph("<i>See what AI can actually prove.</i>", quote_style))
    story.append(Spacer(1, 4))
    created_at = report_data.get("created_at") or datetime.now(timezone.utc).isoformat()
    model_name = report_data.get("model") or "Unspecified Model"
    rep_id = report_data.get("id", "N/A")[:8]
    
    meta_text = f"Analysis Date: <strong>{created_at[:10]}</strong> | Target Model: <strong>{model_name}</strong> | Verification ID: <strong>{rep_id}</strong>"
    story.append(Paragraph(meta_text, subtitle_style))
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#59171B"), spaceAfter=12))

    # 2. Inquiry & Response Summary Box
    q_text = report_data.get("question", "").replace("<", "&lt;").replace(">", "&gt;")
    a_text = report_data.get("answer", "").replace("<", "&lt;").replace(">", "&gt;")
    
    inquiry_data = [
        [
            Paragraph("<strong>Original Question:</strong>", bold_label_style),
            Paragraph(q_text, body_style),
        ],
        [
            Paragraph("<strong>AI's Response:</strong>", bold_label_style),
            Paragraph(a_text, body_style),
        ],
    ]
    
    inquiry_table = Table(inquiry_data, colWidths=[110, 420])
    inquiry_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FDF7F3")),
            ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#EBD5C9")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#EBD5C9")),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ])
    )
    story.append(inquiry_table)
    story.append(Spacer(1, 14))

    # 3. Assessment & What We Found
    story.append(Paragraph("Executive Assessment & Findings", h2_style))
    overall_assessment = report_data.get("overall_assessment", "").replace("<", "&lt;").replace(">", "&gt;")
    summary_text = report_data.get("summary", "").replace("<", "&lt;").replace(">", "&gt;")
    
    findings_data = [
        [
            Paragraph(f"<strong>Status:</strong> {overall_assessment}", bold_label_style),
        ],
        [
            Paragraph(summary_text, body_style),
        ],
    ]
    findings_table = Table(findings_data, colWidths=[530])
    findings_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FAF0EA")),
            ("LINELEFT", (0, 0), (-1, -1), 3.5, colors.HexColor("#59171B")),
            ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#E2C3B5")),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ])
    )
    story.append(findings_table)
    story.append(Spacer(1, 14))

    # 4. Claim-by-Claim Verification
    story.append(Paragraph("Claim-by-Claim Evidence Verification", h2_style))
    claims = report_data.get("claims", [])
    
    if not claims:
        story.append(Paragraph("No individual claim propositions were extracted.", body_style))
    else:
        for idx, claim in enumerate(claims):
            c_text = claim.get("claim_text", "").replace("<", "&lt;").replace(">", "&gt;")
            c_status = claim.get("status", "unable_to_verify")
            c_label = claim.get("status_label") or c_status.replace("_", " ").title()
            c_why = claim.get("explanation", "").replace("<", "&lt;").replace(">", "&gt;")
            c_excerpt = (claim.get("evidence_excerpt") or "").replace("<", "&lt;").replace(">", "&gt;")
            c_src_title = claim.get("source_title") or claim.get("source_domain") or ""
            c_src_url = claim.get("source_url") or ""

            # Badge styling
            if c_status == "supported":
                badge_bg = colors.HexColor("#DCFCE7")
                badge_fg = colors.HexColor("#166534")
                border_col = colors.HexColor("#22C55E")
            elif c_status == "contradicted":
                badge_bg = colors.HexColor("#FFE4E6")
                badge_fg = colors.HexColor("#9F1239")
                border_col = colors.HexColor("#E11D48")
            elif c_status == "partially_supported":
                badge_bg = colors.HexColor("#FEF3C7")
                badge_fg = colors.HexColor("#92400E")
                border_col = colors.HexColor("#F59E0B")
            else:
                badge_bg = colors.HexColor("#FED7B8")
                badge_fg = colors.HexColor("#59171B")
                border_col = colors.HexColor("#8B263E")

            badge_p = Paragraph(
                f"<font color='{badge_fg.hexval()}'><strong>[{c_label.upper()}]</strong></font>",
                bold_label_style,
            )

            claim_rows = [
                [
                    Paragraph(f"<strong>Claim {idx+1}:</strong> \"{c_text}\"", bold_label_style),
                    badge_p,
                ],
                [
                    Paragraph(f"<strong>Finding:</strong> {c_why}", body_style),
                    Paragraph("", body_style),
                ],
            ]

            if c_excerpt:
                claim_rows.append([
                    Paragraph(f"<strong>Evidence:</strong> <i>\"{c_excerpt}\"</i>", quote_style),
                    Paragraph("", body_style),
                ])

            if c_src_url:
                safe_url = c_src_url.replace("&", "&amp;")
                claim_rows.append([
                    Paragraph(f"<strong>Source:</strong> <a href='{safe_url}'><u>{c_src_title or safe_url}</u></a>", link_style),
                    Paragraph("", body_style),
                ])

            claim_table = Table(claim_rows, colWidths=[410, 120])
            claim_table.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFFFFF")),
                    ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#EBD5C9")),
                    ("LINELEFT", (0, 0), (0, -1), 3, border_col),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("SPAN", (0, 1), (1, 1)),
                ] + ([("SPAN", (0, 2), (1, 2))] if len(claim_rows) > 2 else [])
                  + ([("SPAN", (0, 3), (1, 3))] if len(claim_rows) > 3 else [])
                )
            )
            story.append(KeepTogether([claim_table, Spacer(1, 8)]))

    story.append(Spacer(1, 10))

    # 5. Sources Used
    story.append(Paragraph("Authoritative Sources Consulted", h2_style))
    sources_used = report_data.get("sources_used", [])
    
    if not sources_used:
        story.append(Paragraph("No external sources were retrieved for this analysis.", body_style))
    else:
        source_rows = [[
            Paragraph("<strong>Source Title & Reference</strong>", bold_label_style),
            Paragraph("<strong>Type</strong>", bold_label_style),
            Paragraph("<strong>Key Evidence Snippet</strong>", bold_label_style),
        ]]
        
        for s in sources_used:
            s_title = s.get("title", "").replace("<", "&lt;").replace(">", "&gt;")
            s_url = s.get("url", "")
            s_domain = s.get("domain", "")
            s_type = s.get("source_type", "general_web").replace("_", " ").title()
            s_snippet = s.get("snippet", "").replace("<", "&lt;").replace(">", "&gt;")[:180] + "..."

            safe_url = s_url.replace("&", "&amp;")
            title_p = Paragraph(f"<a href='{safe_url}'><strong>{s_title}</strong></a><br/><font color='#7A3E45' size='7'>{s_domain}</font>", body_style)
            type_p = Paragraph(f"<font size='8'>{s_type}</font>", body_style)
            snip_p = Paragraph(f"<font size='8' color='#5C2B30'>{s_snippet}</font>", body_style)
            source_rows.append([title_p, type_p, snip_p])

        sources_table = Table(source_rows, colWidths=[180, 80, 270])
        sources_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#FAF0EA")),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#E2C3B5")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#EBD5C9")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ])
        )
        story.append(KeepTogether([sources_table]))

    story.append(Spacer(1, 14))

    # 6. Important Limitations
    story.append(Paragraph("Important Limitations & Boundaries", h2_style))
    limitations = [
        "This reliability investigation reflects evidence accessible at the time of retrieval and does not constitute absolute or infallible truth.",
        "Absence of corroborating evidence indicates an unverified statement rather than guaranteed falsehood.",
        "External claims were evaluated using deterministic heuristics, entity alignment, and available authoritative documentation without fabricated confidence percentages.",
    ]
    for lim in limitations:
        story.append(Paragraph(f"• {lim}", quote_style))
        story.append(Spacer(1, 3))

    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#E2C3B5"), spaceAfter=8))
    story.append(
        Paragraph(
            "<font size='7.5' color='#8A525A'>AI Reliability Platform — Evidence-Based Verification — Confidential & Protected. No API credentials or private tokens are contained in this document.</font>",
            body_style,
        )
    )

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
