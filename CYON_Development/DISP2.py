import os
import json
import re
from openai import OpenAI, RateLimitError, APIError, APIConnectionError
import functions_framework
from flask import request, jsonify

# --- FIXED: Initialize Client and Regex at the global scope ---
# This runs when the container instance loads, not during the first request.
# This makes the "cold start" (first request) processing faster.
try:
    API_KEY = os.environ.get("OPENAI_API_KEY")
    if not API_KEY:
        raise EnvironmentError("OPENAI_API_KEY environment variable is not set.")
    CLIENT = OpenAI(api_key=API_KEY)
except EnvironmentError as e:
    print(f"FATAL: {e}")
    CLIENT = None # Set to None so a check will fail

# --- FIXED: Compile the regex pattern once at the global scope ---
# This is more efficient than compiling it inside the function every time.
HOVER_PATTERN = re.compile(r'\[([^:]+):([^\]]+)\]')

# --- STAGE 1: Data Mapping ---
# Helper function to convert Qualtrics codes into human-readable text
def map_responses(data):
    """Maps Qualtrics' numeric answers to meaningful strings for the AI prompt."""
    mappings = {
        'DEM1': {'1': 'Female', '2': 'Male', '3': 'Non-binary / third gender', '4': 'Prefer not to say'},
        'DEM3': {'1': '8th grade or less', '2': 'Some high school, no diploma', '3': 'High school graduate or GED', '4': 'Some college, no degree', '5': 'Associate’s degree', '6': 'Bachelor’s degree', '7': 'Graduate or professional degree'},
        'DEM4': {'1': 'Under $10,000', '2': '$10,000 to $14,999', '3': '$15,000 to $24,999', '4': '$25,000 to $34,999', '5': '$35,000 to $49,999', '6': '$50,000 to $74,999', '7': '$75,000 to $99,999', '8': '$100,000 to $124,999', '9': '$125,000 to $149,000', '10': '$150,000 to $199,999', '11': '$200,000 or more'},
        'DEM5': {'1': 'Caucasian/White', '2': 'African American/Black', '3': 'Hispanic/Latino', '4': 'Asian', '5': 'American Indian/Alaskan Native', '6': 'Native Hawaiian/Pacific Islander', '7': 'Other'},
        'DEM7': {'1': 'Very liberal', '2': 'Liberal', '3': 'Somewhat liberal', '4': 'Moderate', '5': 'Somewhat conservative', '6': 'Conservative', '7': 'Very conservative'},
        'DEM8': {'1': 'Democrat', '2': 'Republican', '3': 'Independent'},
        'VOT2': {'1': 'The Democratic candidate (Kamala Harris)', '2': 'The Republican candidate (Donald Trump)', '3': 'Another candidate'},
        'CCP1_1': {
            '1': 'Strongly opposes U.S. withdrawal from Paris Agreement',
            '2': 'Opposes U.S. withdrawal from Paris Agreement',
            '3': 'Somewhat opposes U.S. withdrawal from Paris Agreement',
            '4': 'Neutral on U.S. withdrawal from Paris Agreement',
            '5': 'Somewhat supports U.S. withdrawal from Paris Agreement',
            '6': 'Supports U.S. withdrawal from Paris Agreement',
            '7': 'Strongly supports U.S. withdrawal from Paris Agreement'
        }
    }

    profile = {
        "Gender": mappings['DEM1'].get(data.get('DEM1'), "Not specified"),
        "Age": data.get('DEM2', "Not specified"),
        "Education": mappings['DEM3'].get(data.get('DEM3'), "Not specified"),
        "Income": mappings['DEM4'].get(data.get('DEM4'), "Not specified"),
        "Race/Ethnicity": mappings['DEM5'].get(data.get('DEM5'), "Not specified"),
        "Political Stance": mappings['DEM7'].get(data.get('DEM7'), "Not specified"),
        "Party Affiliation": mappings['DEM8'].get(data.get('DEM8'), "Not specified"),
        "2024 Vote": mappings['VOT2'].get(data.get('VOT2'), "Not specified"),
        "Paris Agreement Stance": mappings['CCP1_1'].get(data.get('CCP1_1'), "Neutral on U.S. withdrawal from Paris Agreement")
    }
    return profile

# --- STAGE 2: Prompt Engineering ---
def create_prompt(profile):
    """Creates the detailed prompt for the GPT-4o model."""

    system_prompt = """
    Your task is to generate a short news article about the Trump administration's climate policies.
    Begin with the sentence:
    “The Trump administration announced the U.S. withdrawal from the Paris Agreement in January 2025. This decision comes with far-reaching implications.”

    Strictly follow these rules for the output:
    1.  Profile Context:
    Analyze the user's profile to infer their likely stance on climate change.
    2.  Persona Generation:
    Simulate the persona of an American adult who holds the opposite stance on climate change from that inferred from the profile.
    Do NOT mention or refer to the “user,” "profile group," “AI,” or “simulated persona” in the article itself.
    3.  Article Structure (logically connected to the opening sentence):
    1) Part 1 (THE FIRST PARAGRAPH IN ORDER): 
    A news-style paragraph reporting how the user's (ideological or partisan) profile group interprets and evaluates the simulated persona group's opinions or arguments on climate policy, AND why they do so.
    2) Part 2 (THE SECOND PARAGRAPH IN ORDER — following Part 1): 
    A counterargument paragraph describing how the simulated persona's (ideological or partisan) group interprets and evaluates the user profile group's opinions or arguments on climate policy, AND why they do so.
    4.  Tone Requirement: 
    Must use plain, respectful language.
    5.  Length:
    The article must be between 150 and 180 words in total.
    6.  Headline:
    Include a typical online news-style headline that highlights how opposing groups view and interpret each other's perspectives on the issue.
    7.  Include exactly four external news source labels within the text. Format them like [LABEL:Tooltip text]. For example: [Source: Pew Research Center, Nov 7, 2024]. Do not include actual hyperlinks.
    8.  Your final output must be a valid JSON object with three keys: "headline", "body", and "persona_adopted". The "persona_adopted" key should briefly state the persona you chose (e.g., "Conservative, skeptical of climate regulations").
    """

    user_prompt = f"Here is the survey participant's profile: {json.dumps(profile)}. Generate the news article based on these details and the rules provided."
    
    return system_prompt, user_prompt

# --- STAGE 3: API Call and Response Formatting ---
def format_body_with_hovers(text_body):
    """Converts [LABEL:Tooltip] syntax into HTML for Qualtrics."""
    def replacer(match):
        label = match.group(1)
        tooltip = match.group(2)
        # Using a standard span structure for easy integration into an HTML/Qualtrics context
        return f'<span class="source-label">{label}<span class="source-tooltip">{tooltip}</span></span>'
    
    # --- FIXED: Use the globally compiled regex pattern ---
    return HOVER_PATTERN.sub(replacer, text_body)

# The function entry point, required for Google Cloud Functions
@functions_framework.http
def generate_news_endpoint(request):
    """The main entry point for the Cloud Function.
    
    This function handles the cross-origin preflight request (OPTIONS) and the
    main POST request to generate the news article using the OpenAI API.
    """
    
    # 1. Handle CORS Preflight Request (for Qualtrics/Web Access)
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '3600'
        }
        return ('', 204, headers)

    # Set standard CORS headers for the response
    headers = {'Access-Control-Allow-Origin': '*'}
    
    try:
        # --- FIXED: Check if global client failed to initialize ---
        if CLIENT is None:
            raise EnvironmentError("OPENAI_API_KEY is not set or client failed to initialize.")
        
        request_data = request.get_json(silent=True)
        if not request_data:
            return (jsonify({"error": "Missing JSON payload in request."}), 400, headers)
            
        participant_profile = map_responses(request_data)
        system_prompt, user_prompt = create_prompt(participant_profile)
        
        # 2. Call OpenAI API
        completion = CLIENT.chat.completions.create(
            model="ft:gpt-4o-2024-08-06:personal::A8vV3mNd",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            response_format={"type": "json_object"},
            # --- NEW: Add a server-side timeout ---
            # This is crucial. It ensures your function fails gracefully
            # if the OpenAI API hangs, *before* your JavaScript times out.
            # Set this to be *less* than your JavaScript timeout (e.g., 40s).
            timeout=40.0 
        )
        
        # 3. Process Response
        response_json_string = completion.choices[0].message.content
        response_data = json.loads(response_json_string)
        
        headline = response_data.get("headline", "No Headline")
        body_raw = response_data.get("body", "No content generated.")
        body_formatted = format_body_with_hovers(body_raw)
        
        final_response = {
            "headline": headline,
            "body": body_formatted,
            "debug_info": {
                "profile": participant_profile
            }
        }
        
        # 4. Return Formatted JSON Response
        return (jsonify(final_response), 200, headers)

    # --- NEW: Add specific OpenAI error handling ---
    except RateLimitError as e:
        error_message = {"error": "OpenAI API rate limit exceeded.", "message": str(e)}
        print(f"RateLimitError: {e}")
        return (jsonify(error_message), 429, headers) # 429 Too Many Requests

    except APIConnectionError as e:
        error_message = {"error": "Could not connect to OpenAI API.", "message": str(e)}
        print(f"APIConnectionError: {e}")
        return (jsonify(error_message), 503, headers) # 503 Service Unavailable

    except APIError as e:
        error_message = {"error": "OpenAI API returned an error.", "message": str(e)}
        print(f"APIError: {e}")
        return (jsonify(error_message), 502, headers) # 502 Bad Gateway
    # --- END NEW ---

    except EnvironmentError as ee:
        # Catch specific configuration errors
        error_message = {"error": str(ee), "message": "Server configuration error."}
        print(f"Configuration Error: {ee}")
        return (jsonify(error_message), 500, headers)

    except Exception as e:
        # Catch all other errors
        error_message = {"error": str(e), "message": "An internal server error occurred."}
        print(f"Error processing request: {e}") 
        return (jsonify(error_message), 500, headers)
