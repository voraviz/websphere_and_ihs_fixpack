import requests
from bs4 import BeautifulSoup
import csv
import re
import time
import os

def get_detailed_info(apar_num, headers, fields_to_track, item, source):
    """Scrapes the individual APAR page for metadata."""
    row_data = {field: "N/A" for field in fields_to_track}
    row_data["APAR Number"] = apar_num
    row_data["isSecurity"] = item["isSecurity"]
    row_data["Source"] = source

    # REQUIREMENT: For IHS, always use the table description as the Title
    if source == "IHS":
        row_data["Title"] = item["table_desc"]
    
    # If it's a security APAR, we skip the web request entirely
    if item["isSecurity"] == "Y":
        if source != "IHS": 
            row_data["Title"] = item["table_desc"]
        return row_data

    # For non-security APARs, scrape the detail page for the remaining fields
    apar_url = f"https://www.ibm.com/support/pages/apar/{apar_num}"
    try:
        time.sleep(0.5) 
        resp = requests.get(apar_url, headers=headers, timeout=10)
        if resp.status_code == 200:
            apar_soup = BeautifulSoup(resp.text, 'html.parser')
            
            if source != "IHS":
                raw_title = apar_soup.title.string if apar_soup.title else ""
                row_data["Title"] = re.sub(rf'^{apar_num}[:\-\s]*', '', raw_title, flags=re.IGNORECASE).strip()

            info_h2 = apar_soup.find('h2', string=lambda t: t and "APAR Information" in t)
            if info_h2:
                ul = info_h2.find_next('ul', class_='ibm-stock-list')
                if ul:
                    for li in ul.find_all('li'):
                        h3, p = li.find('h3'), li.find('p')
                        if h3 and p:
                            header = h3.get_text(strip=True).replace(":", "").lower()
                            for field in fields_to_track:
                                if header == field.lower():
                                    row_data[field] = p.get_text(strip=True)
        else:
            row_data["Title"] = item["table_desc"]
    except Exception:
        row_data["Title"] = item["table_desc"]
    
    return row_data

def scrape_table_logic(soup, anchor_id, table_class=None):
    """Extracts APARs and descriptions from the Fix List table."""
    target = soup.find(id=anchor_id)
    if not target:
        return []

    parent_table = target.find_next('table', class_=table_class) if table_class else target.find_next('table')
    if not parent_table:
        return []

    queue = []
    seen = set()
    rows = parent_table.find_all('tr')
    for row in rows:
        tds = row.find_all('td')
        if len(tds) < 2: continue

        is_sec = "Y" if "✓" in tds[0].get_text() else "N"
        apar_num, description = None, ""
        
        for i, td in enumerate(tds):
            text = td.get_text(strip=True)
            match = re.search(r'[A-Z]{2}\d{5}', text)
            if match:
                apar_num = match.group(0)
                if i + 1 < len(tds):
                    description = tds[i+1].get_text(strip=True)
                break
        
        if apar_num and apar_num not in seen:
            seen.add(apar_num)
            queue.append({"num": apar_num, "isSecurity": is_sec, "table_desc": description})
    return queue

def write_markdown_row(md_file, data, fields):
    """Formats a dictionary into a Markdown table row."""
    row = "| " + " | ".join(str(data.get(f, "N/A")) for f in fields) + " |"
    md_file.write(row + "\n")

def main():
    print("--- IBM Consolidated APAR Scraper (WAS & IHS) ---")
    user_version = input("Enter Fix Pack Version (e.g., 9.0.5.26): ").strip()
    
    if not user_version.startswith("9."):
        print("Error: Major version must be 9.")
        return

    version_anchor = user_version.replace(".", "")
    headers = {"User-Agent": "Mozilla/5.0"}
    fields = ["Source", "APAR Number", "isSecurity", "Title", "Reported component name", "Status", "PE", "HIPER", "Submitted date", "Closed date"]
    
    csv_filename = f"was9_fixpack_{version_anchor}.csv"
    md_filename = f"was9_fixpack_{version_anchor}.md"

    # Initialize Files
    with open(csv_filename, mode='w', newline='', encoding='utf-8') as cf, \
         open(md_filename, mode='w', encoding='utf-8') as mf:
        
        csv.DictWriter(cf, fieldnames=fields).writeheader()
        
        # Markdown Header
        mf.write(f"# IBM Support Fix List Report: {user_version}\n\n")
        mf.write(f"Generated on: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        mf.write("| " + " | ".join(fields) + " |\n")
        mf.write("| " + " | ".join(["---"] * len(fields)) + " |\n")

    # Tracking for Summary
    counts = {"WAS": 0, "IHS": 0}

    # Sources Configuration
    sources = [
        {"name": "WAS", "url": f"https://www.ibm.com/support/pages/fix-list-ibm-websphere-application-server-traditional-v9-0#{version_anchor}", "class": None},
        {"name": "IHS", "url": "https://www.ibm.com/support/pages/node/617655", "class": "bx--data-table"}
    ]

    for src in sources:
        print(f"\nProcessing {src['name']}...")
        try:
            resp = requests.get(src['url'], headers=headers, timeout=15)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                queue = scrape_table_logic(soup, version_anchor, table_class=src['class'])
                
                for i, item in enumerate(queue, 1):
                    data = get_detailed_info(item['num'], headers, fields, item, src['name'])
                    
                    # Append to CSV
                    with open(csv_filename, mode='a', newline='', encoding='utf-8') as cf:
                        csv.DictWriter(cf, fieldnames=fields).writerow(data)
                    
                    # Append to Markdown
                    with open(md_filename, mode='a', encoding='utf-8') as mf:
                        write_markdown_row(mf, data, fields)
                    
                    counts[src['name']] += 1
                    print(f"   [{i}/{len(queue)}] {item['num']} ({src['name']})")
        except Exception as e:
            print(f"Error processing {src['name']}: {e}")

    print(f"\n--- SUCCESS ---")
    print(f"CSV Report: {csv_filename}")
    print(f"Markdown Report: {md_filename}")
    print(f"Totals: WAS ({counts['WAS']}), IHS ({counts['IHS']})")

if __name__ == "__main__":
    main()