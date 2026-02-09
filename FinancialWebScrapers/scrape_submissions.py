import json
import requests
from typing import List, Optional
from pydantic import BaseModel, Field
from pymongo import MongoClient
from datetime import datetime

# filepath: /home/steevesj/github/Financial_Tools/FinancialWebScrapers/scrape_submissions.py

# Pydantic Models
class Submission(BaseModel):
    accession_number: str
    filing_date: str
    report_date: str
    form_type: str
    
class CompanySubmission(BaseModel):
    cik: str
    ticker: str
    company_name: str
    submissions: List[Submission] = Field(default_factory=list)
    scraped_at: str = Field(default_factory=lambda: datetime.now().isoformat())



# MongoDB connection
class MongoDBConnection:
    def __init__(self, uri: str = "mongodb://localhost:27017/", db_name: str = "finance_database"):
        self.client = MongoClient(uri)
        self.db = self.client[db_name]
        self.collection = self.db["company-facts"]
    
    def insert_submission(self, data: CompanySubmission):
        result = self.collection.insert_one(data.dict())
        return result.inserted_id
    
    def close(self):
        self.client.close()

# Main scraper functions
def load_tickers(filepath: str = "tickers.json") -> dict:
    with open(filepath, 'r') as f:
        return json.load(f)

def fetch_submissions(ticker: str, cik: str) -> Optional[dict]:
    user_agent = {"user-agent": "www.jonsteeves.dev jonathonsteeves@cmail.carleton.ca"}
    submissions_url = f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"
    
    try:
        res = requests.get(submissions_url, headers=user_agent)
        res.raise_for_status()
        return res.json()
    except requests.RequestException as e:
        print(f"Error fetching submissions for {ticker}: {e}")
        return None

def parse_submissions(data: dict, ticker: str, cik: str, company_name: str) -> CompanySubmission:
    submissions_list = []
    
    if "filings" in data and "recent" in data["filings"]:
        recent = data["filings"]["recent"]
        for i in range(min(len(recent.get("accessionNumber", [])), 100)):
            submission = Submission(
                accession_number=recent["accessionNumber"][i],
                filing_date=recent["filingDate"][i],
                report_date=recent["reportDate"][i],
                form_type=recent["form"][i]
            )
            submissions_list.append(submission)
    
    return CompanySubmission(
        cik=cik,
        ticker=ticker,
        company_name=company_name,
        submissions=submissions_list
    )

def scrape_and_store():
    tickers = load_tickers()
    db = MongoDBConnection()
    
    for ticker, ticker_data in tickers.items():
        print(f"Processing {ticker}...")
        
        cik = ticker_data.get("cik")
        company_name = ticker_data.get("name", "Unknown")
        
        if not cik:
            print(f"  Skipping {ticker}: No CIK found")
            continue
        
        # Fetch submissions
        submissions_data = fetch_submissions(ticker, cik)
        if not submissions_data:
            continue
        
        # Parse and create model
        company_submission = parse_submissions(submissions_data, ticker, str(cik), company_name)
        
        # Insert into MongoDB
        try:
            inserted_id = db.insert_submission(company_submission)
            print(f"  ✓ Inserted {ticker} with ID: {inserted_id}")
        except Exception as e:
            print(f"  ✗ Error inserting {ticker}: {e}")
    
    db.close()
    print("Scraping complete!")

if __name__ == "__main__":
    scrape_and_store()