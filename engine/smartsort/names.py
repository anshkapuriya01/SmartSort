"""Folder names the model can choose from when naming a group of similar files.

An embedding model can't write words, so it names a group by picking the candidate whose
meaning best fits *every* file in the group and fits the other groups least. Which groups
exist, and what goes in them, comes only from the files' embeddings; these lists just give
the model natural folder names to choose from. Candidates are built by combining subject
areas with document forms ("Physics" + "Notes", "Food" + "Receipts"), plus some everyday
names, plus phrases from the files' own titles (see analyze.name_groups).
"""

# What a group can be about. Broad enough for anyone's files: home, money, work, study, hobbies.
AREAS = [
    # money & admin
    "Finance", "Banking", "Taxes", "Insurance", "Investments", "Loans", "Salary", "Bills",
    "Shopping", "Online Shopping", "Groceries", "Food", "Online Food", "Food Delivery",
    "Restaurant", "Utilities", "Electricity", "Rent", "Subscriptions", "Donations",
    # life
    "Travel", "Flight", "Train", "Hotel", "Cab", "Holiday", "Health", "Medical", "Dental",
    "Fitness", "Diet", "Family", "Kids", "School", "Pets", "Home", "Appliance", "Car",
    "Vehicle", "Legal", "Property", "Identity", "Career", "Job", "Wedding", "Events",
    "Personal", "Cooking", "Recipes", "Gardening", "Photography", "Music", "Art", "Movies",
    "Books", "Reading", "Sports", "Games", "Hobbies", "Volunteering", "Religion",
    # work
    "Work", "Business", "Marketing", "Sales", "Product", "Project", "Meeting", "Team",
    "Management", "Strategy", "Operations", "Human Resources", "Hiring", "Customer",
    "Client", "Support", "Design", "Brand", "Engineering", "Software", "Programming",
    "Python", "Web Development", "Mobile App", "Data", "Analytics", "Machine Learning",
    "Artificial Intelligence", "Cloud", "Security", "IT", "Research", "Consulting",
    "Accounting", "Legal Compliance", "Procurement", "Logistics", "Real Estate", "Startup",
    # study
    "Study", "Course", "College", "University", "Exam", "Physics", "Chemistry", "Biology",
    "Mathematics", "Calculus", "Algebra", "Statistics", "Computer Science",
    "Data Structures", "Algorithms", "Operating Systems", "Computer Networks", "Databases",
    "Electronics", "Electrical Engineering", "Mechanical Engineering", "Civil Engineering",
    "Economics", "History", "Geography", "Political Science", "Psychology", "Sociology",
    "Philosophy", "Literature", "English", "Languages", "Environmental Science",
    "Astronomy", "Medicine", "Nursing", "Pharmacy", "Law", "Architecture", "Education",
]

# What kind of document a group is made of.
FORMS = [
    "Notes", "Receipts", "Bills", "Invoices", "Orders", "Tickets", "Bookings", "Statements",
    "Reports", "Documents", "Records", "Papers", "Contracts", "Agreements", "Policies",
    "Letters", "Forms", "Certificates", "Manuals", "Guides", "Plans", "Lists", "Chapters",
    "Lab Manuals", "Assignments", "Slides", "Scripts", "Applications",
]

# Everyday names that don't come out of AREAS x FORMS.
EXTRA = [
    "Payslips", "Salary Slips", "Bank Statements", "Credit Card Statements", "Tax Returns",
    "Utility Bills", "Electricity Bills", "Phone Bills", "Online Food Orders",
    "Food Delivery Receipts", "Grocery Bills", "Restaurant Bills", "Online Orders",
    "Shopping Receipts", "Travel Tickets", "Flight Tickets", "Train Tickets", "Hotel Bookings",
    "Cab Rides", "Trip Itineraries", "Resumes", "Cover Letters", "Job Applications",
    "Course Certificates", "Offer Letters", "Non-Disclosure Agreements", "Rental Agreements",
    "Insurance Policies", "Medical Reports", "Blood Test Reports", "Prescriptions",
    "Appliance Manuals", "User Manuals", "Warranty Cards", "Meeting Notes",
    "Marketing Campaigns", "Business Reviews", "Quarterly Reports", "Research Papers",
    "Lecture Notes", "Textbook Chapters", "Exam Papers", "Question Papers", "Source Code",
    "To-do Lists", "Checklists", "Shopping Lists", "Journal", "Invitations", "Lab Manuals",
    "Lab Experiments", "Practicals", "Travel", "Bills & Payments", "Money", "Paperwork",
]


def specific_names() -> list[str]:
    names = list(EXTRA)
    for area in AREAS:
        names += [f"{area} {form}" for form in FORMS]
    seen, out = set(), []
    for n in names:
        if n.lower() not in seen:
            seen.add(n.lower())
            out.append(n)
    return out


def broad_names() -> list[str]:
    return AREAS + ["Receipts", "Bills & Payments", "Documents", "Reports", "Notes", "Study Notes",
                    "Coursework", "Paperwork", "Reference", "Admin"]
