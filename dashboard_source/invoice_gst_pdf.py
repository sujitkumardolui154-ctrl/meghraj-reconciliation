"""Meghraj Express invoice PDF renderer using *private* exact logo/profile bytes.

This module contains no customer, banking or legal data. The caller must read
a verified vendor profile from private PostgreSQL; do not commit those values.
The supplied PDF was an earlier layout preview, not a certified native XLSX.
"""
from decimal import Decimal
from io import BytesIO
import re
from xml.sax.saxutils import escape

from PIL import Image as PillowImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, PageBreak, KeepTogether,
)


class TemplateVerificationError(ValueError):
    pass


def _require(profile, key):
    value = profile.get(key)
    if not isinstance(value, str) or not value.strip():
        raise TemplateVerificationError("MISSING_VENDOR_" + key.upper())
    return value


def _money(value):
    amount = Decimal(str(value))
    if not amount.is_finite() or amount < 0 or amount != amount.quantize(Decimal("0.01")):
        raise TemplateVerificationError("INVALID_PDF_AMOUNT")
    return amount


ONES = ("Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven",
        "Eight", "Nine", "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen",
        "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen")
TENS = ("", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty",
        "Seventy", "Eighty", "Ninety")


def _under_thousand(num):
    if num < 20:
        return ONES[num]
    if num < 100:
        return TENS[num // 10] + ((" " + ONES[num % 10]) if num % 10 else "")
    return ONES[num // 100] + " Hundred" + (
        (" " + _under_thousand(num % 100)) if num % 100 else ""
    )


def money_in_words(amount):
    number = _money(amount)
    rupees = int(number)
    paisas = int((number - rupees) * 100)
    if rupees >= 10_000_000_000:
        raise TemplateVerificationError("PDF_AMOUNT_WORDS_OVER_LIMIT")
    remaining = rupees
    chunks = []
    for factor, word in ((10_000_000, "Crore"), (100_000, "Lakh"), (1_000, "Thousand")):
        count, remaining = divmod(remaining, factor)
        if count:
            chunks.append(_under_thousand(count) + " " + word)
    if remaining or not chunks:
        chunks.append(_under_thousand(remaining))
    return ("Rupees " + " ".join(chunks)
            + " and " + _under_thousand(paisas) + " Paisas Only")


def _png_for_logo(profile):
    if profile.get("exact_logo_verified") is not True:
        raise TemplateVerificationError("LOGO_NOT_APPROVED")
    data = profile.get("logo_image")
    if not isinstance(data, bytes) or not data:
        raise TemplateVerificationError("LOGO_IMAGE_REQUIRED")
    try:
        with PillowImage.open(BytesIO(data)) as source:
            if source.width < 100 or source.height < 30:
                raise TemplateVerificationError("LOGO_TOO_SMALL")
            source.load()
            rgb = source.convert("RGBA")
            out = BytesIO()
            rgb.save(out, format="PNG")
            return out.getvalue(), source.size
    except TemplateVerificationError:
        raise
    except Exception:
        raise TemplateVerificationError("LOGO_INVALID_IMAGE") from None


def _plain(value):
    return escape(str(value or "")).replace("\n", "<br/>")


def render_invoice_pdf(invoice, vendor_profile, lines):
    """Return printable invoice+annexure PDF bytes; does not mutate DB.

    invoice is a finalized, verified immutable record with master_snapshot.
    """
    if invoice.get("status") != "FINALIZED" or invoice.get("verification_flags"):
        raise TemplateVerificationError("INVOICE_NOT_VERIFIED_FINALIZED")
    if vendor_profile.get("verified_at") is None or not _require(vendor_profile, "verified_by"):
        raise TemplateVerificationError("VENDOR_PROFILE_NOT_APPROVED")
    logo_png, logo_size = _png_for_logo(vendor_profile)
    legal = {
        key: _require(vendor_profile, key)
        for key in ("legal_name", "declaration_text", "bank_instructions",
                    "pan", "gstin", "vendor_id", "service_type", "sac_code",
                    "footer_text", "authorized_signature_label")
    }
    if legal["legal_name"].upper() != "MEGHRAJ EXPRESS":
        raise TemplateVerificationError("VENDOR_IDENTITY_UNVERIFIED")
    expected = _money(invoice["taxable"])
    actual = sum((_money(line["amount"]) for line in lines), Decimal("0.00"))
    if expected != actual or len(lines) != int(invoice["shipment_count"]):
        raise TemplateVerificationError("ANNEXURE_TOTAL_OR_COUNT_MISMATCH")
    if expected + _money(invoice["cgst"]) + _money(invoice["sgst"]) != _money(invoice["total"]):
        raise TemplateVerificationError("INVOICE_GROSS_MISMATCH")

    snapshot = invoice.get("master_snapshot")
    if not isinstance(snapshot, dict):
        raise TemplateVerificationError("VERIFIED_CUSTOMER_SNAPSHOT_REQUIRED")
    customer_title = snapshot.get("recipient_title")
    customer_address = snapshot.get("customer_address")
    if not isinstance(customer_title, str) or not customer_title.strip() or not customer_address:
        raise TemplateVerificationError("CUSTOMER_ADDRESS_MISSING")

    styles = {
        "h": ParagraphStyle("inv_h", fontName="Helvetica-Bold", fontSize=16,
                            leading=19, alignment=TA_CENTER),
        "p": ParagraphStyle("inv_p", fontName="Helvetica", fontSize=8.1,
                            leading=11.7, spaceAfter=2),
        "bold": ParagraphStyle("inv_b", fontName="Helvetica-Bold", fontSize=8.1,
                               leading=11.7),
        "tiny": ParagraphStyle("inv_t", fontName="Helvetica", fontSize=7.0,
                               leading=9.0),
        "right": ParagraphStyle("inv_right", fontName="Helvetica",
                                fontSize=8.1, leading=12, alignment=TA_RIGHT),
    }
    stream = BytesIO()
    doc = SimpleDocTemplate(
        stream, pagesize=A4, leftMargin=43, rightMargin=43,
        topMargin=26, bottomMargin=27, title="Tax Invoice " + invoice["invoice_no"],
        author=legal["legal_name"],
    )
    story = []
    ratio = logo_size[0] / logo_size[1]
    display_width = min(210, ratio * 70)
    story.append(Image(BytesIO(logo_png), width=display_width,
                       height=display_width / ratio, hAlign="LEFT"))
    story.append(Spacer(1, 9))
    story.append(Paragraph("TAX INVOICE", styles["h"]))
    story.append(Spacer(1, 9))

    date_text = lambda v: v.strftime("%d/%m/%Y") if hasattr(v, "strftime") else (
        str(v)[8:10] + "/" + str(v)[5:7] + "/" + str(v)[:4])
    client_lines = ("To,\n" + customer_title + "\nState Bank of India\n"
                    + invoice["client_name"] + "\n" + str(customer_address))
    right_lines = (
        "Invoice No " + invoice["invoice_no"] + "\n"
        + "From Date " + date_text(invoice["service_from"]) + "\n"
        + "To Date " + date_text(invoice["service_to"]) + "\n"
        + "Invoice Date " + date_text(invoice["invoice_date"])
    )
    detail = Table([
        [Paragraph(_plain(client_lines), styles["p"]),
         Paragraph(_plain(right_lines), styles["right"])]
    ], colWidths=[343,166])
    detail.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING", (0,0), (-1,-1), 0),
        ("RIGHTPADDING", (0,0), (-1,-1), 0),
        ("TOPPADDING", (0,0), (-1,-1), 0),
        ("BOTTOMPADDING", (0,0), (-1,-1), 0),
    ]))
    story.append(detail)
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "State Name- West Bengal<br/>State Code- 19<br/>SBI GSTIN : "
        + _plain(invoice["gstin"]), styles["p"]))
    story.append(Spacer(1, 12))
    story.append(Paragraph(
        "Statement of Service Rendered for the Month of " +
        _plain(invoice["service_month"]), styles["p"]))
    story.append(Spacer(1, 11))
    service_short = invoice["service_month_key"][5:7] + "-" + invoice["service_month_key"][:4]
    month_name = invoice["service_month"].split()[0][:3]
    service_short = month_name + "-" + invoice["service_month_key"][2:4]
    tax_table = Table([
        ["Invoice Month","Bill Ammount","CGST 9 %","SGST 9%","Total",
         "Total With Round Off"],
        [service_short,
         f"{expected:,.2f}", f"{_money(invoice['cgst']):,.2f}",
         f"{_money(invoice['sgst']):,.2f}",
         f"{_money(invoice['total']):,.2f}", ""]
    ], colWidths=[84,90,74,74,90,97], rowHeights=[29,29])
    tax_table.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#E8EFF6")),
        ("GRID",(0,0),(-1,-1),0.4,colors.HexColor("#91A6BD")),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("LEFTPADDING",(0,0),(-1,-1),6),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
        ("FONTSIZE",(0,0),(-1,-1),7.6),
    ]))
    story.append(tax_table)
    story.append(Spacer(1, 10))
    story.append(Paragraph(_plain(money_in_words(invoice["total"])),styles["p"]))
    story.append(Spacer(1, 9))
    story.append(Paragraph(_plain(legal["declaration_text"]),styles["p"]))
    story.append(Spacer(1, 8))
    story.append(Paragraph("Enclosed: Statement/Annexure",styles["p"]))
    story.append(Paragraph(_plain(legal["bank_instructions"]), styles["p"]))
    story.append(Paragraph(
        "2. PAN CARD No : " + _plain(legal["pan"]) +
        " &nbsp;&nbsp; 3. GST No: " + _plain(legal["gstin"]), styles["p"]))
    story.append(Paragraph(
        "4. Service Type - " + _plain(legal["service_type"]) +
        " &nbsp;&nbsp; 5. SAC / HSN Code : " + _plain(legal["sac_code"]),
        styles["p"]))
    story.append(Paragraph("6.VENDOR ID- " + _plain(legal["vendor_id"]),styles["p"]))
    story.append(Paragraph(_plain(legal["footer_text"]), styles["p"]))
    story.append(Spacer(1, 10))
    story.append(Paragraph("For, " + _plain(legal["legal_name"]), styles["right"]))
    story.append(Spacer(1, 16))
    story.append(Paragraph(_plain(legal["authorized_signature_label"]),styles["right"]))

    story.append(PageBreak())
    story.append(Paragraph(
        "Annexure/Statement of Invoice No. " + _plain(invoice["invoice_no"]), styles["h"]
    ))
    story.append(Spacer(1, 12))
    header = ["Dispatch Date", "LR No", "Packet Ref No", "Consignee", "Weight", "Amount"]
    shipment_rows = [header]
    for line in lines:
        shipment_rows.append([
            date_text(line["dispatch_date"]), str(line["lr_no"]),
            str(line.get("packet_ref_no") or ""), str(line["consignee"]),
            f"{Decimal(str(line['weight_kg'])):.3f}", f"{_money(line['amount']):.2f}",
        ])
    shipment_rows.append(["","","","Bill Total","",f"{expected:.2f}"])
    annex = Table(shipment_rows, repeatRows=1,
                  colWidths=[73,90,80,171,50,45], hAlign="CENTER")
    annex.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#E8EFF6")),
        ("GRID",(0,0),(-1,-1),0.25,colors.HexColor("#ADB8C5")),
        ("FONTSIZE",(0,0),(-1,-1),6.5),
        ("LEADING",(0,0),(-1,-1),8),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("TOPPADDING",(0,0),(-1,-1),3.4),
        ("BOTTOMPADDING",(0,0),(-1,-1),3.4),
        ("LEFTPADDING",(0,0),(-1,-1),5),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
        ("FONTNAME",(3,-1),(-1,-1),"Helvetica-Bold"),
    ]))
    story.append(annex)

    def footer(canvas, document):
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.grey)
        canvas.drawString(43, 15, "Meghraj Express | Original logo and approved private vendor details")
        canvas.drawRightString(A4[0]-43,15,"Page " + str(document.page))
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return stream.getvalue()
