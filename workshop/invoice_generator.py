import io
import xml.sax.saxutils as saxutils
from decimal import Decimal, ROUND_HALF_UP
from django.conf import settings
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch


def _esc(val):
    """Safely escape user input for ReportLab HTML-like markup."""
    return saxutils.escape(str(val)) if val is not None else ""


def generate_pdf_invoice(booking, payment=None):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    PRIMARY_COLOR = colors.HexColor("#FF4D30")
    DARK_COLOR = colors.HexColor("#0F172A")
    TEXT_MUTED = colors.HexColor("#64748B")
    BG_LIGHT = colors.HexColor("#F8FAFC")
    BORDER_COLOR = colors.HexColor("#E2E8F0")

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=22,
        leading=26,
        textColor=DARK_COLOR
    )

    subtitle_style = ParagraphStyle(
        'DocSubTitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=TEXT_MUTED
    )

    section_heading = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading3'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=14,
        textColor=DARK_COLOR
    )

    normal_bold = ParagraphStyle(
        'NormalBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9.5,
        leading=13,
        textColor=DARK_COLOR
    )

    normal_text = ParagraphStyle(
        'NormalText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=13,
        textColor=DARK_COLOR
    )

    elements = []
    invoice_no = f"INV-AFP-{booking.id:05d}"
    invoice_date = booking.service_date.strftime("%d %b %Y") if booking.service_date else "N/A"

    # Settings-based business & GST configuration (Issues #27 & #28)
    workshop_name = getattr(settings, 'WORKSHOP_NAME', 'AutoFixPro Workshop')
    workshop_address = getattr(settings, 'WORKSHOP_ADDRESS', '101, AutoFixPro Plaza, SG Highway, Ahmedabad, Gujarat 380054')
    workshop_phone = getattr(settings, 'WORKSHOP_PHONE', '+91 98765 43210')
    workshop_email = getattr(settings, 'WORKSHOP_EMAIL', 'support@autofixpro.com')
    workshop_gstin = getattr(settings, 'WORKSHOP_GSTIN', '24AAACA1234F1Z9')
    gst_rate = Decimal(str(getattr(settings, 'GST_RATE', '18.00')))

    header_data = [
        [
            Paragraph(f"<font color='#FF4D30'><b>AutoFix</b></font><b>Pro</b> {_esc(workshop_name)}", title_style),
            Paragraph("<b>TAX INVOICE</b>", ParagraphStyle('TaxInv', parent=title_style, alignment=2, fontSize=18, textColor=PRIMARY_COLOR))
        ],
        [
            Paragraph(f"{_esc(workshop_address)}<br/>Phone: {_esc(workshop_phone)} | Email: {_esc(workshop_email)}<br/>GSTIN: <b>{_esc(workshop_gstin)}</b>", subtitle_style),
            Paragraph(f"<b>Invoice #:</b> {_esc(invoice_no)}<br/><b>Invoice Date:</b> {_esc(invoice_date)}<br/><b>Booking Ref:</b> #{booking.id}", ParagraphStyle('MetaRight', parent=subtitle_style, alignment=2))
        ]
    ]

    header_table = Table(header_data, colWidths=[3.8 * inch, 3.8 * inch])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 14))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=PRIMARY_COLOR, spaceBefore=0, spaceAfter=14))

    # XML/HTML escaped user and vehicle information (Issue #30)
    cust_info = f"""
    <b>{_esc(booking.user.fullname)}</b><br/>
    Email: {_esc(booking.user.email)}<br/>
    Phone: {_esc(booking.user.phone)}<br/>
    Client ID: #{booking.user.id}
    """

    veh_info = f"""
    <b>{_esc(booking.vehicle.brand)} {_esc(booking.vehicle.model)} ({_esc(booking.vehicle.year)})</b><br/>
    Reg No: <b>{_esc(booking.vehicle.vehicle_number)}</b><br/>
    Fuel: {_esc(booking.vehicle.fuel_type)} | Color: {_esc(booking.vehicle.color)}<br/>
    Slot: {_esc(booking.service_time or '09:00 AM')}
    """

    client_vehicle_data = [
        [Paragraph("BILLED TO (CUSTOMER)", section_heading), Paragraph("VEHICLE DETAILS", section_heading)],
        [Paragraph(cust_info, normal_text), Paragraph(veh_info, normal_text)]
    ]

    client_table = Table(client_vehicle_data, colWidths=[3.7 * inch, 3.7 * inch])
    client_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), BG_LIGHT),
        ('BOX', (0, 0), (-1, -1), 1, BORDER_COLOR),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
    ]))
    elements.append(client_table)
    elements.append(Spacer(1, 16))

    # Proper Decimal-based GST calculation (Issues #22, #23, #28)
    from workshop.views import get_service_amount
    raw_amount = booking.total_amount if hasattr(booking, "total_amount") else get_service_amount(booking.service_type)
    if payment and payment.amount is not None:
        amount = Decimal(str(payment.amount))
    else:
        amount = Decimal(str(raw_amount))

    tax_multiplier = Decimal('1') + (gst_rate / Decimal('100'))
    subtotal = (amount / tax_multiplier).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    half_gst_rate = (gst_rate / Decimal('2')).quantize(Decimal('0.01'))
    cgst = (subtotal * (half_gst_rate / Decimal('100'))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    sgst = (subtotal * (half_gst_rate / Decimal('100'))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    total = (subtotal + cgst + sgst).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    th_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
        textColor=colors.white
    )
    th_right = ParagraphStyle(
        'TableHeaderRight',
        parent=th_style,
        alignment=2
    )

    items_data = [
        [
            Paragraph("<b>#</b>", th_style),
            Paragraph("<b>Service Description &amp; Fitted Parts</b>", th_style),
            Paragraph("<b>Warranty / Audit</b>", th_style),
            Paragraph("<b>Rate (Rs.)</b>", th_right),
            Paragraph("<b>Amount (Rs.)</b>", th_right)
        ]
    ]

    base_pkg_price = booking.base_package_price if hasattr(booking, "base_package_price") else get_service_amount(booking.service_type)
    pkg_sub = (base_pkg_price / tax_multiplier).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    items_data.append([
        Paragraph("1", normal_text),
        Paragraph(f"<b>{_esc(booking.service_type)}</b><br/><font color='#64748B' size='8'>Complete Workshop Certified Labor &amp; Diagnostic Package</font>", normal_text),
        Paragraph("Included (40-Point)", normal_text),
        Paragraph(f"Rs. {pkg_sub:,.2f}", ParagraphStyle('RVal', parent=normal_text, alignment=2)),
        Paragraph(f"Rs. {pkg_sub:,.2f}", ParagraphStyle('AVal', parent=normal_text, alignment=2))
    ])

    item_idx = 1
    if hasattr(booking, "parts_used"):
        for part in booking.parts_used.select_related("inventory_item").all():
            item_idx += 1
            part_unit_sub = (Decimal(str(part.unit_price)) / tax_multiplier).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            part_line_sub = (Decimal(str(part.total_price)) / tax_multiplier).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            items_data.append([
                Paragraph(str(item_idx), normal_text),
                Paragraph(f"<b>{_esc(part.inventory_item.name)}</b> (Qty: {part.quantity})<br/><font color='#64748B' size='8'>OEM Part &bull; Category: {_esc(part.inventory_item.category)}</font>", normal_text),
                Paragraph("6-Mo / 10k km", normal_text),
                Paragraph(f"Rs. {part_unit_sub:,.2f}", ParagraphStyle('RVal', parent=normal_text, alignment=2)),
                Paragraph(f"Rs. {part_line_sub:,.2f}", ParagraphStyle('AVal', parent=normal_text, alignment=2))
            ])

    items_table = Table(items_data, colWidths=[0.4 * inch, 3.4 * inch, 1.4 * inch, 1.1 * inch, 1.3 * inch])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#0F172A")),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(items_table)
    elements.append(Spacer(1, 10))

    # Accurate paid status check: paid ONLY if payment record has status 'Paid' (Issue #29)
    is_paid = bool(payment and payment.payment_status == 'Paid')
    pay_method = f" ({_esc(payment.payment_method)})" if (payment and payment.payment_method) else ""
    status_text = f"PAID{pay_method}" if is_paid else "PAYMENT PENDING"
    status_color = "#16A34A" if is_paid else "#DC2626"

    summary_data = [
        [
            Paragraph(f"<font color='{status_color}'><b>STATUS: {status_text}</b></font><br/><font color='#64748B' size='8'>AutoFixPro Verified Workshop Billing</font>", normal_text),
            Paragraph("Subtotal:", ParagraphStyle('SubLbl', parent=normal_text, alignment=2)),
            Paragraph(f"Rs. {subtotal:,.2f}", ParagraphStyle('SubVal', parent=normal_text, alignment=2))
        ],
        [
            "",
            Paragraph(f"CGST ({half_gst_rate}%):", ParagraphStyle('CgstLbl', parent=normal_text, alignment=2)),
            Paragraph(f"Rs. {cgst:,.2f}", ParagraphStyle('CgstVal', parent=normal_text, alignment=2))
        ],
        [
            "",
            Paragraph(f"SGST ({half_gst_rate}%):", ParagraphStyle('SgstLbl', parent=normal_text, alignment=2)),
            Paragraph(f"Rs. {sgst:,.2f}", ParagraphStyle('SgstVal', parent=normal_text, alignment=2))
        ],
        [
            "",
            Paragraph("<b>Grand Total:</b>", ParagraphStyle('TotLbl', parent=normal_bold, alignment=2, fontSize=11)),
            Paragraph(f"<b>Rs. {total:,.2f}</b>", ParagraphStyle('TotVal', parent=normal_bold, alignment=2, fontSize=12, textColor=PRIMARY_COLOR))
        ],
    ]

    summary_table = Table(summary_data, colWidths=[4.2 * inch, 1.8 * inch, 1.6 * inch])
    summary_table.setStyle(TableStyle([
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('LINEABOVE', (1, 3), (2, 3), 1, DARK_COLOR),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 20))

    terms_text = f"""
    <b>Terms &amp; Conditions:</b><br/>
    1. 6-Month / 10,000 km warranty applicable on all genuine OEM parts fitted by {_esc(workshop_name)}.<br/>
    2. Digital tracking records are securely stored on your AutoFixPro customer account.<br/>
    3. For any service assistance, call <b>{_esc(workshop_phone)}</b> or email <b>{_esc(workshop_email)}</b>.
    """

    sig_data = [
        [
            Paragraph(terms_text, ParagraphStyle('Terms', parent=subtitle_style, fontSize=8, leading=11)),
            Paragraph(f"<b>For {_esc(workshop_name)}</b><br/><br/><br/>___________________________<br/><b>Authorized Workshop Signature</b>", ParagraphStyle('Sig', parent=subtitle_style, alignment=2, leading=12))
        ]
    ]

    sig_table = Table(sig_data, colWidths=[4.6 * inch, 3.0 * inch])
    sig_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(sig_table)

    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf
