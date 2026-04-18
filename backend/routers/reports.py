"""
Reports Router: PDF generation with reportlab.
"""
import io
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Request, Depends, Query
from fastapi.responses import StreamingResponse

from routers.auth import get_current_user
from services.ml_service import get_risk_summary

router = APIRouter()


@router.get("/download/{patient_id}")
async def download_report(
    request: Request,
    patient_id: str,
    days: int = Query(30, ge=1, le=365),
    current_user: dict = Depends(get_current_user),
):
    from bson import ObjectId
    db = request.app.state.db

    if current_user["role"] == "patient" and current_user["sub"] != patient_id:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        patient = await db.users.find_one({"_id": ObjectId(patient_id)})
    except Exception:
        raise HTTPException(status_code=404, detail="Patient not found")
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    cutoff       = datetime.utcnow() - timedelta(days=days)
    measurements = []
    async for m in db.measurements.find(
        {"patient_id": patient_id, "timestamp": {"$gte": cutoff}},
        sort=[("timestamp", -1)],
    ):
        measurements.append(m)

    pdf_bytes = _generate_pdf(patient, measurements, days)
    safe_name = patient["name"].replace(" ", "_")
    filename  = f"IOP_Report_{safe_name}_{datetime.now().strftime('%Y%m%d')}.pdf"

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def _generate_pdf(patient: dict, measurements: list, days: int) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.colors import HexColor, white
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    )

    buffer = io.BytesIO()
    doc    = SimpleDocTemplate(buffer, pagesize=letter,
                               topMargin=0.5*inch, bottomMargin=0.5*inch,
                               leftMargin=0.75*inch, rightMargin=0.75*inch)

    dark_green  = HexColor("#14532d")
    light_green = HexColor("#f0fdf4")
    red_color   = HexColor("#dc2626")
    yellow      = HexColor("#d97706")
    green_ok    = HexColor("#16a34a")
    gray        = HexColor("#6b7280")
    light_gray  = HexColor("#f9fafb")

    styles = getSampleStyleSheet()
    story  = []

    # Header
    header = Table([[Paragraph(
        "<para alignment='center'>"
        "<font size='18' color='#ffffff'><b>GlaucoMonitor — IOP Report</b></font><br/>"
        f"<font size='10' color='#bbf7d0'>Generated: {datetime.now().strftime('%B %d, %Y %H:%M UTC')}</font>"
        "</para>",
        styles["Normal"]
    )]], colWidths=[7*inch])
    header.setStyle(TableStyle([
        ("BACKGROUND", (0,0),(-1,-1), dark_green),
        ("PADDING",    (0,0),(-1,-1), 16),
    ]))
    story += [header, Spacer(1, 0.2*inch)]

    # Patient info
    section = ParagraphStyle("S", parent=styles["Heading2"],
                              fontSize=13, textColor=dark_green, spaceBefore=12, spaceAfter=6)
    story.append(Paragraph("Patient Information", section))

    pt_data = [
        ["Name:",   patient.get("name","–"),             "Age:",    str(patient.get("age","–"))],
        ["Email:",  patient.get("email","–"),             "Cornea:", f"{patient.get('cornea_thickness','–')} μm"],
        ["Period:", f"Last {days} days",                  "Total:",  f"{len(measurements)} readings"],
    ]
    pt_table = Table(pt_data, colWidths=[1.2*inch, 2.3*inch, 1.2*inch, 2.3*inch])
    pt_table.setStyle(TableStyle([
        ("FONTSIZE",  (0,0),(-1,-1), 10),
        ("TEXTCOLOR", (0,0),(0,-1),  gray),
        ("TEXTCOLOR", (2,0),(2,-1),  gray),
        ("FONTNAME",  (0,0),(0,-1),  "Helvetica-Bold"),
        ("FONTNAME",  (2,0),(2,-1),  "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0,0),(-1,-1), [white, light_gray]),
        ("PADDING",   (0,0),(-1,-1), 6),
    ]))
    story += [pt_table, Spacer(1, 0.1*inch)]

    # Summary
    if measurements:
        summary = get_risk_summary(measurements)
        story.append(Paragraph("Summary Statistics", section))

        stats_data = [
            ["Metric", "Value"],
            ["Average IOP",    f"{summary['avg_iop']} mmHg"],
            ["Maximum IOP",    f"{summary['max_iop']} mmHg"],
            ["Minimum IOP",    f"{summary['min_iop']} mmHg"],
            ["HIGH Risk",      str(summary["risk_distribution"].get("HIGH",0))],
            ["MEDIUM Risk",    str(summary["risk_distribution"].get("MEDIUM",0))],
            ["LOW Risk",       str(summary["risk_distribution"].get("LOW",0))],
        ]
        st = Table(stats_data, colWidths=[3.5*inch, 3.5*inch])
        st.setStyle(TableStyle([
            ("BACKGROUND", (0,0),(-1,0), dark_green),
            ("TEXTCOLOR",  (0,0),(-1,0), white),
            ("FONTNAME",   (0,0),(-1,0), "Helvetica-Bold"),
            ("FONTSIZE",   (0,0),(-1,-1), 10),
            ("ROWBACKGROUNDS", (0,1),(-1,-1), [white, light_gray]),
            ("GRID",       (0,0),(-1,-1), 0.5, HexColor("#e5e7eb")),
            ("PADDING",    (0,0),(-1,-1), 8),
            ("ALIGN",      (1,0),(1,-1), "CENTER"),
        ]))
        story += [st, Spacer(1, 0.1*inch)]

    # History table
    if measurements:
        story.append(Paragraph(f"Measurement History (last {min(len(measurements),50)} entries)", section))

        rows = [["Date & Time", "IOP (mmHg)", "Eye", "Risk Level", "Probability"]]
        for m in measurements[:50]:
            ts   = m["timestamp"].strftime("%m/%d/%Y %H:%M") if isinstance(m["timestamp"], datetime) else str(m["timestamp"])[:16]
            rows.append([ts, str(m["iop_value"]), m.get("eye","R"), m.get("risk_level","–"), f"{m.get('risk_probability',0):.0%}"])

        ht = Table(rows, colWidths=[1.8*inch,1.3*inch,0.8*inch,1.4*inch,1.4*inch])
        cmds = [
            ("BACKGROUND", (0,0),(-1,0), dark_green),
            ("TEXTCOLOR",  (0,0),(-1,0), white),
            ("FONTNAME",   (0,0),(-1,0), "Helvetica-Bold"),
            ("FONTSIZE",   (0,0),(-1,-1), 9),
            ("ROWBACKGROUNDS", (0,1),(-1,-1), [white, light_gray]),
            ("GRID",       (0,0),(-1,-1), 0.5, HexColor("#e5e7eb")),
            ("PADDING",    (0,0),(-1,-1), 5),
            ("ALIGN",      (1,0),(-1,-1), "CENTER"),
        ]
        for i, m in enumerate(measurements[:50], 1):
            risk = m.get("risk_level","LOW")
            col  = red_color if risk=="HIGH" else (yellow if risk=="MEDIUM" else green_ok)
            cmds += [("TEXTCOLOR",(3,i),(3,i),col), ("FONTNAME",(3,i),(3,i),"Helvetica-Bold")]
        ht.setStyle(TableStyle(cmds))
        story.append(ht)

    # Footer
    story += [Spacer(1,0.3*inch), HRFlowable(width="100%", thickness=0.5, color=gray), Spacer(1,0.1*inch)]
    disc = ParagraphStyle("D", parent=styles["Normal"], fontSize=8, textColor=gray)
    story.append(Paragraph(
        "For research and educational purposes only. Not a certified medical device. "
        "Consult a qualified ophthalmologist for diagnosis and treatment.",
        disc,
    ))

    doc.build(story)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf
