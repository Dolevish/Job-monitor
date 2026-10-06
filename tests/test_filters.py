import yaml
import pytest

from monitor.filters import Filters, required_years, requirements
from monitor.models import Job

CFG = yaml.safe_load(open("config.yaml", encoding="utf-8"))["filters"]
F = Filters(CFG)


def job(title, desc="", loc="Tel Aviv, Israel", israel=None):
    return Job("t:x", "1", "Acme", title, "https://x", loc, desc, israel=israel)


def test_years_english_and_hebrew():
    assert required_years("Requirements:\n• 3+ years of experience in C") == (3, None)
    assert required_years("• 0-2 years of professional or internship experience") == (0, 2)
    assert required_years("• At least two years of experience with Linux") == (2, None)
    assert required_years("• 1-2 שנות ניסיון בפיתוח C") == (1, 2)
    assert required_years("• שנת ניסיון לפחות בפיתוח") == (1, None)
    assert required_years("• B.Sc. in EE (4 years)") is None


def test_years_ignores_optional_lines_and_sections():
    assert required_years("• 5 years of experience with RTOS - an advantage") is None
    assert required_years("Nice to have:\n• 4+ years of experience in networking") is None
    text = "Requirements:\n• 1 year of experience in C\nAdvantages:\n• 5 years of experience"
    assert required_years(text) == (1, None)
    assert required_years("Our company has over 30 years of experience in defense") is None


def test_takes_the_largest_mandatory_requirement():
    text = "Requirements:\n• 1+ years of experience in Python\n• 3+ years of experience in C"
    assert required_years(text) == (3, None)


def test_title_rules():
    assert F.title_ok("Embedded Software Engineer")
    assert F.title_ok("Firmware Engineer")
    assert F.title_ok("Software Engineer - Networking")
    assert F.title_ok("Junior Software Engineer")
    assert F.title_ok("C++ Software Engineer")
    assert F.title_ok("מהנדס/ת תוכנה משובצת")
    assert not F.title_ok("Senior Embedded Software Engineer")
    assert not F.title_ok("Software Engineer")            # general title without a junior marker
    assert not F.title_ok("Junior Hardware Engineer")
    assert not F.title_ok("Firmware QA Engineer")
    assert not F.title_ok("Embedded Software Student")
    assert not F.title_ok("Embedded Team Lead")


def test_location():
    assert F.location_ok(job("x", loc="Yokneam, Israel"))
    assert F.location_ok(job("x", loc="Haifa, ISR"))
    assert F.location_ok(job("x", loc="Chicago, IL")) is False
    assert F.location_ok(job("x", loc="2 Locations")) is None
    assert F.location_ok(job("x", loc="2 Locations", israel=True))


def test_classify_decisions():
    assert F.classify(job("Embedded Software Engineer", "• 3+ years of experience")).status == "reject"
    assert F.classify(job("Embedded Software Engineer", "• 1-2 years of experience in C")).status == "reject"
    v = F.classify(job("C++ Software Engineer",
                       "• 1-2 years of experience\nTop-tier fresh graduates welcome"))
    assert v.status == "match" and v.grad_friendly
    assert F.classify(job("Firmware Engineer", "• 0-3 years of experience")).status == "match"
    assert F.classify(job("Firmware Engineer", "• B.Sc. in EE\n• C/C++")).status == "review"
    assert F.classify(job("Junior Embedded Engineer", "• C programming")).status == "match"
    assert F.classify(job("Firmware Engineer", "x", loc="Austin, TX")).status == "reject"
    amb = job("Firmware Engineer", "Location: Yokneam, Israel\n• B.Sc.", loc="2 Locations")
    assert F.classify(amb).status == "review"


def test_requirements_section():
    text = ("About the role:\nBuild things.\nRequirements:\n• B.Sc. in EE/CS\n• Strong C\n"
            "• Linux\nAdvantages:\n• RTOS")
    assert requirements(text) == ["B.Sc. in EE/CS", "Strong C", "Linux"]


@pytest.mark.parametrize("degree", ["PhD", "Ph.D.", "M.Sc.", "MSc", "Master's degree",
                                   "Master of Science", "MS degree", "תואר שני", "דוקטורט"])
def test_required_postgraduate_degree_rejected(degree):
    v = F.classify(job("Junior Firmware Engineer", f"Requirements:\n• {degree} in EE is required"))
    assert v.status == "reject" and v.reason.startswith("required degree")


@pytest.mark.parametrize("desc", [
    "Requirements:\n• B.Sc. or M.Sc. in EE",
    "Requirements:\n• B.Sc./M.Sc. in EE",
    "Requirements:\n• M.Sc. or B.Sc. in EE",
    "Requirements:\n• B.Sc. in EE\nPreferred Qualifications:\n• PhD in EE",
    "Requirements:\n• M.Sc. preferred",
    "Requirements:\n• תואר שני יתרון",
    "Responsibilities:\n• Work with PhD researchers",
    "Requirements:\n• Knowledge of MS Office and master Linux tools",
])
def test_optional_degrees_and_bachelor_alternatives_allowed(desc):
    assert F.classify(job("Junior Embedded Engineer", desc)).status == "match"


def test_degree_titles_and_joint_requirements():
    assert not F.title_ok("System Engineer – PhD Graduates")
    assert F.title_ok("Graduate Firmware Engineer (B.Sc./M.Sc.)")
    assert F.title_ok("Firmware Engineer (M.Sc. preferred)")
    assert F.classify(job("Junior Firmware Engineer",
                          "Requirements:\n• B.Sc. in EE/CS and M.Sc. required")).status == "reject"
    assert F.classify(job("Junior Firmware Engineer", "• MSc in Electrical Engineering")).status == "reject"


def test_adjacent_graduate_roles_require_review_without_weakening_experience_rules():
    assert F.classify(job("Outstanding Graduate - Machine Learning Engineer", "• B.Sc.")).reason == "adjacent field"
    assert F.classify(job("Graduate Algorithm Developer", "• 3 years of experience")).status == "reject"
    assert F.classify(job("Junior Embedded Machine Learning Engineer", "• B.Sc.")).status == "match"
