# JobFinder

## Overview
JobFinder is a Streamlit application designed to help users find company career pages based on job roles, locations, and experience levels. The application leverages Google search to retrieve relevant job postings while implementing caching mechanisms to enhance performance and reduce redundant searches.

## Features
- **Search for Jobs**: Users can input job roles, locations, and experience levels to find relevant career pages.
- **Caching**: The application caches search results for 24 hours to improve response times for repeated queries.
- **Custom Inputs**: Users can add custom job roles and locations to tailor their search.
- **Filtering Results**: The results can be filtered by state, job roles, and company names.
- **Downloadable Results**: Users can download the filtered results as a CSV file.
- **Responsive Design**: The application is designed to be responsive and user-friendly.

## How It Works
1. **User Input**: Users select job roles, locations, job levels, and a time range for job postings.
2. **Google Search**: The application constructs a Google search query based on the user inputs and fetches results.
3. **Data Extraction**: It extracts relevant company information from the search results, including company names and URLs.
4. **Display Results**: The results are displayed in a table format, allowing users to click through to the career pages.
5. **Caching**: Results are cached to minimize repeated searches and improve performance.

## Requirements
- Python 3.x
- Streamlit
- Requests
- BeautifulSoup4
- Pandas
- Cachetools
- Google Generative AI (if applicable)

## Installation
To install the required packages, run:
