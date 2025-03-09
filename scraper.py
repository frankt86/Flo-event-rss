import requests
from bs4 import BeautifulSoup
import datetime
import calendar
import time
import re
import json
import PyRSS2Gen
import os

class FloGrapplingEventScraper:
    def __init__(self):
        self.base_url = "https://www.flograppling.com/events"
        self.facets = {"Streaming Source": "FloSports", "Event Type": "Brazilian Jiu-Jitsu"}
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
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
        facets_json = json.dumps(self.facets)
        return f"{self.base_url}?date={date}&facets={facets_json}"
    
    def parse_event(self, event_element):
        """Parse a single event element and extract relevant details."""
        try:
            title_element = event_element.find('h2', class_='event-title')
            title = title_element.text.strip() if title_element else "Unknown Event"
            
            link = self.base_url
            if title_element and title_element.find('a'):
                link = "https://www.flograppling.com" + title_element.find('a').get('href', '')
            
            date_element = event_element.find('div', class_='event-date')
            date_text = date_element.text.strip() if date_element else ""
            
            location_element = event_element.find('div', class_='event-location')
            location = location_element.text.strip() if location_element else "Location not specified"
            
            # Try to parse the date
            event_date = None
            try:
                # This parsing will depend on the actual format on the site
                # Example format: "Mar 15, 2025"
                event_date = datetime.datetime.strptime(date_text, "%b %d, %Y")
            except:
                event_date = datetime.datetime.now()  # Fallback
            
            description = f"<p><strong>{title}</strong></p><p>Date: {date_text}</p><p>Location: {location}</p><p>View on FloGrappling: <a href='{link}'>{title}</a></p>"
            
            return {
                'title': title,
                'link': link,
                'description': description,
                'pubDate': event_date,
                'guid': link
            }
        except Exception as e:
            print(f"Error parsing event: {e}")
            return None
    
    def fetch_events_for_month(self, date):
        """Fetch all events for a specific month."""
        url = self.create_url(date)
        print(f"Fetching events for {date} from {url}")
        
        events = []
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            event_elements = soup.find_all('div', class_='event-card')  # Adjust this selector based on actual HTML
            
            for event_element in event_elements:
                event_data = self.parse_event(event_element)
                if event_data:
                    events.append(event_data)
                    
            print(f"Found {len(events)} events for {date}")
            
        except Exception as e:
            print(f"Error fetching events for {date}: {e}")
            
        # Add a delay to be nice to the server
        time.sleep(2)
        
        return events
    
    def fetch_all_events(self):
        """Fetch events for all months in the date range."""
        all_events = []
        date_range = self.get_date_range()
        
        for date in date_range:
            monthly_events = self.fetch_events_for_month(date)
            all_events.extend(monthly_events)
            
        return all_events
    
    def create_rss_feed(self, events, output_path="flograppling_events.xml"):
        """Create an RSS feed from the events."""
        if not events:
            print("No events to include in the feed.")
            return
        
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
        </body>
        </html>
        """)


if __name__ == "__main__":
    main()
