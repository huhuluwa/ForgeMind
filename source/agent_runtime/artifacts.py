from pathlib import Path
import html
import re
import zipfile
from datetime import datetime

def requested_artifact_format(query):
    if not re.search(r"生成|制作|做成|导出|转换成|整理成|存成|保存为|给我.{0,8}(?:文件|电子书|文档|PDF|EPUB|TXT)", query, re.I):
        return None
    q = query.lower()
    if re.search(r"\bepub\b|电子书", q, re.I):
        return "epub"
    if re.search(r"\bpdf\b|pdf文件", q, re.I):
        return "pdf"
    if re.search(r"\btxt\b|\bttc\b|纯文本文件|文本文件", q, re.I):
        return "txt"
    return None

def _plain_text(markdown):
    text = re.sub(r"\x60{3}[A-Za-z0-9_-]*\n?", "", str(markdown))
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"^\s*[-*+]\s+", "• ", text, flags=re.M)
    text = re.sub(r"[*_~]", "", text)
    return text.strip()

def _write_pdf(path, title, text):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    fonts = [Path(r"C:\Windows\Fonts\msyh.ttc"), Path(r"C:\Windows\Fonts\simsun.ttc"),
             Path(r"C:\Windows\Fonts\simhei.ttf")]
    font_path = next((f for f in fonts if f.exists()), None)
    font_name = "Helvetica"
    if font_path:
        try:
            pdfmetrics.registerFont(TTFont("ForgeMindCJK", str(font_path), subfontIndex=0))
            font_name = "ForgeMindCJK"
        except Exception:
            pass
    doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=54, leftMargin=54,
                            topMargin=54, bottomMargin=54, title=title, author="ForgeMind")
    heading = ParagraphStyle("ForgeTitle", fontName=font_name, fontSize=18, leading=25,
                             textColor=colors.HexColor("#202124"), spaceAfter=18)
    body = ParagraphStyle("ForgeBody", fontName=font_name, fontSize=10.5, leading=17,
                          alignment=TA_LEFT, textColor=colors.HexColor("#202124"),
                          spaceAfter=7, wordWrap="CJK")
    story = [Paragraph(html.escape(title), heading)]
    for para in text.splitlines():
        if para.strip():
            story.append(Paragraph(html.escape(para), body))
        else:
            story.append(Spacer(1, 8))
    doc.build(story)

def _write_epub(path, title, text):
    title_xml = html.escape(title)
    paragraphs = "".join("<p>" + html.escape(line) + "</p>" for line in text.splitlines() if line.strip())
    container = ('<?xml version="1.0" encoding="UTF-8"?>'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
        '</rootfiles></container>')
    opf = ('<?xml version="1.0" encoding="UTF-8"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="bookid">forgemind-'
        + datetime.now().strftime("%Y%m%d%H%M%S") + '</dc:identifier><dc:title>' + title_xml
        + '</dc:title><dc:language>zh</dc:language></metadata>'
        '<manifest><item id="content" href="content.xhtml" media-type="application/xhtml+xml"/>'
        '</manifest><spine><itemref idref="content"/></spine></package>')
    xhtml = ('<?xml version="1.0" encoding="UTF-8"?>'
        '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>' + title_xml
        + '</title><meta charset="UTF-8"/></head><body><h1>' + title_xml
        + '</h1>' + paragraphs + '</body></html>')
    with zipfile.ZipFile(path, "w") as book:
        book.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        book.writestr("META-INF/container.xml", container, compress_type=zipfile.ZIP_DEFLATED)
        book.writestr("OEBPS/content.opf", opf, compress_type=zipfile.ZIP_DEFLATED)
        book.writestr("OEBPS/content.xhtml", xhtml, compress_type=zipfile.ZIP_DEFLATED)

def create_artifact(query, answer, output_dir):
    fmt = requested_artifact_format(query)
    if not fmt:
        return None
    text = _plain_text(answer)
    if not text:
        return {"error": "回答内容为空，无法生成文件"}
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    title = "ForgeMind 对话整理"
    name = f"forgemind-{stamp}.{fmt}"
    path = output_dir / name
    try:
        if fmt == "txt":
            path.write_text(text + "\n", encoding="utf-8")
        elif fmt == "epub":
            _write_epub(path, title, text)
        elif fmt == "pdf":
            _write_pdf(path, title, text)
    except Exception as exc:
        path.unlink(missing_ok=True)
        return {"error": f"{fmt.upper()} 生成失败：{type(exc).__name__}: {str(exc)[:180]}"}
    return {"name": name, "format": fmt, "bytes": path.stat().st_size, "url": "/files/" + name}
