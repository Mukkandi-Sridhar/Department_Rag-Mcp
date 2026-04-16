import sys
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.firebase_app import get_firestore_client, validate_service_account_file


COLLEGE = "R G M College of Engineering & Technology"


FACULTY = [
    {
        "faculty_id": "g_kishor_kumar",
        "name": "Dr. G. Kishor Kumar",
        "role": "hod",
        "designation": "Professor",
        "department": "Computer Science & Engineering",
        "college": COLLEGE,
        "date_of_birth": "1980-04-15",
        "date_of_joining": "2007-11-19",
        "experience_text": "14.9 years",
        "experience_years": 14.9,
        "email": "kishorgulla@yahoo.co.in",
        "phone": "+91 8897272089",
        "qualifications": [
            {
                "degree": "Ph.D",
                "specialization": "CSE",
                "class": None,
                "marks_percent": None,
                "year": 2017,
                "institution": "JNTUA, Anantapuramu",
            },
            {
                "degree": "M.Tech",
                "specialization": "CSE",
                "class": "First Class",
                "marks_percent": 68.0,
                "year": 2005,
                "institution": "JNTUA, Anantapuramu",
            },
            {
                "degree": "B.Tech",
                "specialization": "CSE",
                "class": "Second Class",
                "marks_percent": 57.80,
                "year": 2002,
                "institution": "RGMCET",
            },
        ],
        "research_publications": {
            "text_books": 1,
            "book_chapters": 1,
            "international_journals": 15,
            "sci": 1,
            "esci": 1,
            "scopus": 3,
            "international_conferences": 4,
            "national_journals": 0,
            "workshops_conferences_symposia": 24,
            "sponsored_projects_ongoing": 0,
            "sponsored_projects_completed": 0,
        },
        "memberships_roles": [
            "Member, Board of Studies in CSE at JNTUA Anantapuramu",
            "Member, IEEE, Membership No: 92178108",
            "Member IEAE, Membership No: IEAE2017729",
            "Member, Academic Council at RGM College of Engineering & Technology, Nandyal",
            "Member, Board of Studies at RGM College of Engineering & Technology, Nandyal",
            "In-charge of Remote Center associated with IIT Bombay",
            "In-charge of Spoken Tutorial Project associated with IIT Bombay",
            "Lead for Leading India Project associated with Bennett University, Noida",
        ],
        "organized_events_count": 20,
        "awards": [
            "Research Excellence Award, 2017",
            "Bharat Vikas Award, 2017",
            "Reviewer for IEEE Access",
            "Reviewer for Journal of Concurrency and Computation",
        ],
        "courses": [
            "Machine Learning",
            "Information Retrieval Systems",
            "Information Security",
            "Data Mining and Warehousing",
            "Soft Computing",
            "Unix and Shell Programming",
            "C Programming",
            "Operating Systems",
            "Pattern Recognition",
            "Data Structures",
        ],
    },
    {
        "faculty_id": "ch_srilakshmi_prasanna",
        "name": "Dr. Ch. Srilakshmi Prasanna",
        "role": "faculty",
        "designation": "Assistant Professor",
        "department": "CSE (AI & ML)",
        "college": COLLEGE,
        "date_of_birth": "1986-06-20",
        "date_of_joining": "2025-12-01",
        "experience_text": "9.5 years",
        "experience_years": 9.5,
        "email": "srilakshmi1023@gmail.com",
        "phone": "+91 8099248328",
        "qualifications": [
            {
                "degree": "Ph.D",
                "specialization": "CSE",
                "class": None,
                "marks_percent": None,
                "year": 2025,
                "institution": "JNTUA, Anantapuramu",
            },
            {
                "degree": "M.Tech",
                "specialization": "CSE",
                "class": "Distinction",
                "marks_percent": 76.14,
                "year": 2014,
                "institution": "JNTUACEP Pulivendula",
            },
            {
                "degree": "B.Tech",
                "specialization": "CSE",
                "class": "Second Class",
                "marks_percent": 55.0,
                "year": 2008,
                "institution": "G Pulla Reddy Engineering College",
            },
        ],
        "research_publications": {
            "text_books": 0,
            "book_chapters": 0,
            "international_journals": 19,
            "sci": 1,
            "scopus": 5,
            "international_conferences": 1,
            "national_journals": 0,
            "workshops_conferences_symposia": 48,
            "research_funding_projects_ongoing": 0,
            "research_funding_projects_completed": 0,
            "patents": 1,
            "consultancy_works_ongoing": 0,
            "consultancy_works_completed": 0,
        },
        "memberships_roles": [
            "Coordinator - NAAC Criterion 5 and NBA Criterion 3",
            "Coordinator - Internships, Eduskills, IIT Bombay Spoken Tutorials, NPTEL, and R&D",
            "Board of Studies member - Department of CSE",
            "Organizer for FDPs, workshops, and departmental events",
            "Life Member, International Association of Engineers, Member ID: 154476",
            "Member, Universal Association of Computer and Electronics Engineers, ID: AM1010004162",
        ],
        "organized_events_count": 4,
        "awards": [
            "Blue Prism Foundation Educator - Robotic Process Automation, 2023",
            "AWS Academy Educator - Cloud Foundations and Solutions Architect, 2023",
            "Android Developer Educator Development Program, 2023",
            "Appreciation from IIT Bombay for Spoken Tutorial coordination, 2024",
            "GATE Qualified, CSE",
        ],
        "courses": [
            "Operating Systems",
            "Computer Networks",
            "Artificial Intelligence",
            "Cloud Computing",
            "Python Programming",
            "Deep Learning",
            "Big Data Analytics",
            "R Programming",
            "Exploratory Data Analysis using R and Python",
        ],
    },
    {
        "faculty_id": "g_chandana_swathi",
        "name": "Dr. G. Chandana Swathi",
        "role": "faculty",
        "designation": "Assistant Professor",
        "department": "CSE (AI & ML)",
        "college": COLLEGE,
        "date_of_birth": "1986-06-01",
        "date_of_joining": "2025-11-01",
        "experience_text": "5.9 years",
        "experience_years": 5.9,
        "email": "gchandanaswathi@gmail.com",
        "phone": "+91 9281409828",
        "qualifications": [
            {
                "degree": "Ph.D",
                "specialization": "CSE",
                "class": None,
                "marks_percent": None,
                "year": 2025,
                "institution": "JNTUA, Anantapuramu",
            },
            {
                "degree": "M.Tech",
                "specialization": "SE",
                "class": "Distinction",
                "marks_percent": 83.0,
                "year": 2015,
                "institution": "ECET, Hyderabad",
            },
            {
                "degree": "B.Tech",
                "specialization": "CSE",
                "class": "First Class",
                "marks_percent": 72.0,
                "year": 2007,
                "institution": "RGMCET, Nandyal",
            },
        ],
        "research_publications": {
            "text_books": 1,
            "book_chapters": 0,
            "international_journals": 6,
            "sci": 1,
            "scopus": 3,
            "international_conferences": 2,
            "national_journals": 0,
            "workshops_conferences_symposia": 5,
            "research_funding_projects_ongoing": 0,
            "research_funding_projects_completed": 0,
            "patents": 1,
            "consultancy_works_ongoing": 0,
            "consultancy_works_completed": 0,
        },
        "memberships_roles": [],
        "organized_events_count": 0,
        "awards": [],
        "courses": [
            "Software Engineering",
            "Computer Networks",
            "Mobile Ad-hoc Networks",
            "Principles of Programming Language",
        ],
    },
    {
        "faculty_id": "p_arun_babu",
        "name": "Mr. P. Arun Babu",
        "role": "faculty",
        "designation": "Assistant Professor",
        "department": "Computer Science & Engineering",
        "college": COLLEGE,
        "date_of_birth": "1998-09-07",
        "date_of_joining": "2011-12-07",
        "experience_text": "7.10 years",
        "experience_years": 7.10,
        "email": "arunbabu1208@gmail.com",
        "phone": "+91 9703044883",
        "qualifications": [
            {
                "degree": "Ph.D",
                "specialization": "CSE",
                "class": None,
                "marks_percent": None,
                "year": None,
                "institution": "KL University Vijayawada",
                "status": "Pursuing",
            },
            {
                "degree": "M.Tech",
                "specialization": "SWE",
                "class": "First Class",
                "marks_percent": 67.8,
                "year": 2011,
                "institution": "JNTUA, Anantapur",
            },
            {
                "degree": "B.Tech",
                "specialization": "CSE",
                "class": "Second Class",
                "marks_percent": 55.60,
                "year": 2009,
                "institution": "JNTUA, Anantapur",
            },
        ],
        "research_publications": {
            "text_books": 0,
            "book_chapters": 0,
            "international_journals": 1,
            "esci": 0,
            "scopus": 1,
            "international_conferences": 2,
            "national_journals": 0,
            "workshops_conferences_symposia": 15,
            "sponsored_projects_ongoing": 0,
            "sponsored_projects_completed": 0,
        },
        "memberships_roles": [],
        "organized_events_count": 2,
        "awards": [],
        "courses": [],
    },
    {
        "faculty_id": "chakrapani",
        "name": "Dr. Chakrapani",
        "role": "faculty",
        "designation": "Assistant Professor",
        "department": "CSE (AI & ML)",
        "college": COLLEGE,
        "date_of_birth": "1993-08-20",
        "date_of_joining": "2025-12-01",
        "experience_text": "1.7 years",
        "experience_years": 1.7,
        "email": "chakrapaniaiml@rgmcet.edu.in",
        "phone": "+91 9080338744",
        "qualifications": [
            {
                "degree": "Ph.D",
                "specialization": None,
                "class": None,
                "marks_percent": None,
                "year": 2024,
                "institution": "VIT University, Chennai",
            },
            {
                "degree": "M.Tech",
                "specialization": None,
                "class": "Distinction",
                "marks_percent": 84.70,
                "year": 2019,
                "institution": "VIT University, Chennai",
            },
            {
                "degree": "B.Tech",
                "specialization": None,
                "class": "Distinction",
                "marks_percent": 71.33,
                "year": 2016,
                "institution": "JNTU, Ananthapuram",
            },
        ],
        "research_publications": {
            "text_books": 0,
            "book_chapters": 0,
            "international_journals": 12,
            "esci": 9,
            "scopus": 3,
            "international_conferences": 0,
            "national_journals": 0,
            "workshops_conferences_symposia": 5,
            "research_funding_projects_ongoing": 0,
            "research_funding_projects_completed": 0,
            "patents": 0,
            "consultancy_works_ongoing": 0,
            "consultancy_works_completed": 0,
        },
        "memberships_roles": [],
        "organized_events_count": 0,
        "awards": [],
        "courses": [
            "Deep Learning",
            "Robotics & Automation",
            "Artificial Intelligence",
            "Machine Learning",
        ],
    },
]


def main() -> None:
    try:
        from google.api_core.exceptions import GoogleAPIError, PermissionDenied
    except ImportError:
        GoogleAPIError = Exception
        PermissionDenied = Exception

    validate_service_account_file()
    db = get_firestore_client()

    try:
        for faculty in FACULTY:
            db.collection("faculty").document(faculty["faculty_id"]).set(faculty)
    except PermissionDenied as exc:
        raise RuntimeError(
            "Firestore permission denied. Check the service account and Firestore API."
        ) from exc
    except GoogleAPIError as exc:
        raise RuntimeError(f"Faculty import failed: {exc}") from exc

    print(f"Imported {len(FACULTY)} faculty records into Firestore.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(f"Import failed: {exc}")
        raise SystemExit(1)
