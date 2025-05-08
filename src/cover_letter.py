# src/cover_letter.py
import re

# Placeholder for user profile data structure
# In a real implementation, this would be populated from parsed resume, LinkedIn, etc.
# For now, we'll use dummy data for testing the generator.
DEFAULT_USER_PROFILE = {
    "name": "User Name",
    "contact": {
        "email": "user.email@example.com",
        "phone": "123-456-7890",
        "linkedin": "linkedin.com/in/yourprofile",
        "website": "yourwebsite.com"
    },
    "skills": ["Python", "Flask", "Selenium", "Web Scraping", "Data Analysis", "Project Management"],
    "experience": [
        {"title": "Software Developer", "company": "Tech Solutions", "years": 3, "summary": "Developed web applications using Python and Flask.", "keywords": ["python", "flask", "web development"]},
        {"title": "Junior Analyst", "company": "Data Insights", "years": 1, "summary": "Analyzed data and created reports.", "keywords": ["data analysis", "reporting"]}
    ],
    "education": [
        {"degree": "B.S. in Computer Science", "university": "State University"}
    ]
}

# Simple keyword extraction (can be improved with NLP libraries)
def extract_keywords_from_description(description):
    """Extracts potential keywords from job description."""
    # Simple approach: look for common skill words, tools, etc.
    # Convert to lowercase and remove punctuation for basic matching
    text = description.lower()
    text = re.sub(r"[^", "w\s]", "", text)
    words = set(text.split())
    # Add more sophisticated keyword extraction later (e.g., using NLTK, SpaCy)
    potential_keywords = ["python", "java", "c++", "javascript", "react", "angular", "vue", "node.js",
                          "flask", "django", "selenium", "playwright", "beautifulsoup", "requests",
                          "sql", "nosql", "mongodb", "postgresql", "mysql", "aws", "azure", "gcp",
                          "docker", "kubernetes", "git", "jira", "agile", "scrum",
                          "data analysis", "machine learning", "ai", "deep learning", "tensorflow", "pytorch",
                          "project management", "communication", "teamwork", "leadership"]
    found_keywords = [kw for kw in potential_keywords if kw in words or kw in text] # Check full text too for multi-word keys
    return list(set(found_keywords))

def find_matching_skills(user_skills, job_keywords):
    """Finds skills the user has that match the job keywords."""
    user_skills_lower = [skill.lower() for skill in user_skills]
    matches = [skill for skill in user_skills if skill.lower() in job_keywords]
    return matches

def generate_cover_letter(job_title, company_name, job_description, user_profile_data=None):
    """
    Generates a basic cover letter based on job details and user profile.
    user_profile_data should be the output from consolidate_profile_data or a similar dict.
    """

    # Use provided profile data, otherwise fallback to DEFAULT_USER_PROFILE for structure/defaults
    profile_to_use = user_profile_data if user_profile_data else DEFAULT_USER_PROFILE

    job_keywords = extract_keywords_from_description(job_description)
    
    # Skills handling:
    # The consolidated profile has 'skills' as a list directly.
    # DEFAULT_USER_PROFILE also has 'skills' as a list.
    skills_list = profile_to_use.get("skills", [])
    matching_skills = find_matching_skills(skills_list, job_keywords)

    # Basic Template Structure
    letter = f"Dear Hiring Manager,\n\n"
    letter += f"I am writing to express my strong interest in the {job_title} position at {company_name}, as advertised [mention where you saw the ad - placeholder]. "
    
    # Experience handling:
    # The consolidated profile has 'experience' as a list of dicts.
    # DEFAULT_USER_PROFILE also has 'experience' as a list of dicts.
    experience_list = profile_to_use.get("experience", [])
    
    # Try to pick a relevant background phrase
    # This is still very basic and could be improved by analyzing experience titles or summaries.
    background_phrase = "my professional background"
    if experience_list:
        # Example: use the title of the first experience entry if available
        first_exp_title = experience_list[0].get("title")
        if first_exp_title:
            background_phrase = f"my background as a {first_exp_title}"
        elif skills_list: # Fallback to a key skill
             background_phrase = f"my background in {skills_list[0]}"


    letter += f"With {background_phrase} and experience utilizing technologies relevant to this role, I am confident I possess the skills and qualifications necessary to make a significant contribution to your team.\n\n"

    # Highlight matching skills
    if matching_skills:
        skills_str = ", ".join(matching_skills)
        letter += f"The job description emphasizes the need for skills such as {', '.join(job_keywords[:3]) if job_keywords else 'relevant technical abilities'}. "
        letter += f"My technical skills include {skills_str}, which align well with these requirements. "
        
        if experience_list:
            relevant_exp = None
            for exp in experience_list:
                exp_summary_lower = exp.get("summary", "").lower()
                exp_keywords_lower = [k.lower() for k in exp.get("keywords", [])]
                # Check if any matching skill is in summary or keywords of the experience
                if any(skill.lower() in exp_summary_lower for skill in matching_skills) or \
                   any(skill.lower() in exp_keywords_lower for skill in matching_skills):
                    relevant_exp = exp
                    break
            if relevant_exp:
                letter += f"For instance, in my role as {relevant_exp.get('title', 'a previous position')} at {relevant_exp.get('company', 'a past company')}, I {relevant_exp.get('summary', 'gained valuable experience.')} "
        letter += "\n\n"
    else:
        letter += "My experience in [mention relevant field/experience] has equipped me with a strong foundation in [mention key skill area]. \n\n"

    # Why this company (generic placeholder)
    letter += f"I am particularly drawn to {company_name} because of [mention specific reason - e.g., company mission, recent project, company culture - requires research or generic statement]. "
    letter += "I am eager to apply my skills in a challenging and rewarding environment like yours.\n\n"

    # Conclusion
    letter += "Thank you for considering my application. I have attached my resume for your review and welcome the opportunity to discuss my qualifications further.\n\n"
    letter += "Sincerely,\n"
    
    # Contact Information from profile_to_use
    # The consolidated profile has 'name', 'emails' (list), 'phones' (list), 'linkedin_url', 'website_url'
    user_name = profile_to_use.get('name', DEFAULT_USER_PROFILE.get('name', 'Your Name')) # Fallback chain
    
    primary_email = ""
    if profile_to_use.get("emails"): # Check if 'emails' list exists and is not empty
        primary_email = profile_to_use["emails"][0]
    elif 'contact' in profile_to_use and 'email' in profile_to_use['contact']: # Fallback to DEFAULT_USER_PROFILE structure
        primary_email = profile_to_use['contact']['email']
    else: # Ultimate fallback
        primary_email = DEFAULT_USER_PROFILE.get('contact', {}).get('email', '')

    primary_phone = ""
    if profile_to_use.get("phones"): # Check if 'phones' list exists and is not empty
        primary_phone = profile_to_use["phones"][0]
    elif 'contact' in profile_to_use and 'phone' in profile_to_use['contact']: # Fallback to DEFAULT_USER_PROFILE structure
        primary_phone = profile_to_use['contact']['phone']
    else: # Ultimate fallback
        primary_phone = DEFAULT_USER_PROFILE.get('contact', {}).get('phone', '')

    linkedin_url = profile_to_use.get('linkedin_url', DEFAULT_USER_PROFILE.get('contact', {}).get('linkedin'))

    letter += f"{user_name}\n"
    if primary_email:
        letter += f"{primary_email}\n"
    if primary_phone:
        letter += f"{primary_phone}\n"
    if linkedin_url:
        letter += f"{linkedin_url}\n"
        
    # Website URL is not typically in a signature but could be added if desired.
    # website_url = profile_to_use.get('website_url', DEFAULT_USER_PROFILE.get('contact', {}).get('website'))
    # if website_url:
    #     letter += f"{website_url}\n"

    return letter

# Example Usage (for testing)
if __name__ == "__main__":
    test_job_title = "Senior Python Developer"
    test_company = "FutureTech Solutions"
    test_description = """
    FutureTech Solutions is seeking an experienced Senior Python Developer to join our dynamic team.
    The ideal candidate will have extensive experience with Flask, Django, and cloud platforms like AWS.
    Responsibilities include designing and implementing scalable web services, working with PostgreSQL databases,
    and leading a team of junior developers. Strong knowledge of microservices architecture, Docker, and Kubernetes is essential.
    We value excellent communication and problem-solving skills. Experience with data analysis or machine learning is a plus.
    """

    # Simulate a consolidated profile
    mock_consolidated_profile = {
        "name": "Jane Doe",
        "emails": ["jane.doe@example.com", "j.doe@personal.co"],
        "phones": ["(555) 123-4567"],
        "linkedin_url": "linkedin.com/in/janedoe",
        "website_url": "janedoe.dev",
        "skills": ["Python", "Flask", "Django", "AWS", "PostgreSQL", "Docker", "Kubernetes", "Microservices", "Leadership", "Problem-solving"],
        "experience": [
            {
                "title": "Lead Software Engineer",
                "company": "Innovate LLC",
                "summary": "Led a team to develop and deploy microservices using Python, Flask, and Docker on AWS. Managed project timelines and mentored junior engineers.",
                "keywords": ["python", "flask", "aws", "docker", "leadership", "microservices"]
            },
            {
                "title": "Software Developer",
                "company": "OldTech Corp",
                "summary": "Developed and maintained web applications using Django and PostgreSQL. Contributed to API design and database optimization.",
                "keywords": ["python", "django", "postgresql", "api development"]
            }
        ],
        "education": [
            {"degree": "M.S. in Software Engineering", "university": "Tech Institute"}
        ]
    }

    print("--- Generating letter with MOCK consolidated profile ---")
    generated_letter_mock = generate_cover_letter(test_job_title, test_company, test_description, user_profile_data=mock_consolidated_profile)
    print(generated_letter_mock)

    print("\n--- Generating letter with DEFAULT profile (fallback) ---")
    generated_letter_default = generate_cover_letter(test_job_title, test_company, test_description) # No user_profile_data passed
    print(generated_letter_default)

