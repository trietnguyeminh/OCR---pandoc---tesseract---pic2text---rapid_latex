"""Generate a born-digital sample PDF for testing FormuDoc.

Creates sample_data/sample.pdf with: a title, headings, paragraphs, unicode
math (display + inline), a ruled table, an embedded figure, and a repeated
header/footer across two pages — exercising every branch of the pipeline.
"""
import os
import matplotlib
import fitz
from PIL import Image, ImageDraw

HERE = os.path.dirname(__file__)
FONT = matplotlib.get_data_path() + "/fonts/ttf/DejaVuSans.ttf"
FONT_B = matplotlib.get_data_path() + "/fonts/ttf/DejaVuSans-Bold.ttf"


def _figure(path):
    img = Image.new("RGB", (360, 180), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 359, 179], outline="navy", width=3)
    for i, c in enumerate(["#4f46e5", "#7c3aed", "#2563eb"]):
        d.rectangle([40 + i * 100, 150 - i * 35, 110 + i * 100, 160],
                    fill=c)
    d.text((90, 12), "FormuDoc demo chart", fill="black")
    img.save(path)


def main():
    fig = "/tmp/_formudoc_chart.png"
    _figure(fig)
    doc = fitz.open()

    for pno in range(2):
        page = doc.new_page(width=595, height=842)  # A4
        page.insert_font(fontname="DJ", fontfile=FONT)
        page.insert_font(fontname="DJB", fontfile=FONT_B)
        # repeated header / footer
        page.insert_text((72, 36), "FormuDoc Technical Report — Confidential",
                         fontsize=8, fontname="DJ", color=(0.4, 0.4, 0.4))
        page.insert_text((72, 812), f"Page {pno + 1} of 2", fontsize=8,
                         fontname="DJ", color=(0.4, 0.4, 0.4))

        if pno == 0:
            page.insert_text((72, 90), "Deep Learning for Document Understanding",
                             fontsize=22, fontname="DJB")
            page.insert_text((72, 130), "1. Introduction", fontsize=15, fontname="DJB")
            body = ("Document AI converts unstructured PDFs into structured, "
                    "editable formats. This sample exercises text, headings, "
                    "tables, figures and mathematics.")
            page.insert_textbox(fitz.Rect(72, 145, 523, 210), body,
                                fontsize=11, fontname="DJ")
            page.insert_text((72, 230), "2. The Loss Function", fontsize=15, fontname="DJB")
            page.insert_textbox(fitz.Rect(72, 248, 523, 290),
                                "We minimise the cross-entropy objective shown below, "
                                "where the sum runs over all tokens.",
                                fontsize=11, fontname="DJ")
            # display formula (unicode math)
            page.insert_text((150, 320), "L(θ) = − ∑ᵢ yᵢ log( pᵢ ) + λ ∑ⱼ θⱼ²",
                             fontsize=15, fontname="DJ")
            page.insert_text((150, 350), "∫₀^∞ e^(−x²) dx = √π ⁄ 2",
                             fontsize=15, fontname="DJ")
            # figure
            page.insert_image(fitz.Rect(150, 380, 430, 520), filename=fig)
            page.insert_text((150, 535), "Figure 1: Training throughput by model size.",
                             fontsize=9, fontname="DJ")
        else:
            page.insert_text((72, 90), "3. Results", fontsize=15, fontname="DJB")
            page.insert_textbox(fitz.Rect(72, 108, 523, 150),
                                "Table 1 reports accuracy across configurations.",
                                fontsize=11, fontname="DJ")
            page.insert_text((72, 165), "Table 1: Model comparison.",
                             fontsize=9, fontname="DJ")
            # ruled table
            rows = [["Model", "Params", "Accuracy"],
                    ["Baseline", "12M", "88.1%"],
                    ["FormuNet", "45M", "93.7%"],
                    ["FormuNet-XL", "120M", "95.2%"]]
            x0, y0, cw, rh = 72, 180, 150, 26
            for r in range(len(rows) + 1):
                page.draw_line(fitz.Point(x0, y0 + r * rh),
                               fitz.Point(x0 + 3 * cw, y0 + r * rh))
            for c in range(4):
                page.draw_line(fitz.Point(x0 + c * cw, y0),
                               fitz.Point(x0 + c * cw, y0 + len(rows) * rh))
            for r, row in enumerate(rows):
                for c, val in enumerate(row):
                    page.insert_text((x0 + c * cw + 6, y0 + r * rh + 17), val,
                                     fontsize=10, fontname="DJ")

    out = os.path.join(HERE, "sample.pdf")
    doc.save(out)
    doc.close()
    try:
        os.remove(fig)
    except OSError:
        pass
    print("wrote", out)


if __name__ == "__main__":
    main()
