import asyncio
import aiohttp
from bs4 import BeautifulSoup
import json
import time
import re

# --- Configuration ---
BASE_URL = "https://www.petzl.com"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# === STAGE 1 & 2: Get all Product URLs (Synchronous part) ===
def get_all_product_urls():
    """
    Sequentially scrapes all categories and the products within them
    to create a list of all product URLs to be scraped asynchronously.
    """
    print("--- STAGE 1: Fetching Categories ---")
    start_url = f"{BASE_URL}/DE/de/Professional"
    all_products = []

    import requests # Use synchronous requests for this initial part

    try:
        response = requests.get(start_url, headers=HEADERS)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'lxml')

        category_section = soup.find('div', id='submenu_a2w200000011y8DAAQ')
        if not category_section:
            print("Error: Could not find the main category navigation section.")
            return []

        categories = [{'name': a_tag.get_text(strip=True), 'url': a_tag['href']}
                      for item in category_section.find_all('li', class_='ib')
                      if (a_tag := item.find('a', href=True))]

        print(f"Found {len(categories)} categories. Now fetching products from each.")

        print("\n--- STAGE 2: Fetching Product Listings from each Category ---")
        for category in categories:
            print(f"Fetching products for: {category['name']}")
            try:
                cat_response = requests.get(category['url'], headers=HEADERS)
                cat_response.raise_for_status()
                cat_soup = BeautifulSoup(cat_response.content, 'lxml')

                if container := cat_soup.find('div', class_='productContainer all'):
                    for block in container.find_all('div', class_='product'):
                        if prod_link := block.find('a', href=True):
                            all_products.append({
                                'category': category['name'],
                                'product_url': prod_link['href']
                            })
                time.sleep(0.5)
            except requests.RequestException as e:
                print(f"  - Could not fetch category {category['name']}: {e}")
                continue

    except requests.RequestException as e:
        print(f"Failed to fetch the main page: {e}")
        return []

    print(f"\nTotal products to scrape: {len(all_products)}")
    return all_products


# === STAGE 3: Fetch and Parse a Single Product Page (Asynchronous Worker) ===

def parse_product_details(soup):
    """Parses the BeautifulSoup object of a product page to extract all details."""
    details = {}

    # Product Title, Subtitle, and Main Description
    if title_tag := soup.find('h1', class_='productTitle'):
        details['title'] = title_tag.get_text(strip=True, separator=' ').replace(' ®', '®')
    if subtitle_tag := soup.find('p', class_='productSubtitle'):
        details['subtitle'] = subtitle_tag.get_text(strip=True)
    if desc_container := soup.find('div', class_='productCaracteristiques'):
        details['main_description'] = desc_container.get_text(strip=True)

    # Image Gallery
    if slideshow := soup.find('div', id='slideshow'):
        details['gallery'] = {
            'thumbnails': [img['style'].split("url('")[1].split("')")[0]
                           for img in slideshow.select('li.thumb[style]')],
            'full_images': [img['data-zoom']
                            for img in slideshow.select('img.zoomOnClick[data-zoom]')]
        }

    # Features from "Detailed description"
    if detailed_desc_section := soup.find('div', id='descriptif'):
        desc_points = detailed_desc_section.select('div.list ul li')
        details['features'] = [point.get_text(strip=True, separator=' ') for point in desc_points]

    # Specifications
    # MODIFIED: Use re.compile to find the header reliably
    spec_section = soup.find('h3', string=re.compile(r'Specifications|Spezifikationen'))
    if spec_section and (spec_list := spec_section.find_next('div', class_='list')):
        specs = {}
        for item in spec_list.find_all('li'):
            text = item.get_text(strip=True)
            if ':' in text:
                key, value = text.split(':', 1)
                specs[key.strip()] = value.strip()
            else:
                specs.setdefault('notes', []).append(text)
        details['specifications'] = specs

    # References Table
    # MODIFIED: Use re.compile to find the header reliably
    references_section = soup.find('h3', string=re.compile(r'References|Referenzen'))
    if references_section:
        references = []
        for table in references_section.find_next_siblings('table'):
            # Using select to be more robust against thead/tbody variations
            header_row = table.select_one('thead tr, tr:first-child')
            if not header_row: continue

            headers = [th.get_text(strip=True) for th in header_row.find_all('th')][1:]
            if not headers: continue

            # This logic rebuilds each product reference column by column
            # It assumes a structure where each row describes one attribute.
            num_products_in_table = len(headers)
            temp_refs = [{} for _ in range(num_products_in_table)]

            # Pre-populate the reference code from the headers
            for i, ref_code in enumerate(headers):
                temp_refs[i]['Reference'] = ref_code

            # Now iterate through the data rows
            for row in table.select('tbody tr, tr:not(:first-child)'):
                row_title_cell = row.find('td', class_='rowTitle')
                if not row_title_cell: continue

                # Clean the row title, e.g., "Colors)" -> "Colors"
                row_title = row_title_cell.get_text(strip=True).replace(')', '').strip()
                values = [td.get_text(strip=True) for td in row.find_all('td')[1:]]

                if "Farbe" in row_title:
                  row_title = "color"
                if "Reference" in row_title:
                  row_title = "article_number"
                for i, value in enumerate(values):
                    if i < len(temp_refs):
                        temp_refs[i][row_title] = value

            references.extend(temp_refs)
        details['references'] = references

    # Technical Documents
    tech_docs = {}
    if tech_info_section := soup.find('div', id='solutions'):
        for link_block in tech_info_section.find_all('div', class_='titleLink'):
            if heading_tag := link_block.find('h3'):
                heading = heading_tag.get_text(strip=True)
                doc_links = []
                for a_tag in link_block.find_all('a', href=True):
                    url = a_tag['href']
                    if not url.startswith('http'):
                        url = BASE_URL + url
                    doc_links.append({
                        'text': a_tag.get_text(strip=True, separator=' '),
                        'url': url
                    })
                if doc_links:
                    tech_docs[heading] = doc_links
    details['technical_documents'] = tech_docs

    return details

async def fetch_and_parse(session, product):
    """Async worker: fetches a URL, parses it, and returns the merged data."""
    url = product['product_url']
    try:
        async with session.get(url, headers=HEADERS, timeout=30) as response:
            if response.status != 200:
                print(f"  - Failed {url} with status {response.status}")
                return product # Return original info on failure
            html = await response.text()
            soup = BeautifulSoup(html, 'lxml')
            detailed_data = parse_product_details(soup)
            product.update(detailed_data)
            return product
    except Exception as e:
        print(f"  - Error processing {url}: {e}")
        return product


# === STAGE 4: Main Orchestration ===

async def main_pitzl():
    """Main function to run the entire scraping process."""

    products_to_scrape = get_all_product_urls()
    if not products_to_scrape:
        return

    print(f"\n--- STAGE 3: Asynchronously Fetching Details for {len(products_to_scrape)} Products ---")

    async with aiohttp.ClientSession() as session:
        tasks = [fetch_and_parse(session, product) for product in products_to_scrape]
        results = await asyncio.gather(*tasks)

    print("\n--- STAGE 4: Data Processing Complete ---")

    final_data = {}
    for product in results:
        category = product.get('category', 'Uncategorized')
        final_data.setdefault(category, []).append(product)

    output_file = 'petzl_full_product_data.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(final_data, f, indent=2, ensure_ascii=False)

    print(f"\nSuccessfully scraped all data. Results saved to '{output_file}'")