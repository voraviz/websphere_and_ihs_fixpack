import requests
from bs4 import BeautifulSoup
import csv
import re
import time
import os
from datetime import datetime

def format_date_for_file(date_str):
    """Converts '09 February 2026' to '20260209'."""
    try:
        match = re.search(r'(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})', date_str, re.I)
        if match:
            date_obj = datetime.strptime(match.group(), "%d %B %Y")
            return date_obj.strftime("%Y%m%d")
        return "UnknownDate"
    except Exception:
        return "UnknownDate"

def get_detailed_info(apar_num, headers, fields_to_track, item, source):
    """Scrapes the individual APAR page for metadata."""
    row_data = {field: "N/A" for field in fields_to_track}
    row_data["APAR Number"] = apar_num
    row_data["isSecurity"] = item["isSecurity"]
    row_data["Source"] = source

    if source == "IHS":
        row_data["Title"] = item["table_desc"]
    
    if item["isSecurity"] == "Y":
        if source != "IHS": 
            row_data["Title"] = item["table_desc"]
        return row_data

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

def scrape_table_logic(soup, anchor_id, table_class=None, find_meta=False):
    """Extracts Fix Pack metadata and APARs from the table."""
    target = soup.find(id=anchor_id)
    if not target:
        return [], {}

    parent_table = target.find_next('table', class_=table_class) if table_class else target.find_next('table')
    if not parent_table:
        return [], {}

    meta = {"Release Date": "Unknown", "Last Modified": "Unknown", "Status": "Unknown"}
    
    if find_meta:
        table_text = parent_table.get_text(" ", strip=True)
        
        rel_match = re.search(r'Fix release date:\s*(\d{1,2}\s+\w+\s+\d{4})', table_text, re.I)
        if rel_match:
            meta["Release Date"] = rel_match.group(1).strip()
            
        mod_match = re.search(r'Last modified:\s*(\d{1,2}\s+\w+\s+\d{4})', table_text, re.I)
        if mod_match:
            meta["Last Modified"] = mod_match.group(1).strip()
            
        stat_match = re.search(r'Status:\s*(\w+)', table_text, re.I)
        if stat_match:
            meta["Status"] = stat_match.group(1).strip()

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
            
    return queue, meta

def write_markdown_row(md_file, data, fields):
    row = "| " + " | ".join(str(data.get(f, "N/A")) for f in fields) + " |"
    md_file.write(row + "\n")

def main():
    print("--- IBM Consolidated APAR Scraper (WAS & IHS) ---")
    user_version = input("Enter Fix Pack Version (e.g., 9.0.5.26 or 8.5.5.2.29): ").strip()
    
    version_anchor = user_version.replace(".", "")
    headers = {"User-Agent": "Mozilla/5.0"}
    fields = ["Source", "APAR Number", "isSecurity", "Title", "Reported component name", "Status", "PE", "HIPER", "Submitted date", "Closed date"]
    
    if user_version.startswith("9."):
        was_url = f"https://www.ibm.com/support/pages/fix-list-ibm-websphere-application-server-traditional-v9-0#{version_anchor}"
        
    elif user_version.startswith("8."):
        was_url = f"https://www.ibm.com/support/pages/fix-list-ibm-websphere-application-server-v85#{version_anchor}"
    else:
        print("Error: Major version must be 8 or 9.")
        return
    base_prefix = f"was_fixpack_{version_anchor}"
    counts = {"WAS": 0, "IHS": 0}
    # Storage for the metadata to be printed at the end
    collected_meta = {}

    sources = [
        {"name": "WAS", "url": was_url, "class": "bx--data-table", "find_meta": True},
        {"name": "IHS", "url": "https://www.ibm.com/support/pages/node/617655", "class": "bx--data-table", "find_meta": False}
    ]

    final_csv = None
    final_md = None

    for src in sources:
        print(f"\nProcessing {src['name']}...")
        try:
            resp = requests.get(src['url'], headers=headers, timeout=15)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                queue, meta = scrape_table_logic(soup, version_anchor, table_class=src['class'], find_meta=src['find_meta'])
                
                # Store WAS metadata for later printing
                if src['find_meta']:
                    collected_meta = meta
                    file_date = format_date_for_file(meta['Release Date'])
                    final_csv = f"{base_prefix}_{file_date}.csv"
                    final_md = f"{base_prefix}_{file_date}.md"
                
                # Ensure files are initialized if WAS fails or has no date
                if not final_csv:
                    final_csv = f"{base_prefix}_NoDate.csv"
                    final_md = f"{base_prefix}_NoDate.md"

                # Initialize Files only once
                if not os.path.exists(final_csv):
                    with open(final_csv, mode='w', newline='', encoding='utf-8') as cf, \
                         open(final_md, mode='w', encoding='utf-8') as mf:
                        csv.DictWriter(cf, fieldnames=fields).writeheader()
                        mf.write(f"# IBM Support Fix List Report: {user_version}\n\n")
                        if collected_meta:
                            mf.write(f"**Release Date:** {collected_meta.get('Release Date')} | **Status:** {collected_meta.get('Status')}\n\n")
                        mf.write("| " + " | ".join(fields) + " |\n")
                        mf.write("| " + " | ".join(["---"] * len(fields)) + " |\n")

                for i, item in enumerate(queue, 1):
                    data = get_detailed_info(item['num'], headers, fields, item, src['name'])
                    with open(final_csv, mode='a', newline='', encoding='utf-8') as cf:
                        csv.DictWriter(cf, fieldnames=fields).writerow(data)
                    with open(final_md, mode='a', encoding='utf-8') as mf:
                        write_markdown_row(mf, data, fields)
                    counts[src['name']] += 1
                    print(f"   [{i}/{len(queue)}] {item['num']} ({src['name']})")
                    
        except Exception as e:
            print(f"Error processing {src['name']}: {e}")

    # --- FINAL OUTPUT SUMMARY ---
    print(f"\n" + "="*45)
    print(f"FIX PACK DETAILS ({user_version})")
    print(f"="*45)
    if collected_meta:
        print(f"Fix Release Date: {collected_meta.get('Release Date')}")
        print(f"Last Modified:    {collected_meta.get('Last Modified')}")
        print(f"Status:           {collected_meta.get('Status')}")
    else:
        print("Metadata: Not Found")
    print("-"*45)
    print(f"CSV Report: {final_csv}")
    print(f"MD Report:  {final_md}")
    print(f"Totals:     WAS ({counts['WAS']}), IHS ({counts['IHS']})")
    print("="*45)

if __name__ == "__main__":
    main()