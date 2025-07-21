# Created: 2025-07-21
# Last Modified: 2025-07-21 13:18:11

import os
import requests
from bs4 import BeautifulSoup
from zipfile import ZipFile
from io import BytesIO

# Constants
URL = "https://download.cms.gov/nppes/NPI_Files.html"
DOWNLOAD_DIR = "npi_data"

# Ensure the download directory exists
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Fetch the webpage
response = requests.get(URL)
response.raise_for_status()

# Parse the HTML content
soup = BeautifulSoup(response.content, 'html.parser')

# Find all links in the Weekly Incremental NPI Files Version 2 (V.2) section
weekly_links = []
for link in soup.find_all('a', href=True):
    href = link['href']
    if 'weekly' in href.lower() and href.endswith('.zip'):
        weekly_links.append(href)

# Sort links to find the most recent one
weekly_links.sort(reverse=True)
most_recent_link = weekly_links[0] if weekly_links else None

if most_recent_link:
    # Download the most recent file
    file_url = most_recent_link if most_recent_link.startswith('http') else f'https://download.cms.gov{most_recent_link}'
    zip_response = requests.get(file_url)
    zip_response.raise_for_status()

    # Unzip the file
    with ZipFile(BytesIO(zip_response.content)) as thezip:
        thezip.extractall(DOWNLOAD_DIR)

    print(f"Downloaded and extracted: {file_url}")
else:
    print("No weekly files found.") 