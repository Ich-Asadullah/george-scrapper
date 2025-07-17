import asyncio
import aiohttp
from bs4 import BeautifulSoup
import json
import time
import requests
from urllib.parse import urljoin, urlparse
from pathlib import PurePosixPath

semaphore = asyncio.Semaphore(20)

# --- Configuration ---
BASE_URL = "https://edelrid.com"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'X-Requested-With': 'XMLHttpRequest' # Crucial header for Edelrid's API
}

# === STAGE 1 & 2: Get all Product URLs (Synchronous part - from your code) ===

def fetch_edelrid_categories(url):
    """
    Fetches the main product categories from the Edelrid professional page.
    """
    categories = []
    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'lxml')

        container = soup.find('div', class_='iframe-brick')
        if not container:
            print("Error: Could not find the main category container ('iframe-brick').")
            return []

        category_blocks = container.find_all('div', class_='ed-product-grid-item')

        for block in category_blocks:
            name_tag = block.find('div', class_='h5')
            link_tag = block.find('a', href=True)

            if name_tag and link_tag:
                name = name_tag.get_text(strip=True)
                relative_url = link_tag['href']
                absolute_url = relative_url if relative_url.startswith('http') else BASE_URL + relative_url
                categories.append({
                    'category_name': name,
                    'category_url': absolute_url
                })
        return categories
    except requests.exceptions.RequestException as e:
        print(f"Error fetching categories from {url}: {e}")
        return []

def get_all_product_urls_edelrid():
    """
    Scrapes categories, then for each category, finds the 'load all' URL
    and fetches all product listings from it.
    """
    print("--- STAGE 1: Fetching Edelrid Categories ---")
    start_url = f"{BASE_URL}/de-de/professional"
    categories = fetch_edelrid_categories(start_url)

    all_products = []

    print(f"\n--- STAGE 2: Finding 'Load All' links and Fetching Product Listings ---")
    for category in categories:
        print(f"Processing category: {category['category_name']}")

        try:
            initial_response = requests.get(category['category_url'], headers=HEADERS)
            initial_response.raise_for_status()
            initial_soup = BeautifulSoup(initial_response.content, 'lxml')

            # Fetch initial products
            product_blocks_initial = initial_soup.find_all('div', class_='ed-product-grid-item')

            count = 0
            for block in product_blocks_initial:
                if 'ed-grid-item-highlights' in block.get('class', []): continue

                if prod_link := block.find('a', class_='ed-product-grid-item-link', href=True):
                    product_url = prod_link['href']
                    if not product_url.startswith('http'):
                        product_url = BASE_URL + product_url
                    all_products.append({
                        'category': category['category_name'],
                        'product_url': product_url
                    })
                    count += 1

            loader_div = initial_soup.find('div', attrs={'data-controller': 'article-loader'})
            if not loader_div:
                print(f"  - Could not find article-loader div for '{category['category_name']}'. Skipping.")
                continue

            category_id = loader_div.get('data-article-loader-category-id-value')
            department = loader_div.get('data-article-loader-department-value', 'professional')

            api_url = f"{BASE_URL}/de-de/view/list/products/{category_id}/{department}?brick=contentSection:1.content&page={category['category_url']}&render_template=category_page/_product-grid.html.twig&limit=9999"

            print(f"  - Making API call to load all products for category ID {category_id}...")
            api_response = requests.get(api_url, headers=HEADERS)
            api_response.raise_for_status()

            products_html = api_response.text

            if not products_html:
                print(f"  - API response for '{category['category_name']}' contained no HTML. Skipping.")
                continue

            products_soup = BeautifulSoup(products_html, 'lxml')
            product_blocks = products_soup.find_all('div', class_='ed-product-grid-item')

            for block in product_blocks:
                if 'ed-grid-item-highlights' in block.get('class', []): continue

                if prod_link := block.find('a', class_='ed-product-grid-item-link', href=True):
                    product_url = prod_link['href']
                    if not product_url.startswith('http'):
                        product_url = BASE_URL + product_url
                    all_products.append({
                        'category': category['category_name'],
                        'product_url': product_url
                    })
                    count += 1
            print(f"  - Scraped {count} products.")
            time.sleep(0.5)

        except requests.exceptions.RequestException as e:
            print(f"  - An error occurred for category '{category['category_name']}': {e}")
            continue

    unique_products = [dict(t) for t in {tuple(d.items()) for d in all_products}]
    print(f"\nTotal unique products found across all categories: {len(unique_products)}")
    return unique_products


# === STAGE 3: Fetch and Parse a Single Product Page (Asynchronous Worker) ===

def extract_features_list(soup):
    """
    This function takes a BeautifulSoup object and extracts all the features
    listed in the 'Features' section.

    Args:
        soup: A BeautifulSoup object parsed from the HTML.

    Returns:
        A list of strings, where each string is a feature.
        Returns an empty list if the 'Features' section is not found.
    """
    features_list = []
    # Find the anchor tag with id 'features' which contains the "Features" heading
    features_anchor = soup.find('a', id='features')

    if features_anchor:
        # The list of features is in the 'ul' tag within the next sibling div
        accordion_content = features_anchor.find_next_sibling('div', class_='uk-accordion-content')
        if accordion_content:
            feature_ul = accordion_content.find('ul')
            if feature_ul:
                # Find all list items (li) and extract their text
                for item in feature_ul.find_all('li'):
                    features_list.append(item.get_text(strip=True))

    return features_list

def extract_download_links(soup):
    """
    This function takes a BeautifulSoup object and extracts the name and link
    of all files listed in the 'PDF Downloads' section.

    Args:
        soup: A BeautifulSoup object parsed from the HTML.

    Returns:
        A list of dictionaries, where each dictionary contains the 'name' and 'link'
        of a downloadable file. Returns an empty list if the section is not found.
    """
    pdf_downloads = []
    # Find the anchor tag with id 'pdf-downloads'
    downloads_anchor = soup.find('a', id='pdf-downloads')

    if downloads_anchor:
        # The download links are in the next sibling div
        accordion_content = downloads_anchor.find_next_sibling('div', class_='uk-accordion-content')
        if accordion_content:
            # Find all anchor tags within the list of downloads
            for link in accordion_content.find_all('a', class_='ed-link-plain'):
                file_name = link.get_text(strip=True)
                file_link = link.get('href')
                if file_name and file_link:
                    pdf_downloads.append({'name': file_name, 'link': file_link})

    return pdf_downloads


def parse_product_details_edelrid(soup):
    """Parses the BeautifulSoup object of a product page to extract all details."""
    details = {}

    # --- Product Title, Subtitle, and Main Description ---
    try:
        if title_tag := soup.select_one('.ed-product-detail-banner-details-header h1'):
            details['title'] = title_tag.get_text(strip=True)
        if subtitle_tag := soup.select_one('.ed-product-detail-banner-sub-headline'):
            details['subtitle'] = subtitle_tag.get_text(strip=True)
        if desc_tag := soup.select_one('.ed-product-detail-banner-details .ed-text-child-light-content'):
             details['main_description'] = desc_tag.get_text(strip=True)
    except Exception as e:
        print(f"  - Warning: Could not parse title/description. Error: {e}")

    # --- Image Gallery for the active color variant ---
    try:
        if active_carousel := soup.select_one('.ed-product-detail-banner-container.ed-active'):
            image_urls = []
            for li in active_carousel.select('li.ed-product-detail-banner-image'):
                if img_tag := li.find('img', src=True):
                    # Get a higher resolution version by replacing the size in the URL
                    high_res_url = img_tag['src'].replace('/web-s', '/web-xl').replace('/web-m', '/web-xl')
                    image_urls.append(high_res_url)
            details['gallery'] = {"full_images": list(dict.fromkeys(image_urls))} # Remove duplicates
    except Exception as e:
        print(f"  - Warning: Could not parse image gallery. Error: {e}")

    # --- Accordion Sections (Description, Features, Tech Info, Documents) ---
    try:
        # Initialize keys to ensure they exist even if a section is not found
        details['features'] = extract_features_list(soup)
        details['technical_documents'] = extract_download_links(soup)

        # Select all top-level list items in the accordion
        accordion_items = soup.select('.ed-product-page-details > div > ul > li')
        for item in accordion_items:
            if title_tag := item.find('a', class_='uk-accordion-title'):
                title_text = title_tag.get_text(strip=True)
                title_key = title_text.lower().replace('&', 'and').replace(' ', '_')
                content_div = item.find('div', class_='uk-accordion-content')
                if not content_div: continue

                # # --- NEW: For "Beschreibung" (Parse as Features) ---
                # if 'beschreibung' in title_key:
                #     # Get bullet points as features, if they exist
                #     feature_list = content_div.select('ul > li')
                #     if feature_list:
                #         details['features'] = [li.get_text(strip=True) for li in feature_list]

                #     # Also get paragraph text as the detailed description
                #     if p_tag := content_div.find('p'):
                #         details['detailed_description'] = p_tag.get_text(strip=True)
                #     # Fallback if no list or p-tag found
                #     elif not feature_list:
                #         details['detailed_description'] = content_div.get_text(strip=True, separator='\n')

                # --- For "Technische Informationen" (Specifications) ---
                elif 'technische_informationen' in title_key:
                    specs = {}
                    for li in content_div.select('ul > li'):
                        text = li.get_text(strip=True)
                        if ':' in text:
                            key, value = text.split(':', 1)
                            specs[key.strip()] = value.strip()
                        else:
                            specs.setdefault('notes', []).append(text)
                    details['specifications'] = specs

                # # --- NEW: For "Sicherheitshinweise" (Parse as Technical Documents) ---
                # elif 'sicherheitshinweise' in title_key:
                #     doc_links = []
                #     for li in content_div.select('ul > li'):
                #         if a_tag := li.find('a', href=True):
                #             url = a_tag['href']
                #             if not url.startswith('http'):
                #                 url = BASE_URL + url
                #             doc_links.append({
                #                 'text': a_tag.get_text(strip=True, separator=' ').replace('\n', ' '),
                #                 'url': url
                #             })
                #     if doc_links:
                #         # Use the accordion title as the key, similar to the Petzl scraper
                #         details.setdefault('technical_documents', {})[title_text] = doc_links

    except Exception as e:
        print(f"  - Warning: Could not parse accordion sections. Error: {e}")


    # --- References (Variants from JSON) ---
    try:
        variants_container = soup.find('div', {'data-product-detail-description-variants-value': True})
        if variants_container:
            # Create a mapping from color ID to color name
            color_map = {
                btn['data-color-id']: btn.get('uk-tooltip', '').split('title: ')[-1].split(';')[0].strip()
                for btn in soup.select('button.ed-product-color-toggle[data-color-id]')
            }

            variants_json_str = variants_container['data-product-detail-description-variants-value']
            variants_data = json.loads(variants_json_str)

            references = []
            for color_id_str, sizes_data in variants_data:
                color_name = color_map.get(color_id_str, "N/A")
                for size_name, variant_details in sizes_data:
                    references.append({
                        "color": color_name,
                        "size": size_name,
                        "article_number": variant_details.get("articleNumber"),
                        "gtin": variant_details.get("gtin"),
                        "price_eur": variant_details.get("price") / 100.0 if variant_details.get("price") else None,
                        "stock_quantity": variant_details.get("stockQty")
                    })
            details['references'] = references
    except (json.JSONDecodeError, AttributeError, KeyError) as e:
        print(f"  - Warning: Could not parse product variants. Error: {e}")

    return details

async def fetch_and_parse_edelrid(session, product):
    """Async worker: fetches a URL, parses it, and returns the merged data."""
    url = product['product_url']
    try:
        async with semaphore:
            async with session.get(url, headers=HEADERS, timeout=60) as response:
                if response.status != 200:
                    print(f"  - Failed {url} with status {response.status}")
                    return {**product, 'error': f'HTTP Status {response.status}'}

                html = await response.text()
                soup = BeautifulSoup(html, 'lxml')

                detailed_data = parse_product_details_edelrid(soup)
                product.update(detailed_data)
                return product
    except asyncio.TimeoutError:
        print(f"  - Timeout error processing {url}")
        return {**product, 'error': 'Timeout'}
    except Exception as e:
        print(f"  - General error processing {url}: {e}")
        return {**product, 'error': str(e)}


# === STAGE 4: Main Orchestration ===

async def main_edelrid():
    """Main function to run the entire Edelrid scraping process."""

    products_to_scrape = get_all_product_urls_edelrid()
    if not products_to_scrape:
        print("No products found to scrape. Exiting.")
        return

    print(f"\n--- STAGE 3: Asynchronously Fetching Details for {len(products_to_scrape)} Products ---")

    async with aiohttp.ClientSession() as session:
        tasks = [fetch_and_parse_edelrid(session, product) for product in products_to_scrape]
        results = await asyncio.gather(*tasks)

    print("\n--- STAGE 4: Data Processing Complete ---")

    final_data = {}
    for product in results:
        category = product.get('category', 'Uncategorized')
        # We don't want to save the original 'category_name' and 'category_url' in the product list
        product.pop('category_name', None)
        product.pop('category_url', None)
        final_data.setdefault(category, []).append(product)

    output_file = 'edelrid_full_product_data.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(final_data, f, indent=2, ensure_ascii=False)

    print(f"\nSuccessfully scraped all data. Results saved to '{output_file}'")