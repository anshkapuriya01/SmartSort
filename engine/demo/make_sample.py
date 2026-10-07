"""Build a realistic messy Desktop to try smartsort on.

    python demo/make_sample.py ~/smartsort-demo
"""

import random
import shutil
import sys
from pathlib import Path

import docx
import pymupdf as fitz
from pillow_heif import register_heif_opener
from PIL import Image, ImageDraw, ImageFont
from pptx import Presentation

register_heif_opener()

# (filename, title, body) — a typical Desktop: home admin, work, travel, a little reading.
PDFS = [
    ("document(3).pdf", "Order Receipt",
     "Thank you for your order. Order number 402-8812345. Order date 4 September 2026. Items: wireless "
     "mouse x 1, Rs 1,299; USB-C cable x 2, Rs 798. Subtotal Rs 2,097, delivery free, total paid Rs 2,097. "
     "Payment method: credit card ending 4421. Shipping address: 12 Park Street, Pune."),
    ("0042.pdf", "Electricity Bill - September 2026",
     "Consumer number 110023344. Billing period 1 Aug to 31 Aug 2026. Previous reading 18234, current "
     "reading 18512, units consumed 278. Energy charges Rs 1,946, fixed charges Rs 120, tax Rs 98. "
     "Amount due Rs 2,164. Due date 20 September 2026. Pay online to avoid a late payment surcharge."),
    ("Untitled 2.pdf", "Account Statement",
     "Savings account XXXX4410. Statement period 1 August 2026 to 31 August 2026. Opening balance "
     "Rs 84,210.55. 02 Aug UPI/grocery debit 1,240.00. 05 Aug salary credit 92,000.00. 10 Aug rent "
     "debit 25,000.00. 18 Aug ATM withdrawal 5,000.00. Closing balance Rs 1,41,105.30."),
    ("salary.pdf", "Payslip for August 2026",
     "Employee ID E10442. Designation: Senior Analyst. Earnings: basic pay 46,000, house rent allowance "
     "18,400, special allowance 27,600. Deductions: provident fund 5,520, professional tax 200, income "
     "tax 8,900. Net pay Rs 77,380 credited to bank account ending 4410."),
    ("tax2025.pdf", "Income Tax Return Acknowledgement",
     "Assessment year 2026-27. Form ITR-1. PAN XXXXX1234X. Total income Rs 11,04,000. Tax payable "
     "Rs 0 after deductions under section 80C and 80D. Refund due Rs 6,420. Filed electronically and "
     "verified. Keep this acknowledgement for your records."),
    ("insurance.pdf", "Motor Insurance Policy Schedule",
     "Policy number MI/2026/883421. Insured vehicle: hatchback, registration MH12 AB 1234. Period of "
     "insurance 15 Jan 2026 to 14 Jan 2027. Insured declared value Rs 4,10,000. Premium Rs 9,860 "
     "including GST. Own damage and third party liability cover. No claim bonus 20%."),
    ("download.pdf", "E-Ticket / Booking Confirmation",
     "Booking reference XK29PL. Passenger: Sara Khan. Flight AI 302 from Delhi (DEL) to Mumbai (BOM). "
     "Departure 14 October 2026 06:40, arrival 08:55. Seat 14C. Cabin baggage 7 kg, check-in 15 kg. "
     "Web check-in opens 48 hours before departure. Please carry a valid photo ID."),
    ("IMG_2024.pdf", "Hotel Reservation Confirmed",
     "Thank you for booking with us. Confirmation number 77120934. Check-in Wednesday 14 October 2026 "
     "from 2 pm, check-out Saturday 17 October 2026 by 11 am. Deluxe king room, 2 adults. Total "
     "Rs 18,600 including taxes. Free cancellation until 12 October."),
    ("scan_0012.pdf", "Residential Lease Agreement",
     "This lease agreement is made on 1 April 2026 between the landlord and the tenant for the flat at "
     "12 Park Street, Pune. Term: 11 months. Monthly rent Rs 25,000 payable by the 5th. Security deposit "
     "Rs 75,000, refundable. Either party may terminate with one month notice. Signatures of both parties."),
    ("contract_v2_FINAL.pdf", "Mutual Non-Disclosure Agreement",
     "This agreement is entered into by and between the parties to protect confidential information "
     "shared for evaluating a potential business relationship. Confidential information shall not be "
     "disclosed to any third party for three years. Governing law: India. In witness whereof the parties "
     "have executed this agreement."),
    ("a8f3c9e1.pdf", "Quarterly Business Review - Q2 2026",
     "Executive summary: revenue grew 14% year over year to Rs 4.2 crore, driven by the enterprise "
     "segment. Gross margin improved to 61%. Customer churn fell to 2.1%. Risks: hiring delays in "
     "engineering. Recommendations: expand the sales team in the south region and invest in onboarding."),
    ("report.pdf", "Campaign Performance Report - Monsoon Sale",
     "Overview of the monsoon sale marketing campaign. Channels: social media, email, search ads. "
     "Impressions 2.4 million, click-through rate 3.1%, conversions 8,450, cost per acquisition Rs 212. "
     "Email outperformed paid social. Next steps: shift budget toward retargeting and email."),
    ("notes.pdf", "Product Launch Sync - Meeting Notes",
     "Meeting notes, 22 September. Attendees: Priya, Tom, Ana, Rahul. Discussed the launch date for the "
     "new mobile app, beta feedback and the press plan. Decisions: launch moves to 15 October. Action "
     "items: Tom to fix the onboarding bug, Ana to finalise screenshots, Rahul to brief support."),
    ("file_7.pdf", "WX-200 Washing Machine - User Manual",
     "Read these safety instructions before use. Installation: place the machine on a level floor and "
     "connect the inlet hose. Selecting a programme: turn the dial to Cotton, Synthetic or Quick Wash. "
     "Cleaning the filter every month. Troubleshooting: if the drum does not spin, check the load balance."),
    ("final.pdf", "Laboratory Test Report - Complete Blood Count",
     "Patient: Sara Khan, 32 years. Sample collected 2 September 2026. Haemoglobin 13.2 g/dL (normal "
     "12-15). White blood cell count 7,400 per microlitre. Platelets 2.6 lakh. Fasting blood sugar "
     "92 mg/dL. Vitamin D 18 ng/mL, low; please consult your physician."),
    ("Document.pdf", "Sara Khan - Resume",
     "Email: sara@example.com | Phone +91 98xxxxxx10. Experience: Senior Analyst, 2022-present, built "
     "dashboards and forecasting models. Analyst, 2019-2022. Education: MBA, 2019; B.Com, 2017. Skills: "
     "SQL, Excel, Python, Tableau, stakeholder management. Languages: English, Hindi."),
    ("cert.pdf", "Certificate of Completion",
     "This is to certify that Sara Khan has successfully completed the online course Data Visualisation "
     "Fundamentals, consisting of 24 hours of lessons and graded projects. Awarded on 5 June 2026."),
    ("paper.pdf", "Attention-Based Forecasting for Retail Demand",
     "Abstract. We propose an attention-based model for forecasting daily retail demand. 1 Introduction. "
     "2 Related work on time-series forecasting. 3 Method. 4 Experiments on three public datasets show a "
     "9% lower error than strong baselines. 5 Conclusion. References."),
    ("receipt.pdf", "Your order from Spice Route has been delivered",
     "Order ID 58213390. Ordered on 18 September 2026, 8:42 pm via FoodHub. Restaurant: Spice Route, "
     "Koregaon Park. Items: paneer butter masala x 1, garlic naan x 3, mango lassi x 2. Item total Rs 690, "
     "delivery fee Rs 35, platform fee Rs 5, taxes Rs 36. Total paid Rs 766 by UPI. Delivered in 32 minutes."),
    ("receipt (2).pdf", "Order Summary - Burger Barn",
     "Thanks for ordering with FoodHub. Order #58291177 placed 21 September 2026, 1:15 pm. Burger Barn, "
     "Baner Road. 2 x classic chicken burger, 1 x large fries, 2 x cold coffee. Item total Rs 840, packaging "
     "Rs 20, delivery partner fee Rs 30, GST Rs 42. Grand total Rs 932. Paid with card. Rate your meal."),
    ("IMG_3301.pdf", "Order Delivered - Dosa Corner",
     "Your food order from Dosa Corner was delivered at 9:05 am on 26 September 2026. Order number 58377012. "
     "Masala dosa x 2, filter coffee x 2, medu vada x 1. Subtotal Rs 380, delivery Rs 25, taxes Rs 19. "
     "Amount paid Rs 424 via wallet. Tip your delivery partner. Ordered on the FoodHub app."),
    ("bill.pdf", "FreshMart Grocery - Tax Invoice",
     "FreshMart Supermarket, Aundh. Bill no. FM-77120, 24 September 2026. Toor dal 1 kg Rs 168, basmati rice "
     "5 kg Rs 640, sunflower oil 1 L Rs 155, eggs 12 Rs 84, milk 2 L Rs 116, bananas 1 dozen Rs 60. Total "
     "Rs 1,223, GST included. Paid by debit card. Thank you for shopping at FreshMart."),
    ("ride.pdf", "Trip receipt - Thanks for riding",
     "Ride on 23 September 2026 from Pune Airport to Kalyani Nagar. Distance 9.4 km, duration 28 min. Base "
     "fare Rs 180, distance charge Rs 112, time charge Rs 28, airport fee Rs 50. Total Rs 370 charged to "
     "card ending 4421. Driver: Ramesh, white sedan MH12 XY 4521. Rate your ride."),
    ("ticket2.pdf", "Train E-Ticket - Deccan Queen",
     "PNR 4521889012. Train 12124 Deccan Queen, Pune to Mumbai CSMT. Journey date 2 October 2026, departure "
     "07:15, arrival 10:25. Coach C3, seat 42, chair car. Passenger: Sara Khan, 32, female. Fare Rs 420. "
     "Carry a valid photo identity card during the journey."),
    ("ch2.pdf", "Chapter 2: Understanding Exposure",
     "Exposure is the amount of light that reaches the camera sensor. It is controlled by three settings: "
     "aperture, shutter speed and ISO. A wide aperture gives a shallow depth of field. A fast shutter "
     "freezes motion. Raising ISO brightens the image but adds noise. Together they form the exposure triangle."),
    ("ch3.pdf", "Chapter 3: Composition",
     "Composition is how elements are arranged in the frame. The rule of thirds places the subject off "
     "centre. Leading lines guide the eye. Framing and negative space add depth. Shoot at eye level for "
     "portraits and change your viewpoint to make ordinary scenes interesting."),
]

DOCXS = [
    ("New Document.docx", "Cover Letter",
     "Dear Hiring Manager, I am writing to apply for the Data Analytics Lead role advertised on your "
     "careers page. Over the past seven years I have built reporting systems and forecasting models. "
     "I would welcome the chance to discuss how I can help your team. Sincerely, Sara Khan"),
    ("notes.docx", "Marketing Weekly - Notes",
     "Meeting notes, 29 September. Reviewed the monsoon sale results and the Q4 content calendar. "
     "Decided to test two new email subject lines and pause the underperforming display ads. Action "
     "items: Priya to draft the festive campaign brief, Tom to share the budget split."),
]

PPTX = ("ppt.pptx", "Q4 Marketing Plan",
        ["Goals: grow festive sales by 25%", "Channels: email, social media, search ads, partnerships",
         "Budget split and timeline", "Creative themes for the festive campaign",
         "Measurement: conversions, cost per acquisition, retention"])


def write_pdf(path: Path, title: str, body: str, scanned: bool = False):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(fitz.Rect(60, 50, 540, 130), title, fontsize=20, fontname="hebo")
    page.insert_textbox(fitz.Rect(60, 140, 540, 780), body, fontsize=11, fontname="helv")
    if scanned:  # flatten to an image so there's no text layer, like a phone scan
        pix = page.get_pixmap(dpi=120)
        img_doc = fitz.open()
        p = img_doc.new_page(width=page.rect.width, height=page.rect.height)
        p.insert_image(p.rect, pixmap=pix)
        img_doc.save(path)
        return
    doc.save(path)


def font(size):
    for f in ["/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Helvetica.ttc"]:
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            pass
    return ImageFont.load_default()


def screenshot(path: Path, lines: list[str]):
    img = Image.new("RGB", (1440, 900), (30, 30, 36))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 1440, 36], fill=(50, 50, 58))
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse([14 + i * 22, 11, 28 + i * 22, 25], fill=c)
    d.rectangle([0, 36, 240, 900], fill=(40, 40, 48))
    for i, name in enumerate(["main.py", "utils.py", "README.md", "tests/"]):
        d.text((20, 60 + i * 28), name, fill=(190, 190, 200), font=font(18))
    for i, line in enumerate(lines):
        d.text((270, 60 + i * 30), line, fill=(220, 220, 170) if i % 3 else (120, 200, 255), font=font(20))
    img.save(path)


def chart(path: Path):
    img = Image.new("RGB", (1000, 700), "white")
    d = ImageDraw.Draw(img)
    d.text((300, 20), "Monthly Expenses 2026", fill="black", font=font(32))
    d.line([80, 620, 950, 620], fill="black", width=3)
    d.line([80, 620, 80, 90], fill="black", width=3)
    for i, h in enumerate([300, 420, 260, 480, 350, 390]):
        d.rectangle([120 + i * 135, 620 - h, 200 + i * 135, 620], fill=(70, 130, 220))
        d.text((125 + i * 135, 630), ["Jan", "Feb", "Mar", "Apr", "May", "Jun"][i], fill="black", font=font(22))
    img.save(path)


def main(out: Path):
    if out.exists() and any(out.iterdir()):
        sys.exit(f"{out} is not empty; pick a new folder")
    out.mkdir(parents=True, exist_ok=True)
    random.seed(7)
    for name, title, body in PDFS:
        write_pdf(out / name, title, body, scanned=(name == "scan_0012.pdf"))
    shutil.copy(out / "Untitled 2.pdf", out / "statement (1).pdf")  # exact duplicate, different name

    for name, title, body in DOCXS:
        d = docx.Document()
        d.add_heading(title, level=1)
        d.add_paragraph(body)
        d.save(out / name)

    name, title, bullets = PPTX
    prs = Presentation()
    s = prs.slides.add_slide(prs.slide_layouts[0])
    s.shapes.title.text = title
    s.placeholders[1].text = "Marketing team"
    s = prs.slides.add_slide(prs.slide_layouts[1])
    s.shapes.title.text = "Overview"
    s.placeholders[1].text = "\n".join(bullets)
    prs.save(out / name)

    (out / "todo.txt").write_text("buy milk\npay electricity bill\ncall mom\nrenew car insurance before january\n"
                                  "book cab to airport for 14 oct\n")
    (out / "recipe.txt").write_text(
        "Masala chai. Ingredients: 2 cups water, 1 cup milk, 2 tsp tea leaves, sugar, crushed ginger, "
        "2 cardamom pods. Method: boil water with ginger and cardamom, add tea leaves and simmer for two "
        "minutes, add milk and sugar, bring to a boil and strain. Serves two.\n")
    (out / "export_sales.py").write_text(
        "import csv\n\ndef export(rows, path):\n    with open(path, 'w', newline='') as f:\n"
        "        writer = csv.writer(f)\n        for row in rows:\n            writer.writerow(row)\n"
    )

    screenshot(out / "Screenshot 2026-09-14 at 10.21.33.png",
               ["def bfs(graph, start):", "    seen = {start}", "    queue = deque([start])",
                "    while queue:", "        node = queue.popleft()", "        for nxt in graph[node]:"])
    screenshot(out / "IMG_4471.png",
               ["$ npm run build", "ERROR in src/App.tsx:12", "  Type 'string' is not assignable",
                "  to type 'number'.", "Found 1 error."])
    chart(out / "image.png")

    # Real photos: macOS ships some; copy two and make a resized duplicate of one.
    photos = sorted(Path("/System/Library/Desktop Pictures/.thumbnails").glob("*.heic"))[:2] or sorted(
        Path("/Library/Desktop Pictures").glob("*.jpg"))[:2]
    for i, p in enumerate(photos):
        Image.open(p).convert("RGB").save(out / f"IMG_{2031 + i}.jpg", quality=92)
    if photos:
        im = Image.open(out / "IMG_2031.jpg")
        im.resize((im.width // 2, im.height // 2)).save(out / "photo (2).jpg", quality=80)

    (out / "project-backup.zip").write_bytes(b"PK\x05\x06" + bytes(18))
    (out / "Zoom-installer.dmg").write_bytes(bytes(1024))
    (out / "meeting-recording.mp4").write_bytes(bytes(2048))
    (out / "expenses.csv").write_text("date,category,amount\n2026-09-02,groceries,1240\n2026-09-10,rent,25000\n")
    print(f"Made {len(list(out.iterdir()))} files in {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "~/smartsort-demo").expanduser())
