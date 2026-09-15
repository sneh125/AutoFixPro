import io
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch


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
    
    header_data = [
        [
            Paragraph("<font color='#FF4D30'><b>AutoFix</b></font><b>Pro</b> Workshop", title_style),
            Paragraph("<b>TAX INVOICE</b>", ParagraphStyle('TaxInv', parent=title_style, alignment=2, fontSize=18, textColor=PRIMARY_COLOR))
        ],
        [
            Paragraph("101, AutoFixPro Plaza, SG Highway, Ahmedabad, Gujarat 380054<br/>Phone: +91 98765 43210 | Email: support@autofixpro.com<br/>GSTIN: <b>24AAACA1234F1Z9</b>", subtitle_style),
            Paragraph(f"<b>Invoice #:</b> {invoice_no}<br/><b>Invoice Date:</b> {invoice_date}<br/><b>Booking Ref:</b> #{booking.id}", ParagraphStyle('MetaRight', parent=subtitle_style, alignment=2))
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

    cust_info = f"""
    <b>{booking.user.fullname}</b><br/>
    Email: {booking.user.email}<br/>
    Phone: {booking.user.phone}<br/>
    Client ID: #{booking.user.id}
    """

    veh_info = f"""
    <b>{booking.vehicle.brand} {booking.vehicle.model} ({booking.vehicle.year})</b><br/>
    Reg No: <b>{booking.vehicle.vehicle_number}</b><br/>
    Fuel: {booking.vehicle.fuel_type} | Color: {booking.vehicle.color}<br/>
    Slot: {booking.service_time or '09:00 AM'}
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

    from workshop.views import get_service_amount
    amount = get_service_amount(booking.service_type)
    if payment and payment.amount:
        amount = float(payment.amount)

    subtotal = round(amount / 1.18, 2)
    cgst = round(subtotal * 0.09, 2)
    sgst = round(subtotal * 0.09, 2)
    total = round(subtotal + cgst + sgst, 2)

    items_data = [
        [
            Paragraph("<b>#</b>", normal_bold),
            Paragraph("<b>Service Description</b>", normal_bold),
            Paragraph("<b>Diagnostic Scan</b>", normal_bold),
            Paragraph("<b>Rate (₹)</b>", ParagraphStyle('RHead', parent=normal_bold, alignment=2)),
            Paragraph("<b>Amount (₹)</b>", ParagraphStyle('AHead', parent=normal_bold, alignment=2))
        ],
        [
            Paragraph("1", normal_text),
            Paragraph(f"<b>{booking.service_type}</b><br/><font color='#64748B' size='8'>Complete Workshop Labor, OEM Filter &amp; Fluid Service</font>", normal_text),
            Paragraph("Included (40-Point)", normal_text),
            Paragraph(f"₹{subtotal:,.2f}", ParagraphStyle('RVal', parent=normal_text, alignment=2)),
            Paragraph(f"₹{subtotal:,.2f}", ParagraphStyle('AVal', parent=normal_text, alignment=2))
        ]
    ]

    items_table = Table(items_data, colWidths=[0.4 * inch, 3.4 * inch, 1.4 * inch, 1.1 * inch, 1.3 * inch])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#0F172A")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(items_table)
    elements.append(Spacer(1, 10))

    is_paid = (booking.status == 'Completed') or (payment and payment.payment_status == 'Paid')
    status_text = "PAID (RAZORPAY DIGITAL)" if is_paid else "PAYMENT PENDING"
    status_color = "#16A34A" if is_paid else "#DC2626"

    summary_data = [
        [
            Paragraph(f"<font color='{status_color}'><b>STATUS: {status_text}</b></font><br/><font color='#64748B' size='8'>Payment Gateway: Razorpay Secured | 256-Bit Encrypted</font>", normal_text),
            Paragraph("Subtotal:", ParagraphStyle('SubLbl', parent=normal_text, alignment=2)),
            Paragraph(f"₹{subtotal:,.2f}", ParagraphStyle('SubVal', parent=normal_text, alignment=2))
        ],
        [
            "",
            Paragraph("CGST (9%):", ParagraphStyle('CgstLbl', parent=normal_text, alignment=2)),
            Paragraph(f"₹{cgst:,.2f}", ParagraphStyle('CgstVal', parent=normal_text, alignment=2))
        ],
        [
            "",
            Paragraph("SGST (9%):", ParagraphStyle('SgstLbl', parent=normal_text, alignment=2)),
            Paragraph(f"₹{sgst:,.2f}", ParagraphStyle('SgstVal', parent=normal_text, alignment=2))
        ],
        [
            "",
            Paragraph("<b>Grand Total:</b>", ParagraphStyle('TotLbl', parent=normal_bold, alignment=2, fontSize=11)),
            Paragraph(f"<b>₹{total:,.2f}</b>", ParagraphStyle('TotVal', parent=normal_bold, alignment=2, fontSize=12, textColor=PRIMARY_COLOR))
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

    terms_text = """
    <b>Terms & Conditions:</b><br/>
    1. 6-Month / 10,000 km warranty applicable on all genuine OEM parts fitted by AutoFixPro.<br/>
    2. Digital tracking records are securely stored on your AutoFixPro customer account.<br/>
    3. For any service assistance, call <b>+91 98765 43210</b> or email <b>support@autofixpro.com</b>.
    """

    sig_data = [
        [
            Paragraph(terms_text, ParagraphStyle('Terms', parent=subtitle_style, fontSize=8, leading=11)),
            Paragraph("<b>For AutoFixPro Technologies Inc.</b><br/><br/><br/>___________________________<br/><b>Authorized Workshop Signature</b>", ParagraphStyle('Sig', parent=subtitle_style, alignment=2, leading=12))
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
