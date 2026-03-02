# IBM WebSphere & IHS Fix Pack Summary

This Python script retrieves IBM's support pages to gather information about APARs (Authorized Program Analysis Reports) included in a specific IBM WebSphere Application Server (WAS) V9 fix pack. It consolidates data for both WAS and the corresponding IBM HTTP Server (IHS) fix pack into CSV and Markdown files.

## Features

*   **Consolidated Data:** Gathers APARs for both WebSphere Application Server and IBM HTTP Server.
*   **Fix Pack Specific:** Fetches the list of APARs associated with a user-provided fix pack version (e.g., `9.0.5.26`).
*   **Detailed Metadata:** For non-security APARs, it visits the individual APAR page to scrape metadata such as Component, Status, Submitted/Closed dates, and more.
*   **Dual Export:** Saves all collected information into clean, easy-to-use CSV and Markdown files.

## Prerequisites

*   Python 3
*   Required Python libraries: `requests` and `beautifulsoup4`.

You can install the dependencies using pip:
```bash
pip install requests beautifulsoup4
```

## Usage

1.  Run the script from your terminal:
    ```bash
    python was_apar_by_fixpack.py
    ```
2.  The script will prompt you to enter the desired fix pack version (in `V.R.M.F` format). The program will then process both WAS and IHS sources and display its progress.

### Example Execution

```
--- IBM Consolidated APAR Scraper (WAS & IHS) ---
Enter Fix Pack Version (e.g., 9.0.5.26 or 8.5.5.29): 9.0.5.26

[1/2] Processing WAS...
   [1/27] PH66923 (WAS)
   [2/27] PH68469 (WAS)
   ...
   [27/27] PH67458 (WAS)

[2/2] Processing IHS...
   [1/6] PH67551 (IHS)
   [2/6] PH67623 (IHS)
   ...
   [6/6] PH68132 (IHS)

=============================================
FIX PACK DETAILS (9.0.5.26)
=============================================
Fix Release Date: 2 December 2025
Last Modified:    2 December 2025
Status:           Recommended
---------------------------------------------
CSV Report: was_fixpack_90526_20251202.csv
MD Report:  was_fixpack_90526_20251202.md
Totals:     WAS (27), IHS (6)
=============================================
```

## Output Format

The script generates a CSV file named `was_fix_pack_<version>.csv` (e.g., `was_fix_pack_90526.csv`).

The columns include: `Source`, `APAR Number`, `isSecurity`, `Title`, `Reported component name`, `Status`, `PE`, `HIPER`, `Submitted date`, `Closed date`.

### Example CSV Output ([was_fixpack_90526_20251202.csv](was9_fixpack_90526_20251202.csv))

```csv
Source,APAR Number,isSecurity,Title,Reported component name,Status,PE,HIPER,Submitted date,Closed date
WAS,PH66923,N,OOM HEAP ISSUE WHILE NAVIGATING ON ADMIN CONSOLE-LOGGING PANEL,WEBSPHERE APP S,CLOSED  PER,NoPE,NoHIPER,2025-06-10,2025-08-08
WAS,PH67137,Y,WebSphere Application Server is affected by a denial of service due to Apache commons fileupload (CVE-2025-48976 CVSS 7.5),N/A,N/A,N/A,N/A,N/A,N/A
IHS,PH67551,N,Fix potential bug in PH61590 and adderror_loglogging,WAS IHS ZOS,CLOSED  PER,NoPE,NoHIPER,2025-07-29,2025-11-12
IHS,PH67676,N,Add additional directories torpath/runpathofhttpdbinaries,N/A,N/A,N/A,N/A,N/A,N/A
```
### Example MD Output ([was9_fixpack_90526_20251202.md](was9_fixpack_90526_20251202.md))
## Important Note on Security APARs

For APARs marked as security-related (`isSecurity` = `Y`), the script **does not** scrape the individual APAR detail page. This is an intentional design choice due to different APAR detailed inforamtion. You can find more information from CVE and CVSS in column title. 
