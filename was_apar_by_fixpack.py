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

def find_latest_version(url, headers):
    """Scans the page to find the most recent version in the table."""
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            # Look for IDs that follow the V.R.M.F pattern (4-5 digits) inside the main table
            table = soup.find('table', class_='bx--data-table')
            if table:
                # IBM typically puts the latest version in the first <tr> or via an <a> tag ID
                # We look for the first element with an ID that looks like a version anchor
                anchors = soup.find_all(id=re.compile(r'^\d{4,5}$'))
                if anchors:
                    # The first one found on the page is usually the latest
                    latest_anchor = anchors[0]['id']
                    # Reconstruct dots: 90526 -> 9.0.5.26
                    if len(latest_anchor) == 5:
                        return f"{latest_anchor[0]}.{latest_anchor[1]}.{latest_anchor[2]}.{latest_anchor[3:]}"
                    elif len(latest_anchor) == 4:
                        return f"{latest_anchor[0]}.{latest_anchor[1]}.{latest_anchor[2]}.{latest_anchor[3]}"
        return None
    except Exception as e:
        print(f"Error finding latest version: {e}")
        return None

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
        if rel_match: meta["Release Date"] = rel_match.group(1).strip()
            
        mod_match = re.search(r'Last modified:\s*(\d{1,2}\s+\w+\s+\d{4})', table_text, re.I)
        if mod_match: meta["Last Modified"] = mod_match.group(1).strip()
            
        stat_match = re.search(r'Status:\s*(\w+)', table_text, re.I)
        if stat_match: meta["Status"] = stat_match.group(1).strip()

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
                if i + 1 < len(tds): description = tds[i+1].get_text(strip=True)
                break
        if apar_num and apar_num not in seen:
            seen.add(apar_num)
            queue.append({"num": apar_num, "isSecurity": is_sec, "table_desc": description})
            
    return queue, meta

def write_markdown_row(md_file, data, fields):
    row = "| " + " | ".join(str(data.get(f, "N/A")) for f in fields) + " |"
    md_file.write(row + "\n")

def main():
    print("--- IBM Consolidated APARs for for WAS and IHS version 8/9 ---")
    user_version = input("Enter Fix Pack Version (e.g., 9.0.5.26 or 9.0.0.0/8.0.0.0 for latest): ").strip()
    headers = {"User-Agent": "Mozilla/5.0"}

    # Base URLs for version detection
    v9_base = "https://www.ibm.com/support/pages/fix-list-ibm-websphere-application-server-traditional-v9-0"
    v8_base = "https://www.ibm.com/support/pages/fix-list-ibm-websphere-application-server-v85"

    # AUTO-DETECT LATEST VERSION
    if user_version in ["9.0.0.0", "8.0.0.0"]:
        print(f"Version {user_version} detected. Finding latest released version...")
        target_url = v9_base if user_version.startswith("9.") else v8_base
        latest = find_latest_version(target_url, headers)
        if latest:
            print(f"Latest version found: {latest}")
            user_version = latest
        else:
            print("Could not detect latest version. Proceeding with input.")

    version_anchor = user_version.replace(".", "")
    fields = ["Source", "APAR Number", "isSecurity", "Title", "Reported component name", "Status", "PE", "HIPER", "Submitted date", "Closed date"]
    
    if user_version.startswith("9."):
        was_url = f"{v9_base}#{version_anchor}"
    elif user_version.startswith("8."):
        was_url = f"{v8_base}#{version_anchor}"
    else:
        print("Error: Major version must be 8 or 9.")
        return
    base_prefix = f"was_fixpack_{version_anchor}"
    counts = {"WAS": 0, "IHS": 0}
    collected_meta = {}
    sources = [
        {"name": "WAS", "url": was_url, "class": "bx--data-table", "find_meta": True},
        {"name": "IHS", "url": "https://www.ibm.com/support/pages/node/617655", "class": "bx--data-table", "find_meta": False}
    ]

    final_csv, final_md = None, None

    for src in sources:
        print(f"\nProcessing {src['name']}...")
        try:
            resp = requests.get(src['url'], headers=headers, timeout=15)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                queue, meta = scrape_table_logic(soup, version_anchor, table_class=src['class'], find_meta=src['find_meta'])
                
                if src['find_meta']:
                    collected_meta = meta
                    file_date = format_date_for_file(meta['Release Date'])
                    final_csv = f"{base_prefix}_{file_date}.csv"
                    final_md = f"{base_prefix}_{file_date}.md"
                
                if not final_csv:
                    final_csv = f"{base_prefix}_NoDate.csv"
                    final_md = f"{base_prefix}_NoDate.md"

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

    print(f"\n" + "="*45 + f"\nFIX PACK DETAILS ({user_version})\n" + "="*45)
    if collected_meta:
        print(f"Fix Release Date: {collected_meta.get('Release Date')}\nLast Modified:    {collected_meta.get('Last Modified')}\nStatus:           {collected_meta.get('Status')}")
    print("-"*45 + f"\nCSV Report: {final_csv}\nMD Report:  {final_md}\nTotals:     WAS ({counts['WAS']}), IHS ({counts['IHS']})\n" + "="*45)

if __name__ == "__main__":
    main()