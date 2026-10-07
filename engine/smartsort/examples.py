"""Short example snippets for each document type.

Document types are recognised by comparing a file with these examples rather than with a
one-line description. The examples also give a fixed reference point for centring, so the
result doesn't depend on what else happens to be in the folder (a folder that is 90% reports
would otherwise cancel out the very signal that says "report").
"""

KIND_EXAMPLES = {
    "Notes & Articles": [
        "Chapter 5: Thermodynamics. The first law states that energy can neither be created nor destroyed. "
        "Internal energy, heat and work are related by dU = q + w. Isothermal and adiabatic processes are compared.",
        "Meeting notes, 12 March. Attendees: Priya, Tom, Ana. Discussed the launch timeline and budget. "
        "Action items: Tom to update the roadmap, Ana to share the design mockups by Friday.",
        "Weekly sync notes. Agenda, discussion points, decisions made and next steps for the team.",
        "How sleep affects memory. Researchers have long known that a good night's sleep helps us remember. "
        "In this article we look at what happens in the brain during deep sleep and why it matters.",
        "Introduction to cell biology. Cells are the basic unit of life. Prokaryotic cells lack a nucleus; "
        "eukaryotic cells have membrane-bound organelles such as mitochondria.",
    ],
    "Reports": [
        "Quarterly Business Review Q2 2026. Executive summary: revenue grew 14% year over year. Key metrics, "
        "regional performance, risks and recommendations. Appendix: detailed figures by product line.",
        "Project status report. Overview, progress this month, milestones achieved, budget versus actual, "
        "issues and risks, next steps.",
        "Annual sustainability report 2025: emissions, energy use, targets and progress against goals.",
    ],
    "Manuals & Guides": [
        "User manual. Model WX-200 washing machine. Safety instructions. Installation. Operating the controls. "
        "Cleaning and maintenance. Troubleshooting: if the drum does not spin, check that... Warranty.",
        "Getting started guide. Step 1: download the app. Step 2: create an account. Step 3: connect your "
        "device. Frequently asked questions and support contacts.",
        "Experiment 6. Aim: to determine the focal length of a convex lens. Apparatus: optical bench, lens. "
        "Procedure: 1. Place the lens... Observations. Result. Precautions.",
    ],
    "Letters & Forms": [
        "Dear Hiring Manager, I am writing to apply for the position of product designer at your company. "
        "I believe my experience... Thank you for your consideration. Sincerely, Maya Lee",
        "Application form. Full name, date of birth, address, phone number, email. Declaration: I confirm "
        "that the information given is correct. Signature and date.",
        "To whom it may concern. This letter is to confirm that Mr. Arjun Rao has been employed with us "
        "since 2021 as a senior analyst. Regards, HR Department.",
    ],
    "Contracts & Agreements": [
        "Residential lease agreement. This agreement is made between the landlord and the tenant. Term of "
        "lease: 11 months. Monthly rent, security deposit, maintenance, termination clause. Signatures.",
        "Non-disclosure agreement. The parties agree that confidential information shall not be disclosed "
        "to any third party. Governing law. In witness whereof the parties have signed.",
        "Terms of service and employment contract: duties, compensation, notice period, confidentiality.",
        "Policy schedule. Policy number, insured person, period of insurance, sum insured, premium, "
        "cover details, exclusions, claims procedure and terms and conditions of the policy.",
    ],
    "Invoices & Receipts": [
        "TAX INVOICE. Invoice number INV-1043. Date 03/02/2026. Billed to: customer name and address. "
        "Description, quantity, rate, amount. Subtotal, GST 18%, total payable. Payment due within 15 days.",
        "Payment receipt. Transaction ID 88231. Amount paid: Rs 1,499. Paid via card ending 4421. "
        "Order summary: 1 x headphones. Thank you for shopping with us.",
        "Electricity bill. Consumer number, billing period, units consumed, amount due, due date.",
    ],
    "Statements": [
        "Account statement for the period 1 Jan to 31 Jan 2026. Opening balance, date, description, debit, "
        "credit, balance. Closing balance. Savings account number XXXX4410.",
        "Salary slip for March 2026. Employee ID, basic pay, house rent allowance, deductions, provident "
        "fund, income tax, net pay credited to bank account.",
        "Credit card statement. Statement date, payment due date, total amount due, minimum amount due, "
        "transactions, reward points.",
        "Income tax return acknowledgement. Assessment year, PAN, total income, deductions, tax paid, "
        "refund due. Form 16 certificate of tax deducted at source.",
    ],
    "Tickets & Bookings": [
        "E-ticket. Booking reference XK29PL. Passenger: Sara Khan. Flight AI 302 Delhi to Mumbai, departure "
        "06:40, seat 14C, baggage allowance 15 kg. Please arrive at the airport two hours before departure.",
        "Hotel booking confirmation. Check-in 12 May, check-out 15 May. Deluxe room, 2 guests. Booking ID, "
        "total price, cancellation policy.",
        "Train ticket PNR 4521889. Coach B2, berth 34. Journey date, from, to, fare. Event ticket: gate, row, seat.",
    ],
    "Resumes": [
        "Curriculum Vitae. Priya Sharma. Email, phone, LinkedIn. Education: B.Sc. Computer Science, 2022-2025. "
        "Skills: Java, Python, SQL. Experience: intern at a software company. Projects. Achievements.",
        "RESUME. Objective: seeking a challenging role. Work experience: Sales executive 2019-2023. "
        "Education. Certifications. Languages known. References available on request.",
    ],
    "Certificates": [
        "Certificate of Achievement. This is to certify that Aman Gupta has successfully completed the "
        "workshop on Robotics held on 12 March 2025. Signed: Director. Date.",
        "CERTIFICATE OF PARTICIPATION awarded for participating in the national marathon. Presented by "
        "the organising committee.",
    ],
    "Medical Records": [
        "Laboratory report. Patient name, age, sample date. Test, result, unit, reference range. "
        "Haemoglobin 12.8 g/dL. Fasting glucose 96 mg/dL. Cholesterol 182 mg/dL. Reviewed by pathologist.",
        "Prescription. Dr. Mehta, MBBS MD. Diagnosis: viral fever. Rx: paracetamol 500 mg twice daily for "
        "three days. Follow-up after one week. Discharge summary and doctor's notes.",
    ],
    "Research Papers": [
        "Abstract. We propose a novel method for image segmentation. 1 Introduction. Related work. 3 Method. "
        "4 Experiments: results on benchmark datasets show improved accuracy. 5 Conclusion. References [1] [2]",
        "Abstract—This paper studies the effect of temperature on crop yield using regression analysis. "
        "Keywords: agriculture, climate. I. INTRODUCTION ... REFERENCES",
    ],
    "Code": [
        "def main():\n    data = load()\n    for row in data:\n        print(row)\n\nif __name__ == '__main__':\n    main()",
        "#include <stdio.h>\nint main() {\n    int n, i;\n    scanf(\"%d\", &n);\n    for (i = 0; i < n; i++) "
        "printf(\"%d\\n\", i);\n    return 0;\n}",
        "public class Main { public static void main(String[] args) { System.out.println(\"Hello\"); } }",
    ],
    "Lists & To-dos": [
        "To do: buy groceries, pay rent, call the bank, finish the report by Monday, book train tickets.",
        "Quick notes - meeting at 5pm, wifi password in the drawer, return library books, gym tomorrow.",
        "Packing list: passport, charger, sunscreen, two shirts, toothbrush.",
    ],
}
