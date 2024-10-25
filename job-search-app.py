import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
from urllib.parse import quote, urlparse
import re
import time
import random
import cachetools.func
from datetime import datetime
import json
import os
import logging
import google.generativeai as genai
from datetime import datetime, timedelta
import re
from typing import Dict, Any

# Set up the Streamlit app configuration
st.set_page_config(
    page_title="Company Career Page Finder",
    page_icon="💼",
    layout="wide"
)

# Set up logging
logging.basicConfig(
    filename='cache/scraper.log',
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

    
# Create a cache directory if it doesn't exist
if not os.path.exists('cache'):
    os.makedirs('cache')

class SearchCache:
    def __init__(self, cache_file='cache/search_cache.json'):
        self.cache_file = cache_file
        self.cache = self._load_cache()
        self.cache_hits = 0
        self.cache_misses = 0

    def _load_cache(self):
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r') as f:
                    cache_data = json.load(f)
                # Remove old entries (older than 24 hours)
                current_time = datetime.now().timestamp()
                cache_data = {
                    k: v for k, v in cache_data.items()
                    if current_time - v['timestamp'] < 86400  # 24 hours
                }
                return cache_data
            return {}
        except Exception:
            return {}

    def _save_cache(self):
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f)
        except Exception as e:
            st.error(f"Error saving cache: {e}")

    def get(self, key):
        if key in self.cache:
            entry = self.cache[key]
            if datetime.now().timestamp() - entry['timestamp'] < 86400:  # 24 hours
                self.cache_hits += 1
                return entry['data']
        self.cache_misses += 1
        return None

    def set(self, key, value):
        self.cache[key] = {
            'data': value,
            'timestamp': datetime.now().timestamp()
        }
        self._save_cache()

# Initialize cache
search_cache = SearchCache()



def get_random_user_agent():
    """Return a random user agent string"""
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 Edg/91.0.864.59'
    ]
    return random.choice(user_agents)

def construct_google_query(job_roles, locations, time_range, job_levels):
    """Construct a Google search query based on user inputs"""
    job_query = ' OR '.join(f'"{role}"' for role in job_roles)
    location_query = ' OR '.join(f'"{loc}"' for loc in locations)
    level_query = ' OR '.join(f'"{level}"' for level in job_levels)
    
    date_filter = ""
    if time_range != "Any time":
        if time_range == "Past 24 hours":
            date_filter = "&tbs=qdr:d"
        elif time_range == "Past week":
            date_filter = "&tbs=qdr:w"
        elif time_range == "Past month":
            date_filter = "&tbs=qdr:m"
        elif time_range == "Past 3 months":
            date_filter = "&tbs=qdr:m3"
        elif time_range == "Past year":
            date_filter = "&tbs=qdr:y"
    
    excluded_sites = ' '.join([f'-site:{site}' for site in [
        'indeed.com', 'linkedin.com', 'glassdoor.com', 'monster.com', 'ziprecruiter.com', 
        'levels.fyi', 'higheredjobs.com', 'environmentalcareer.com', 'zippia.com', 'randstadusa.com', 
        'stryker.com', 'wiverse.com', 'theplacementexchange.org', 'talent.difc', 'builtin.com', 
        '5amventures.com', 'wellfound.com','reddit.com','squarepeghires.com','gracklehq.com',
        'tata.com','sulekha.com', 'campusbuilding.com', 'foxcareers.com',
        'jobmonkey.com', 'aijobs.net'
    ]])
    base_query = f'({job_query}) ({location_query}) ({level_query}) (careers OR "job openings" OR "we\'re hiring") {excluded_sites}'
    return base_query, date_filter

def get_google_search_results(query, date_filter, num_results=25, max_retries=3):
    """Enhanced Google search function with better anti-bot detection avoidance"""
    # Check cache first
    cache_key = f"{query}{date_filter}"
    cached_result = search_cache.get(cache_key)
    if cached_result:
        st.info("Retrieved results from cache.")
        return cached_result

    st.info("Fetching fresh results from Google...")
    
    headers = {
        'User-Agent': get_random_user_agent(),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
        # Add referrer to seem more legitimate
        'Referer': 'https://www.google.com/'
    }
    
    # Add cookies to seem more like a real browser
    cookies = {
        'CONSENT': 'YES+',
        'NID': '511=' + ''.join(random.choices('0123456789abcdef', k=178))
    }
    
    encoded_query = quote(query)
    # Use different Google domains randomly to distribute requests
    google_domains = ['www.google.com', 'www.google.co.uk', 'www.google.ca']
    domain = random.choice(google_domains)
    
    url = f'https://{domain}/search?q={encoded_query}&num={num_results}{date_filter}&hl=en'
    
    session = requests.Session()
    
    # Implement exponential backoff
    for attempt in range(max_retries):
        try:
            # Add random delay between requests with exponential backoff
            wait_time = random.uniform(2, 5) * (2 ** attempt)
            if attempt > 0:
                st.warning(f"Waiting {wait_time:.0f} seconds before retry {attempt + 1}/{max_retries}...")
            time.sleep(wait_time)
            
            # Make the request with cookies and extended timeout
            response = session.get(
                url,
                headers=headers,
                cookies=cookies,
                timeout=30,
                allow_redirects=True
            )
            
            if response.status_code == 200:
                # Verify the response contains actual search results
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Check for multiple possible result selectors
                search_results = (
                    soup.find_all('div', class_='g') or
                    soup.find_all('div', class_='rc') or
                    soup.find_all('div', attrs={'data-sokoban-container': True})
                )
                
                # Also check for any search result links
                links = soup.find_all('a')
                result_links = [link for link in links if 'google' not in link.get('href', '')]
                
                # Check for CAPTCHA or other blocking indicators
                if 'detected unusual traffic' in response.text.lower() or 'captcha' in response.text.lower():
                    st.error("Google has detected automated traffic. Please wait a while before trying again.")
                    time.sleep(random.uniform(60, 120))
                    continue
                
                if search_results or result_links:
                    # Cache the successful result
                    search_cache.set(cache_key, response.text)
                    return response.text
                else:
                    st.warning(f"No search results found in the response. Retrying... (Attempt {attempt + 1}/{max_retries})")
                    
                    # Log the response for debugging
                    with open(f'cache/debug_response_{attempt}.html', 'w', encoding='utf-8') as f:
                        f.write(response.text)
                    continue
                    
            elif response.status_code == 429:
                st.error(f"Rate limited. Waiting longer before retry. (Attempt {attempt + 1}/{max_retries})")
                time.sleep(random.uniform(120, 240))  # Longer wait for rate limiting
                continue
                
            response.raise_for_status()
            
        except requests.RequestException as e:
            st.error(f"Request error (attempt {attempt + 1}/{max_retries}): {str(e)}")
            if attempt == max_retries - 1:
                return None
            continue
            
    return None

def extract_company_name(title, url):
    """
    Simplified company name extraction.
    """
    job_boards = ['indeed', 'linkedin', 'glassdoor', 'monster', 'ziprecruiter', 
                  'levels.fyi', 'simplyhired', 'dice', 'careerbuilder', 'workday', 
                  'lever.co', 'greenhouse.io', 'jobvite']
    
    # Skip if URL is from a job board
    parsed_url = urlparse(url)
    if any(board in parsed_url.netloc.lower() for board in job_boards):
        return None
    
    # Extract potential company name from the domain
    domain_parts = parsed_url.netloc.split('.')
    if len(domain_parts) > 1:
        potential_name = domain_parts[-2].title()
        if len(potential_name) > 2:
            return potential_name
    
    # Try simple pattern-based extraction from title
    title = re.sub(r'\s*[-|].*$', '', title)  # Remove text after dash or pipe
    company_patterns = [r'at\s+([A-Z][A-Za-z0-9\s&]+)', r'([A-Z][A-Za-z0-9\s&]+)\s+(Careers|Jobs)']
    
    for pattern in company_patterns:
        match = re.search(pattern, title)
        if match:
            return match.group(1).strip()

    return None

def is_career_page(url, snippet, title):
    """
    Simplified career page check.
    """
    excluded_domains = ['indeed.com', 'linkedin.com', 'glassdoor.com', 'monster.com']
    parsed_url = urlparse(url)
    domain = parsed_url.netloc.lower()

    if any(excluded in domain for excluded in excluded_domains):
        return False
    
    career_keywords = ['career', 'careers', 'jobs', 'positions', 'opportunities']
    path = parsed_url.path.lower()

    # Check if URL path or text indicates a career page
    has_career_indicators = any(keyword in path for keyword in career_keywords)
    has_career_text = any(keyword in title.lower() or keyword in snippet.lower() for keyword in career_keywords)

    return has_career_indicators or has_career_text

def extract_company_info(html_content):
    """
    Simplified company information extraction.
    """
    if not html_content:
        return []
    soup = BeautifulSoup(html_content, 'html.parser')
    search_results = soup.find_all('div', class_='g')
    
    companies = []
    seen_domains = set()
    
    for result in search_results:
        link_elem = result.find('a')
        if not link_elem or 'href' not in link_elem.attrs:
            continue
        
        url = link_elem['href']
        parsed_url = urlparse(url)
        domain = parsed_url.netloc.lower()
        
        # Skip duplicate domains
        if domain in seen_domains:
            continue
        
        title_elem = result.find('h3')
        snippet_elem = result.find('div', class_='VwiC3b')
        title = title_elem.text if title_elem else ''
        snippet = snippet_elem.text if snippet_elem else ''
        
        # Extract company name and validate
        company_name = extract_company_name(title, url)
        if company_name and is_career_page(url, snippet, title):
            companies.append({
                'name': company_name,
                'url': url,
                'snippet': snippet,
                'domain': domain
            })
            seen_domains.add(domain)
    
    return companies

def search_for_companies(selected_roles, selected_locations, selected_levels, time_range):
    all_companies = []
    
    for location in selected_locations:
        with st.spinner(f"Searching for companies in {location}..."):
            base_query, date_filter = construct_google_query(selected_roles, [location], time_range, selected_levels)
            search_results = get_google_search_results(base_query, date_filter)
            
            if search_results:
                companies = extract_company_info(search_results)
                for company in companies:
                    company['location'] = location
                all_companies.extend(companies)
            
            # Respect rate limits by adding a delay between searches
            time.sleep(random.uniform(10, 20))  # Random delay between 10 to 20 seconds
    
    return all_companies

def extract_job_roles(snippet, selected_roles):
    """
    Extract job roles from the snippet based on the user's selected roles.
    """
    found_roles = []
    for role in selected_roles:
        if re.search(r'\b' + re.escape(role) + r'\b', snippet, re.IGNORECASE):
            found_roles.append(role)
    return ', '.join(found_roles) if found_roles else 'N/A'

def extract_job_info(snippet):
    """
    Extract job posted time and salary range from the snippet.
    """
    # Extract posted time
    time_patterns = [
        r'(\d+)\s*(hour|day|week|month)s?\s+ago',
        r'Posted\s+(\d+)\s*(hour|day|week|month)s?\s+ago',
    ]
    posted_time = 'N/A'
    for pattern in time_patterns:
        match = re.search(pattern, snippet, re.IGNORECASE)
        if match:
            number, unit = match.groups()
            posted_time = f"{number} {unit}(s) ago"
            break

    # Extract salary range
    salary_pattern = r'\$\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(?:-|to)\s*\$\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?)'
    salary_match = re.search(salary_pattern, snippet)
    salary_range = f"${salary_match.group(1)} - ${salary_match.group(2)}" if salary_match else 'N/A'

    return posted_time, salary_range

def create_results_table(companies, selected_roles):
    """
    Create a table from the search results with clickable Career Page links and an editable status column.
    """
    table_data = []
    for i, company in enumerate(companies, 1):
        job_roles = extract_job_roles(company['snippet'], selected_roles)
        posted_time, salary_range = extract_job_info(company['snippet'])
        table_data.append({
            'S Number': i,
            'State': company['location'],
            'Company': company['name'],
            'Career Page': f'<a href="{company["url"]}" target="_blank">{company["url"]}</a>',
            'Job Roles': job_roles,
            'Posted Time': posted_time,
            'Salary Range': salary_range,
            'Status': 'TBD'  # New column with default value
        })
    return pd.DataFrame(table_data)

def display_filtered_table():
    if st.session_state.results_table is not None:

        # Add a search bar for filtering by company name with a grey background and a magnifying glass emoji
        with st.container():
            st.markdown("<style>div.row-widget.stRadio > div.widget.st-iframe {background-color: grey;}</style>", unsafe_allow_html=True)
            search_term = st.text_input("", "", placeholder="🔍")
        
        # Add filters for State, Job Roles, Company, and Status
        with st.expander("Filter Results"):
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                filter_state = st.multiselect("Filter by State:", options=['All'] + list(st.session_state.results_table['State'].unique()))

            with col2:
                filter_roles = st.multiselect("Filter by Job Roles:", options=['All'] + list(st.session_state.results_table['Job Roles'].unique()))

            with col3:
                filter_company = st.multiselect("Filter by Company:", options=['All'] + list(st.session_state.results_table['Company'].unique()))

            with col4:
                filter_status = st.multiselect("Filter by Status:", options=['All', 'Applied', 'TBD', 'Later'])

            # Apply filters
            filtered_table = st.session_state.results_table.copy()

            # Apply search filter
            if search_term:
                filtered_table = filtered_table[filtered_table['Company'].str.contains(search_term, case=False, na=False)]

            if filter_state and 'All' not in filter_state:
                filtered_table = filtered_table[filtered_table['State'].isin(filter_state)]

            if filter_roles and 'All' not in filter_roles:
                filtered_table = filtered_table[filtered_table['Job Roles'].apply(lambda x: any(role in x for role in filter_roles))]

            if filter_company and 'All' not in filter_company:
                filtered_table = filtered_table[filtered_table['Company'].isin(filter_company)]

            if filter_status and 'All' not in filter_status:
                filtered_table = filtered_table[filtered_table['Status'].isin(filter_status)]

            # Display the filtered table
            if not filtered_table.empty:
                st.write(filtered_table.to_html(escape=False, index=False, classes='dataframe'), unsafe_allow_html=True)

        # Status selection displayed after the table, now collapsible
        with st.expander("Select Status for Each Company"):
            for index, row in filtered_table.iterrows():
                # Use a unique key for each selectbox based on the company index and name
                status_key = f"status_{index}_{row['Company']}"  # Unique key for each company and index

                # Initialize the status in session state if not already set
                if status_key not in st.session_state:
                    st.session_state[status_key] = row['Status']  # Set initial status

                # Create the selectbox
                status = st.selectbox(
                    f"Status for {index + 1}: {row['Company']}",
                    options=['Applied', 'TBD', 'Later'],
                    index=['Applied', 'TBD', 'Later'].index(st.session_state[status_key]),
                    key=status_key
                )

                # Update the session state immediately after selection
                st.session_state.results_table.at[row.name, 'Status'] = status  # Update the session state

        # Add Refresh Button below the status selection
        if st.button("Refresh"):
            st.success("Page Refreshed! 🍹")  # Display the prompt with a glass of juice emoji

        # Prepare CSV download (without HTML tags)
        csv_data = filtered_table.copy()
        csv_data['Career Page'] = csv_data['Career Page'].apply(lambda x: x.split('"')[1])  # Extract URL from HTML
        csv = csv_data.to_csv(index=False)
        st.download_button(
            label="Download Filtered Results as CSV",
            data=csv,
            file_name="filtered_company_career_pages.csv",
            mime="text/csv"
        )
    else:
        st.warning("No results match the selected filters.")

# Add custom CSS for responsive table
st.markdown("""
<style>
    .dataframe {
        width: 100%;
        font-size: 0.8em;
    }
    .dataframe th, .dataframe td {
        text-align: left;
        padding: 8px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        max-width: 150px;
    }
    @media screen and (max-width: 600px) {
        .dataframe th, .dataframe td {
            font-size: 0.7em;
            padding: 4px;
            max-width: 100px;
        }
    }
</style>
""", unsafe_allow_html=True)

# Define job levels
job_levels = [
    "Entry Level",
    "Associate",
    "Mid-Level",
    "Senior",
    "Manager",
    "Director",
    "Executive"
]

# Set up the Streamlit app
st.markdown(
    """
    <h1 style="text-align: center;">Company Career Page Finder</h1>
    """,
    unsafe_allow_html=True
)
st.write("Find company career pages based on job roles, locations, and experience levels.")

# Predefined lists
default_roles = [
    "Junior Data Scientist", "Machine Learning Engineer", "Data Engineer",
    "Generative AI Engineer", "AI Engineer", "Medical AI", "Healthcare AI",
    "Clinical Data"
]

default_locations = [
    "San Francisco", "Los Angeles", "San Diego", "Seattle", 
    "Spokane", "Hillsboro", "Portland", "Austin", "Dallas", "Houston"
]

# Initialize session state for custom inputs
if 'custom_roles' not in st.session_state:
    st.session_state.custom_roles = []
if 'custom_locations' not in st.session_state:
    st.session_state.custom_locations = []

# Initialize session state for the results table
if 'results_table' not in st.session_state:
    st.session_state.results_table = None

# Input fields
with st.expander("Search Form"):
    with st.form("search_form"):
        # Job Roles
        selected_roles = st.multiselect(
            "Select Job Roles:",
            options=default_roles + st.session_state.custom_roles,
            default=[]
        )
        
        # Custom Role Input
        custom_role = st.text_input("Enter custom job role:")
        add_role_button = st.form_submit_button("Add Custom Role")
        
        # Locations
        selected_locations = st.multiselect(
            "Select Locations:",
            options=default_locations + st.session_state.custom_locations,
            default=[]
        )
        
        # Custom Location Input
        custom_location = st.text_input("Enter custom location:")
        add_location_button = st.form_submit_button("Add Custom Location")
        
        # Job Levels
        selected_levels = st.multiselect(
            "Select Job Levels:",
            options=job_levels,
            default=[]
        )
        
        # Time Range
        time_range = st.selectbox(
            "Show jobs posted within:",
            options=["Past 24 hours", "Past week", "Past month", "Past 3 months", "Past year", "Any time"],
            index=0  # Default to "Past 24 hours"
        )
        
        search_submitted = st.form_submit_button("Search Career Pages")

# Handle custom inputs
if add_role_button and custom_role and custom_role not in st.session_state.custom_roles:
    st.session_state.custom_roles.append(custom_role)
    st.rerun()

if add_location_button and custom_location and custom_location not in st.session_state.custom_locations:
    st.session_state.custom_locations.append(custom_location)
    st.rerun()

# Process search when form is submitted
if search_submitted:
    # Remove "Other" from selections if present
    selected_roles = [role for role in selected_roles if role != "Other"]
    selected_locations = [loc for loc in selected_locations if loc != "Other"]
    
    if not selected_roles or not selected_locations or not selected_levels:
        st.error("Please select at least one job role, location, and job level.")
    else:
        companies = search_for_companies(selected_roles, selected_locations, selected_levels, time_range)
        
        if companies:
            # Create the results table and store in session state
            st.session_state.results_table = create_results_table(companies, selected_roles)
            
            # Display filters and table
            # display_filtered_table()
        else:
            st.warning("No company career pages found for your search criteria.")

# Display the table if it exists in session state (for when the page reloads)
if st.session_state.results_table is not None:
    display_filtered_table()

# Add cache control to sidebar
with st.sidebar:
    st.title("Cache Control")
    if st.button("Clear Search Cache", key="sidebar_clear_cache"):
        try:
            os.remove('cache/search_cache.json')
            search_cache = SearchCache()  # Reinitialize cache
            st.success("Search cache cleared successfully!")
        except FileNotFoundError:
            st.info("No cache file found. Cache is already empty.")
        except Exception as e:
            st.error(f"Error clearing cache: {e}")
    
    # # New button to delete the scraper.log file
    # if st.button("Delete Scraper Log", key="delete_log"):
    #     try:
    #         os.remove('cache/scraper.log')
    #         st.success("Scraper log deleted successfully!")
    #     except FileNotFoundError:
    #         st.info("No log file found. Log is already empty.")
    #     except Exception as e:
    #         st.error(f"Error deleting log file: {e}")
    
    st.markdown("""
    ### Tips for best results:
    1. Start with smaller searches (1-2 roles/locations)
    2. Wait a few minutes between searches
    3. Use the cache to avoid repeated searches
    4. Clear cache if results seem stale
    """)

    st.markdown("### Debug Options")
    if st.button("View Debug Logs"):
        try:
            with open('cache/scraper.log', 'r') as f:
                st.code(f.read())
        except FileNotFoundError:
            st.info("No debug logs found")

# Add rate limit warning
st.warning("""
⚠️ Note: This tool respects Google's rate limits and searches one location at a time:
- The search may take longer due to built-in delays between location searches
- If you receive a rate limit warning, wait longer before trying again
- Reduce the number of locations or roles to speed up the search
- Use cached results when possible
""")

# Add cache statistics to sidebar
with st.sidebar:
    st.title("Cache Statistics")
    st.write(f"Cache hits: {search_cache.cache_hits}")
    st.write(f"Cache misses: {search_cache.cache_misses}")




































