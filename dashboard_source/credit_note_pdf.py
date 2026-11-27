"""Credit note PDF using uploaded 'Credit Note' layout, private vendor branding.

A credit note is separate from invoice cancellation. All source invoice dates,
periods and credit values come from the verified read-only preview/database.
No financial ledger writes are performed by the PDF renderer.
"""
from datetime import date
from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, Image,
    KeepTogether,
)
from invoice_gst_pdf import _png_for_logo, money_in_words, TemplateVerificationError


def _text(value):
    return escape(str(value or "")).replace("\n", "<br/>")


def render_credit_note_pdf(note, vendor, lines, preview=False):
    if note.get("status") != ("PREVIEW" if preview else "FINALIZED"):
        raise TemplateVerificationError("CREDIT_NOTE_STATUS_NOT_ELIGIBLE")
    if not lines or len(lines) != int(note.get("line_count", 0)):
        raise TemplateVerificationError("CREDIT_NOTE_LINE_COUNT_MISMATCH")
    if vendor.get("verified_at") is None or not vendor.get("verified_by"):
        raise TemplateVerificationError("VENDOR_PROFILE_NOT_APPROVED")
    if vendor.get("legal_name", "").strip().upper() != "MEGHRAJ EXPRESS":
        raise TemplateVerificationError("VENDOR_LEGAL_IDENTITY_INVALID")
    if vendor.get("sac_code") != "996812":
        raise TemplateVerificationError("VENDOR_SAC_MISMATCH")
    for field in ("gstin", "pan", "registered_office", "head_office",
                  "registered_phone", "registered_email", "head_phone",
                  "website", "authorized_signature_label"):
        if not isinstance(vendor.get(field), str) or not vendor[field].strip():
            raise TemplateVerificationError("MISSING_VENDOR_" + field.upper())
    png, source_size = _png_for_logo(vendor)
    actual = sum((Decimal(str(row["credited_taxable"])) for row in lines), Decimal("0.00"))
    taxable = Decimal(str(note["taxable"]))
    cgst = Decimal(str(note["cgst"]))
    sgst = Decimal(str(note["sgst"]))
    gross = Decimal(str(note["total"]))
    if not actual == taxable or taxable + cgst + sgst != gross:
        raise TemplateVerificationError("CREDIT_NOTE_TOTAL_MISMATCH")

    output = BytesIO()
    document = SimpleDocTemplate(
        output, pagesize=A4, leftMargin=37, rightMargin=37, topMargin=31,
        bottomMargin=39, title="Credit Note " + note["credit_note_no"],
        author=vendor["legal_name"],
    )
    available_width = A4[0] - 74
    header_style = ParagraphStyle("c_header", fontName="Helvetica-Bold",
                                   fontSize=15, leading=19, alignment=TA_CENTER)
    small = ParagraphStyle("c_small", fontName="Helvetica",
                           fontSize=8.4, leading=12)
    smbold = ParagraphStyle("c_bold", parent=small, fontName="Helvetica-Bold")
    tiny = ParagraphStyle("c_tiny", fontName="Helvetica",
                          fontSize=7.6, leading=10)
    right = ParagraphStyle("c_right", parent=small, alignment=TA_RIGHT)
    story = []
    logo_width = 160
    logo = Image(BytesIO(png), width=logo_width,
                 height=logo_width * source_size[1] / source_size[0])
    right_panel = Paragraph(
        "<b>" + _text(vendor["legal_name"]) + "</b><br/>"
        "Regd. Off.: " + _text(vendor["registered_office"]) + "<br/>"
        "Phone: " + _text(vendor["registered_phone"]) +
        " | Email: " + _text(vendor["registered_email"]) + "<br/>"
        "Head Off.: " + _text(vendor["head_office"]) + "<br/>"
        "Ph.: " + _text(vendor["head_phone"]) +
        " | Web: " + _text(vendor["website"]),
        tiny,
    )
    header = Table([[logo,right_panel]], colWidths=[170,available_width-170])
    header.setStyle(TableStyle([
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("BOTTOMPADDING",(0,0),(-1,-1),6),
        ("LINEBELOW",(0,0),(-1,-1),1,colors.black),
    ]))
    story.append(header)
    title = Table([[Paragraph("CREDIT NOTE",header_style)]], colWidths=[available_width])
    title.setStyle(TableStyle([
        ("BOX",(0,0),(-1,-1),1,colors.black),
        ("TOPPADDING",(0,0),(-1,-1),5),
        ("BOTTOMPADDING",(0,0),(-1,-1),5),
    ]))
    story += [Spacer(1,8),title,Spacer(1,12)]

    try:
        printed_date = date.fromisoformat(str(note["credit_note_date"])).strftime("%d/%m/%Y")
    except (TypeError,ValueError):
        raise TemplateVerificationError("INVALID_CREDIT_NOTE_DATE") from None
    recipient = (
        "To,<br/><b>" + _text(note["customer_name"]) + "</b><br/>"
        "State Name - West Bengal<br/>State Code - 19<br/>"
        "SBI GSTIN : " + _text(note["customer_gstin"])
    )
    meta = (
        "<b>Credit Note No. :</b> " + _text(note["credit_note_no"]) +
        "<br/><b>Credit Note Date :</b> " + _text(printed_date)
    )
    address = Table([[Paragraph(recipient,small),Paragraph(meta,small)]],
                    colWidths=[available_width*0.55,available_width*0.45])
    address.setStyle(TableStyle([
        ("VALIGN",(0,0),(-1,-1),"TOP"),
        ("BOTTOMPADDING",(0,0),(-1,-1),15),
    ]))
    story.append(address)
    story.append(Paragraph(
        "Statement of Courier Charges deducted/Cancelled by Customer.", smbold))
    story.append(Spacer(1,5))
    story.append(Paragraph("Service Entry Modification Details", smbold))
    story.append(Spacer(1,5))

    widths=[43,62,93,91,available_width-43-62-93-91-93,93]
    cells=[[Paragraph(x,sm bold if False else smbold) for x in
            ("Sl. No.","SAC CODE","INVOICE NO.","INVOICE DATE","MONTH","AMOUNT")]]
    for entry in lines:
        d = date.fromisoformat(str(entry["invoice_date"])).strftime("%d/%m/%Y")
        month = entry["service_month"]
        amt = Decimal(str(entry["credited_taxable"]))
        cells.append([
            Paragraph(str(entry["line_no"]),tiny), Paragraph("996812",tiny),
            Paragraph(_text(entry["invoice_no"]),tiny), Paragraph(d,tiny),
            Paragraph(_text(month),tiny), Paragraph(f"{amt:,.2f}",right),
        ])
    grid = Table(cells,colWidths=widths,repeatRows=1,hAlign="LEFT")
    grid.setStyle(TableStyle([
        ("GRID",(0,0),(-1,-1),0.35,colors.black),
        ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#f1f1f1")),
        ("VALIGN",(0,0),(-1,-1),"TOP"),
        ("LEFTPADDING",(0,0),(-1,-1),4), ("RIGHTPADDING",(0,0),(-1,-1),4),
        ("TOPPADDING",(0,0),(-1,-1),4), ("BOTTOMPADDING",(0,0),(-1,-1),4),
    ]))
    story.append(grid)
    summary_rows=[
        ["Sub Total", f"{taxable:,.2f}"],
        ["Add Central GST @ 9%",f"{cgst:,.2f}"],
        ["Add State GST @ 9%",f"{sgst:,.2f}"],
        ["Grand Total",f"{gross:,.2f}"],
    ]
    summary=Table(summary_rows,colWidths=[145,108],hAlign="RIGHT")
    summary.setStyle(TableStyle([
        ("GRID",(0,0),(-1,-1),0.4,colors.black),
        ("ALIGN",(1,0),(1,-1),"RIGHT"),
        ("FONTNAME",(0,3),(-1,3),"Helvetica-Bold"),
        ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)
    ]))
    story.extend([Spacer(1,12),summary,Spacer(1,9)])
    story.append(Paragraph("<b>Amount in words:</b> "+_text(money_in_words(gross)),small))
    story.append(Paragraph("<b>Reason:</b> "+_text(note["reason"]),small))
    story.append(Spacer(1,8))
    story.append(Paragraph(
        "GST Number - "+_text(vendor["gstin"])+
        " | PAN No. - "+_text(vendor["pan"])+
        " | State - West Bengal | SAC - 996812",small
    ))
    story.append(Spacer(1,12))
    story.append(Paragraph("For, "+_text(vendor["legal_name"]),smbold))
    story.append(Spacer(1,15))
    story.append(Paragraph(_text(vendor["authorized_signature_label"]),small))
    story.append(Paragraph("Enclosed: Statement/Annexure",tiny))
    def footer(canvas,doc):
        canvas.saveState()
        canvas.setFont("Helvetica",7)
        canvas.drawString(37,20,"Meghraj Express | Credit Note | Page "+str(doc.page))
        if preview:
            canvas.setFillColor(colors.HexColor("#a83e3e"))
            canvas.setFont("Helvetica-Bold",9)
            canvas.drawRightString(A4[0]-37,20,"PREVIEW - NOT ISSUED")
        canvas.restoreState()
    document.build(story,onFirstPage=footer,onLaterPages=footer)
    return output.getvalue()
