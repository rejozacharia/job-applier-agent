# src/profile_consolidator.py
import re

# Basic regex for email and phone (can be improved)
EMAIL_REGEX = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
PHONE_REGEX = r"(\+\d{1,2}\s?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}" # North American focus

def extract_emails_from_text(text):
    """Extracts all unique emails from a given text."""
    if not text:
        return []
    return list(set(re.findall(EMAIL_REGEX, text)))

def extract_phones_from_text(text):
    """Extracts all unique phone numbers from a given text."""
    if not text:
        return []
    return list(set(re.findall(PHONE_REGEX, text)))

def consolidate_profile_data(resume_data, web_profile_data, db_profile_data):
    """
    Consolidates profile information from various sources.
    - resume_data: dict, output from parse_resume (e.g., {"raw_text": "..."})
    - web_profile_data: dict, e.g., {"linkedin_text": "...", "website_text": "..."}
    - db_profile_data: Profile model object or dict representation
    """
    consolidated = {
        "name": None, # Placeholder, name extraction is complex
        "emails": [],
        "phones": [],
        "linkedin_url": None,
        "website_url": None,
        "skills": [], # Placeholder
        "experience": [], # Placeholder
        "education": [], # Placeholder
        "conflicts": [] # List of detected conflicts
    }

    # --- Process DB Profile Data ---
    if db_profile_data:
        if hasattr(db_profile_data, 'default_email') and db_profile_data.default_email:
            consolidated["emails"].append(db_profile_data.default_email)
        if hasattr(db_profile_data, 'linkedin_url') and db_profile_data.linkedin_url:
            consolidated["linkedin_url"] = db_profile_data.linkedin_url
        if hasattr(db_profile_data, 'website_url') and db_profile_data.website_url:
            consolidated["website_url"] = db_profile_data.website_url
        # Add other fields from db_profile_data if they exist (e.g., name if we add it to Profile model)

    # --- Process Resume Data ---
    if resume_data and resume_data.get("raw_text"):
        resume_text = resume_data["raw_text"]
        consolidated["emails"].extend(extract_emails_from_text(resume_text))
        consolidated["phones"].extend(extract_phones_from_text(resume_text))
        # Future: Add extraction for name, skills, experience, education from resume_text

    # --- Process Web Profile Data ---
    if web_profile_data:
        linkedin_text = web_profile_data.get("linkedin_text")
        if linkedin_text:
            consolidated["emails"].extend(extract_emails_from_text(linkedin_text))
            consolidated["phones"].extend(extract_phones_from_text(linkedin_text))
            # Future: Add more structured extraction from LinkedIn

        website_text = web_profile_data.get("website_text")
        if website_text:
            consolidated["emails"].extend(extract_emails_from_text(website_text))
            consolidated["phones"].extend(extract_phones_from_text(website_text))
            # Future: Add more structured extraction from personal website

    # Make emails and phones unique
    consolidated["emails"] = sorted(list(set(e.lower() for e in consolidated["emails"] if e)))
    consolidated["phones"] = sorted(list(set(p for p in consolidated["phones"] if p)))

    # --- Basic Conflict Detection ---
    # Example: Conflict if multiple different primary emails are found (excluding DB default)
    # This is very simplistic and needs refinement.
    # For now, we'll just list all found items. User can pick.
    # A true conflict might be if resume email != db_profile.default_email
    
    # If db_profile_data.default_email exists and other emails are found from resume/web
    # that are different, it could be a conflict or just additional emails.
    db_email = getattr(db_profile_data, 'default_email', None)
    if db_email:
        other_emails = [e for e in consolidated["emails"] if e != db_email]
        if other_emails:
            consolidated["conflicts"].append({
                "field": "email",
                "db_value": db_email,
                "other_values": other_emails,
                "message": "Database email differs from or has additional emails found in other sources."
            })
    elif len(consolidated["emails"]) > 1:
         consolidated["conflicts"].append({
            "field": "email",
            "values": consolidated["emails"],
            "message": "Multiple emails found. User should select primary."
        })


    # Similar logic for phone, LinkedIn URL, etc. can be added.
    # For example, if db_profile_data.linkedin_url is set, but resume/web text implies a different one.

    return consolidated

if __name__ == "__main__":
    # Mock data for testing
    mock_resume_data = {
        "raw_text": "John Doe\njohn.doe@email.com\n123-456-7890\nlinkedin.com/in/johndoe\nSkills: Python, Java"
    }
    mock_web_data = {
        "linkedin_text": "John Doe - Contact: j.doe@company.com, 555-123-4567",
        "website_text": "About John Doe. Reach me at john@personal.site"
    }
    
    # Mock DB Profile (as if from SQLAlchemy model)
    class MockDBProfile:
        default_email = "john.doe@email.com"
        linkedin_url = "linkedin.com/in/johndoe"
        website_url = "johnpersonal.com" # Deliberate difference for testing

    mock_db_profile = MockDBProfile()

    print("--- Test Case 1: All data sources ---")
    consolidated1 = consolidate_profile_data(mock_resume_data, mock_web_data, mock_db_profile)
    import json
    print(json.dumps(consolidated1, indent=2))

    print("\n--- Test Case 2: Only resume and DB (no web) ---")
    consolidated2 = consolidate_profile_data(mock_resume_data, {}, mock_db_profile)
    print(json.dumps(consolidated2, indent=2))
    
    print("\n--- Test Case 3: Only resume ---")
    consolidated3 = consolidate_profile_data(mock_resume_data, {}, None)
    print(json.dumps(consolidated3, indent=2))

    print("\n--- Test Case 4: DB with different email ---")
    class MockDBProfileDiff:
        default_email = "john.official@work.com"
        linkedin_url = "linkedin.com/in/johndoe"
        website_url = "johnpersonal.com"
    consolidated4 = consolidate_profile_data(mock_resume_data, mock_web_data, MockDBProfileDiff())
    print(json.dumps(consolidated4, indent=2))