from pathlib import Path

from docx import Document
from docx.document import Document as DocumentType
from docx.table import Table as DocxTable
from docx.text.paragraph import Paragraph as DocxParagraph
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / '南化建招聘管理系统操作手册.docx'
OUTPUT = ROOT / '.manual_qa' / 'manual-review.pdf'


def blocks(parent):
    parent_element = parent.element.body if isinstance(parent, DocumentType) else parent._tc
    for child in parent_element.iterchildren():
        if isinstance(child, CT_P):
            yield DocxParagraph(child, parent)
        elif isinstance(child, CT_Tbl):
            yield DocxTable(child, parent)


def esc(text):
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def render():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    pdfmetrics.registerFont(TTFont('CN', r'C:\Windows\Fonts\simhei.ttf'))
    base = getSampleStyleSheet()
    styles = {
        'Normal': ParagraphStyle('CNBody', parent=base['BodyText'], fontName='CN', fontSize=9.5, leading=14, textColor=colors.HexColor('#1F2F44'), spaceAfter=5),
        'Title': ParagraphStyle('CNTitle', parent=base['Title'], fontName='CN', fontSize=25, leading=32, textColor=colors.black, alignment=TA_CENTER, spaceAfter=18),
        'Heading 1': ParagraphStyle('CNH1', parent=base['Heading1'], fontName='CN', fontSize=17, leading=23, textColor=colors.black, spaceBefore=8, spaceAfter=8, keepWithNext=True),
        'Heading 2': ParagraphStyle('CNH2', parent=base['Heading2'], fontName='CN', fontSize=12.5, leading=18, textColor=colors.black, spaceBefore=8, spaceAfter=5, keepWithNext=True),
        'Heading 3': ParagraphStyle('CNH3', parent=base['Heading3'], fontName='CN', fontSize=10.5, leading=15, textColor=colors.black, spaceBefore=6, spaceAfter=4, keepWithNext=True),
        'List Bullet': ParagraphStyle('CNBullet', parent=base['BodyText'], fontName='CN', fontSize=9.5, leading=14, leftIndent=16, firstLineIndent=-9, bulletIndent=4, spaceAfter=4),
        'List Bullet 2': ParagraphStyle('CNBullet2', parent=base['BodyText'], fontName='CN', fontSize=9.5, leading=14, leftIndent=28, firstLineIndent=-9, bulletIndent=16, spaceAfter=4),
        'List Number': ParagraphStyle('CNNumber', parent=base['BodyText'], fontName='CN', fontSize=9.5, leading=14, leftIndent=18, firstLineIndent=-10, spaceAfter=4),
    }
    table_cell = ParagraphStyle('CNCell', parent=styles['Normal'], fontSize=8.1, leading=11, spaceAfter=0)
    table_head = ParagraphStyle('CNCellHead', parent=table_cell, textColor=colors.white, alignment=TA_CENTER)
    story = []
    document = Document(SOURCE)
    number = 0
    for block in blocks(document):
        if isinstance(block, DocxParagraph):
            text = block.text.strip()
            if not text:
                if block._p.xpath('.//w:br[@w:type="page"]'):
                    story.append(PageBreak())
                    number = 0
                    continue
                story.append(Spacer(1, 5))
                continue
            style_name = block.style.name
            style = styles.get(style_name, styles['Normal'])
            if style_name == 'List Number':
                number += 1
                text = f'{number}. {text}'
            elif style_name.startswith('Heading') or style_name == 'Title':
                number = 0
            elif style_name.startswith('List Bullet'):
                text = '• ' + text
            story.append(Paragraph(esc(text), style))
        else:
            data = []
            for row_index, row in enumerate(block.rows):
                data.append([Paragraph(esc(cell.text), table_head if row_index == 0 else table_cell) for cell in row.cells])
            widths = [6.65 * inch / max(len(data[0]), 1)] * len(data[0])
            table = Table(data, colWidths=widths, repeatRows=1, hAlign='CENTER')
            commands = [
                ('FONTNAME', (0, 0), (-1, -1), 'CN'),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#123A67')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#D9D9D9')),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ]
            for row_index in range(2, len(data), 2):
                commands.append(('BACKGROUND', (0, row_index), (-1, row_index), colors.HexColor('#F6F9FD')))
            table.setStyle(TableStyle(commands))
            story.extend([table, Spacer(1, 8)])

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont('CN', 8)
        canvas.setFillColor(colors.HexColor('#5C6C80'))
        canvas.drawRightString(letter[0] - 0.78 * inch, 0.38 * inch, f'第 {doc.page} 页')
        canvas.restoreState()

    pdf = SimpleDocTemplate(str(OUTPUT), pagesize=letter, leftMargin=0.78 * inch, rightMargin=0.78 * inch, topMargin=0.68 * inch, bottomMargin=0.6 * inch, title='南化建招聘管理系统操作手册审阅稿')
    pdf.build(story, onFirstPage=footer, onLaterPages=footer)
    print(OUTPUT)


if __name__ == '__main__':
    render()
