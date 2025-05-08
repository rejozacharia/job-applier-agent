# src/web_scraper.py
import requests
from bs4 import BeautifulSoup

def fetch_html_content(url):
    """Fetches HTML content from a given URL."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()  # Raise an exception for HTTP errors (4xx or 5xx)
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL {url}: {e}")
        return None

def parse_html_with_bs(html_content):
    """Parses HTML content using BeautifulSoup."""
    if not html_content:
        return None
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        return soup
    except Exception as e:
        print(f"Error parsing HTML: {e}")
        return None

def scrape_website_text(url):
    """
    Fetches and extracts all visible text from a website.
    This is a very basic text extraction.
    """
    html_content = fetch_html_content(url)
    if not html_content:
        return None
    
    soup = parse_html_with_bs(html_content)
    if not soup:
        return None
        
    # Get all text from the body
    # This will include script and style content if not handled carefully
    # For more precise extraction, specific tags or classes should be targeted.
    text_parts = soup.stripped_strings # More efficient than .get_text() for many cases
    return " ".join(text_parts) if text_parts else None

def scrape_linkedin_profile(linkedin_url):
    """
    Placeholder for LinkedIn profile scraping.
    LinkedIn is heavily protected against scraping.
    Direct scraping is unreliable and may violate ToS.
    This function will likely need to use an API or more advanced techniques.
    For now, it will just attempt a basic fetch.
    """
    print(f"Attempting to fetch LinkedIn profile (basic): {linkedin_url}")
    # Note: This basic fetch will likely be blocked or return login page.
    return scrape_website_text(linkedin_url) 

def scrape_job_description(url):
    """
    Fetches a job posting URL and attempts to extract the job description text.
    Uses heuristics to find common job description containers.
    """
    html_content = fetch_html_content(url)
    if not html_content:
        return None
    
    soup = parse_html_with_bs(html_content)
    if not soup:
        return None

    # Heuristics to find the job description container
    # These selectors might need to be expanded and refined over time.
    selectors = [
        "article.job-description",
        "div#job-description",
        "div.job-description",
        "div#jobDescription", # Common, e.g., on LinkedIn
        "div.jobDescription",
        "div.job-details-content",
        "div.job_description",
        "section.job-description",
        "div[class*='jobDescription']", # Class contains 'jobDescription'
        "div[id*='jobDescription']",   # ID contains 'jobDescription'
        "article[class*='job-description']",
        "article", # Generic fallback if more specific ones fail
        "main"     # Another generic fallback
    ]

    description_text = None
    for selector in selectors:
        try:
            # Handle both simple tag selectors and attribute selectors
            if '#' in selector or '.' in selector or '[' in selector:
                container = soup.select_one(selector)
            else: # Simple tag like 'article' or 'main'
                container = soup.find(selector)

            if container:
                # Get all text, trying to be smart about stripping unwanted tags
                # Remove script, style, nav, header, footer tags before extracting text
                for unwanted_tag in container.find_all(['script', 'style', 'nav', 'header', 'footer', 'aside', 'form']):
                    unwanted_tag.decompose()
                
                text_parts = container.stripped_strings
                description_text = " ".join(text_parts)
                if description_text and len(description_text) > 100: # Arbitrary length check for meaningful content
                    print(f"Found job description using selector: {selector}")
                    return description_text
            else:
                print(f"Job description container not found with selector: {selector}")
        except Exception as e:
            print(f"Error processing selector {selector}: {e}")
            continue
    
    if not description_text:
        print("Could not find a distinct job description container. Falling back to full page text.")
        return scrape_website_text(url) # Fallback to all text if specific container not found
# Example Job Description Scraping
    # Using a known job posting URL for testing (replace with a live one if needed, but be mindful of site terms)
    # For this example, let's use a generic structure that might be found on a simple job board.
    # A real test would require a more complex, live URL.
    # test_job_url = "https://jobs.example.com/listing/12345" # Replace with a real, simple job posting URL for testing
    # print(f"\n--- Scraping Job Description from: {test_job_url} ---")
    # job_desc_text = scrape_job_description(test_job_url)
    # if job_desc_text:
    #     print(f"Extracted Job Description (first 500 chars): {job_desc_text[:500]}...")
    # else:
    #     print("Failed to scrape job description.")
    print("\nNote: Job description scraping example is commented out. Provide a live URL for testing.")

    return description_text
if __name__ == "__main__":
    test_personal_site_url = "http://example.com" # A simple site for testing
    print(f"\n--- Scraping Personal Website: {test_personal_site_url} ---")
    personal_site_text = scrape_website_text(test_personal_site_url)
    if personal_site_text:
        print(f"Extracted Text (first 300 chars): {personal_site_text[:300]}...")
    else:
        print("Failed to scrape personal website.")

    # Example LinkedIn URL (will likely fail or show login page)
    test_linkedin_url = "https://www.linkedin.com/in/williamhgates" # Example public profile
    print(f"\n--- Scraping LinkedIn Profile: {test_linkedin_url} ---")
    linkedin_text = scrape_linkedin_profile(test_linkedin_url)
    if linkedin_text:
        print(f"Extracted Text (first 300 chars if successful): {linkedin_text[:300]}...")
    else:
        print("Failed to scrape LinkedIn profile (as expected with basic fetch).")