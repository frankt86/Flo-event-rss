import requests
from bs4 import BeautifulSoup
import datetime
import calendar
import time
import re
import json
import PyRSS2Gen
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import urllib.parse

class FloGrapplingEventScraper:
    def __init__(self):
        self.base_url = "https://www.flograppling.com/events"
        self.facets = {"Streaming Source": "FloSports", "Event Type": "Brazilian Jiu-Jitsu"}
        
    def get_date_range(self):
        """Generate a list of dates from 1 year ago to 2 months in the future."""
        today = datetime.date.today()
        
        # One year ago
        start_date = today.replace(year=today.year - 1)
        
        # Two months in the future
        end_month = today.month + 2
        end_year = today.year
        if end_month > 12:
            end_month -= 12
            end_year += 1
        end_date = today.replace(year=end_year, month=end_month)
        
        date_list = []
        current_date = start_date.replace(day=1)
        
        while current_date <= end_date:
            date_list.append(current_date.strftime("%Y-%m-%d"))
            # Move to first day of next month
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)
                
        return date_list
    
    def create_url(self, date):
        """Create the URL for a specific month."""
        facets_string = urllib.parse.quote(json.dumps(self.facets))
        return f"{self.base_url}?date={date}&facets={facets_string}"
    
    def setup_browser(self):
        """Set up headless Chrome browser for Selenium."""
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        
        # This is important for GitHub Actions
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-setuid-sandbox")
        
        # Create the browser
        return webdriver.Chrome(options=chrome_options)
    
    def parse_events_from_page(self, browser):
        """Parse events from the loaded page using Selenium."""
        events = []
        
        try:
            # Wait for the event cards to load
            wait = WebDriverWait(browser, 10)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".event-card, .events-list")))
            
            # Give a little extra time for all content to load
            time.sleep(3)
            
            # Get the page source after JavaScript has loaded the content
            page_source = browser.page_source
            soup = BeautifulSoup(page_source, 'html.parser')
            
            # Debug: Save the HTML to examine
            with open("debug_page.html", "w", encoding="utf-8") as f:
                f.write(page_source)
            
            # First, try the most likely selector for event cards
            event_elements = soup.select(".event-card")
            
            # If that doesn't work, try other possible selectors
            if not event_elements:
                event_elements = soup.select(".event-list-item")
            
            if not event_elements:
                event_elements = soup.select(".events-list .event")
            
            # If still no events found, look for any divs that might contain event info
            if not event_elements:
                print("No event cards found with common selectors. Trying to find alternative elements...")
                
                # Look for elements with "event" in their class name
                event_elements = soup.select("[class*=event]")
                
                # Print out the classes for debugging
                class_names = set()
                for element in soup.select("[class]"):
                    for class_name in element.get("class", []):
                        if "event" in class_name.lower():
                            class_names.add(class_name)
                print(f"Found potential event-related classes: {', '.join(class_names)}")
            
            print(f"Found {len(event_elements)} potential event elements")
            
            for event_element in event_elements:
                # Print the raw HTML of the event for debugging
                print(f"Processing event element: {event_element}")
                
                # Try to extract event details
                title = None
                link = None
                date_text = None
                location = None
                
                # Look for title
                title_element = event_element.select_one(".event-title, h2, h3, [class*=title]")
                if title_element:
                    title = title_element.text.strip()
                    
                    # Look for link
                    link_element = title_element.find('a') or event_element.find('a')
                    if link_element and link_element.get('href'):
                        link = "https://www.flograppling.com" + link_element.get('href') if link_element.get('href').startswith('/') else link_element.get('href')
                
                # If no title found yet, try harder
                if not title:
                    # Look for any heading elements
                    heading = event_element.find(["h1", "h2", "h3", "h4", "h5", "h6"])
                    if heading:
                        title = heading.text.strip()
                
                # Look for date
                date_element = event_element.select_one(".event-date, [class*=date]")
                if date_element:
                    date_text = date_element.text.strip()
                
                # Look for location
                location_element = event_element.select_one(".event-location, [class*=location]")
                if location_element:
                    location = location_element.text.strip()
                
                if title:
                    # Try to parse the date
                    event_date = datetime.datetime.now()  # Default to now
                    if date_text:
                        # Try various date formats
                        date_formats = [
                            "%b %d, %Y",  # Mar 15, 2025
                            "%B %d, %Y",  # March 15, 2025
                            "%m/%d/%Y",   # 03/15/2025
                            "%Y-%m-%d"    # 2025-03-15
                        ]
                        
                        for date_format in date_formats:
                            try:
                                event_date = datetime.datetime.strptime(date_text, date_format)
                                break
                            except ValueError:
                                continue
                    
                    if not link:
                        link = browser.current_url
                    
                    description = f"<p><strong>{title}</strong></p>"
                    if date_text:
                        description += f"<p>Date: {date_text}</p>"
                    if location:
                        description += f"<p>Location: {location}</p>"
                    description += f"<p>View on FloGrappling: <a href='{link}'>{title}</a></p>"
                    
                    events.append({
                        'title': title,
                        'link': link,
                        'description': description,
                        'pubDate': event_date,
                        'guid': link
                    })
            
            if not events:
                print("No events could be extracted from the page.")
                print(f"Page URL: {browser.current_url}")
            
        except Exception as e:
            print(f"Error parsing events: {e}")
        
        return events
    
    def fetch_events_for_month(self, browser, date):
        """Fetch all events for a specific month using Selenium."""
        url = self.create_url(date)
        print(f"Fetching events for {date} from {url}")
        
        try:
            browser.get(url)
            
            # Wait for page to load (this may need adjustment)
            WebDriverWait(browser, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Give some extra time for JavaScript to run
            time.sleep(5)
            
            # Parse events from the loaded page
            events = self.parse_events_from_page(browser)
            print(f"Found {len(events)} events for {date}")
            
        except Exception as e:
            print(f"Error fetching events for {date}: {e}")
            events = []
        
        return events
    
    def fetch_all_events(self):
        """Fetch events for all months in the date range."""
        all_events = []
        date_range = self.get_date_range()
        
        browser = self.setup_browser()
        try:
            for date in date_range:
                monthly_events = self.fetch_events_for_month(browser, date)
                all_events.extend(monthly_events)
                # Brief pause between requests
                time.sleep(2)
        finally:
            browser.quit()
            
        return all_events
    
    def create_rss_feed(self, events, output_path="flograppling_events.xml"):
        """Create an RSS feed from the events."""
        if not events:
            print("No events to include in the feed.")
            # Create an empty feed with a message
            rss = PyRSS2Gen.RSS2(
                title="FloGrappling BJJ Events",
                link="https://www.flograppling.com/events",
                description="Upcoming and past BJJ events from FloGrappling",
                lastBuildDate=datetime.datetime.now(),
                items=[
                    PyRSS2Gen.RSSItem(
                        title="No events found",
                        link="https://www.flograppling.com/events",
                        description="No events were found in the scrape. This could be due to website changes or no events being scheduled.",
                        guid=PyRSS2Gen.Guid("https://www.flograppling.com/events#no-events-" + datetime.datetime.now().strftime("%Y%m%d")),
                        pubDate=datetime.datetime.now()
                    )
                ]
            )
        else:
            rss_items = []
            for event in events:
                try:
                    rss_item = PyRSS2Gen.RSSItem(
                        title=event['title'],
                        link=event['link'],
                        description=event['description'],
                        guid=PyRSS2Gen.Guid(event['guid']),
                        pubDate=event['pubDate']
                    )
                    rss_items.append(rss_item)
                except Exception as e:
                    print(f"Error creating RSS item: {e}")
            
            rss = PyRSS2Gen.RSS2(
                title="FloGrappling BJJ Events",
                link="https://www.flograppling.com/events",
                description="Upcoming and past BJJ events from FloGrappling",
                lastBuildDate=datetime.datetime.now(),
                items=rss_items
            )
        
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            rss.write_xml(f)
            
        print(f"RSS feed created at {output_path}")
        return output_path


def main():
    scraper = FloGrapplingEventScraper()
    events = scraper.fetch_all_events()
    
    # Create docs directory if it doesn't exist
    os.makedirs("docs", exist_ok=True)
    
    # Save the RSS feed in the docs directory
    scraper.create_rss_feed(events, "docs/flograppling_events.xml")
    
    # Create a simple index.html file
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write("""
        <!DOCTYPE html>
        <html>
        <head>
            <title>FloGrappling BJJ Events RSS Feed</title>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; margin: 0; padding: 20px; max-width: 800px; margin: 0 auto; }
                header { margin-bottom: 20px; }
                a { color: #0066cc; }
                .feed-info { background-color: #f0f0f0; padding: 15px; border-radius: 5px; margin-bottom: 20px; }
            </style>
        </head>
        <body>
            <header>
                <h1>FloGrappling BJJ Events RSS Feed</h1>
            </header>
            <div class="feed-info">
                <p>This is an automatically updated RSS feed of BJJ events from FloGrappling.</p>
                <p>Last updated: """ + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC") + """</p>
                <p><a href="flograppling_events.xml">Subscribe to the RSS Feed</a></p>
            </div>
            <p>This feed is updated daily via GitHub Actions.</p>
            <p>Events found: """ + str(len(events)) + """</p>
        </body>
        </html>
        """)


if __name__ == "__main__":
    main()
