from datetime import datetime


def fill_form_based_resume(url: str, candidate_resume_and_answers: str):
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"""
    Please view the form and then work to fill in the form based on a given candidate resume.

    1. First, navigate to {url}
    2. Review the fields and determine the text to fill in each field based on the candidate resume and answers:
    {candidate_resume_and_answers}
    3. Fill in each field with human click, type, and move to next field. Do not do it instantly.    
    4. Do not submit the form, just fill it in, then take a full page screenshot and save it to:
    ./screenshots/{url.replace("https://", "").replace("/", "_")}-{timestamp}.png
    """
