import asyncio
import datetime
import json
import os
import PyRSS2Gen
from playwright.async_api import async_playwright
import urllib.parse
import time

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
    
    async def fetch_events_for_month(self, page, date):
        """Fetch events for a specific month using Playwright."""
        url = self.create_url(date)
        print(f"Fetching events for {date} from {url}")
        
        try:
            # Navigate to the URL
            await page.goto(url, wait_until="networkidle")
            
            # Wait for content to load - adjust selectors based on actual page structure
            await asyncio.sleep(3)  # Additional time for JavaScript to execute
            
            # Look for specific event date entries
            event_rows = await page.query_selector_all("tr, .event-row, [class*='event-item'], [class*='event-card'], [class*='event-list-item']")
            
            events = []
            print(f"Found {len(event_rows)} potential event elements")
            
            if len(event_rows) == 0:
                # If no specific event rows found, try a more general approach - take a screenshot for debugging
                screenshot_path = f"debug_{date.replace('-', '_')}.png"
                await page.screenshot(path=screenshot_path)
                print(f"Saved debug screenshot to {screenshot_path}")
                
                # Look for date headers which may indicate event dates
                date_headers = await page.query_selector_all("h2, h3, h4, [class*='date-header']")
                print(f"Found {len(date_headers)} potential date headers")
                
                for header in date_headers:
                    header_text = await header.text_content()
                    print(f"Date header: {header_text}")
                    
                    # Try to extract event info from nearby elements
                    events_section = await header.evaluate("""
                        header => {
                            const section = document.createElement('div');
                            let current = header.nextElementSibling;
                            while (current && !current.matches('h2, h3, h4, [class*="date-header"]')) {
                                section.appendChild(current.cloneNode(true));
                                current = current.nextElementSibling;
                            }
                            return section.innerHTML;
                        }
                    """)
                    
                    print(f"Events section HTML length: {len(events_section) if events_section else 0}")
            
            # Extract structured event data
            events_data = await page.evaluate("""
                () => {
                    // Look for event entries in various formats
                    const eventEntries = [];
                    
                    // Try to find event rows/cards/items
                    document.querySelectorAll('tr, [class*="event-row"], [class*="event-card"], [class*="event-item"], [class*="event-list-item"]').forEach(row => {
                        // Get event text content
                        const rowText = row.textContent.trim();
                        if (!rowText) return;
                        
                        // Look for event title
                        let title = '';
                        const titleEl = row.querySelector('h2, h3, h4, [class*="title"], [class*="event-name"], td:nth-child(2)');
                        if (titleEl) {
                            title = titleEl.textContent.trim();
                        }
                        
                        // Skip if no meaningful title
                        if (!title || title === 'EVENT' || title === 'STREAMING') return;
                        
                        // Try to get date
                        let eventDate = '';
                        let time = '';
                        
                        // Look for date/time elements
                        const dateEl = row.querySelector('[class*="date"], [class*="time"], td:nth-child(1)');
                        if (dateEl) {
                            const dateText = dateEl.textContent.trim();
                            if (dateText) {
                                // Check if it contains date or time format
                                if (dateText.match(/\\d{1,2}[:h]/)) {
                                    time = dateText;
                                } else if (dateText.match(/\\d{1,4}[-/]\\d{1,2}|\\w+ \\d{1,2}/)) {
                                    eventDate = dateText;
                                } else {
                                    time = dateText;
                                }
                            }
                        }
                        
                        // Look for location
                        let location = '';
                        const locationEl = row.querySelector('[class*="location"], [class*="venue"], td:nth-child(3)');
                        if (locationEl) {
                            location = locationEl.textContent.trim();
                        }
                        
                        // Get link if available
                        let link = '';
                        const linkEl = row.querySelector('a');
                        if (linkEl && linkEl.href) {
                            link = linkEl.href;
                        }
                        
                        // Only add if we have a title
                        if (title) {
                            eventEntries.push({
                                title,
                                date: eventDate,
                                time,
                                location,
                                link
                            });
                        }
                    });
                    
                    // As a backup, try to find date headers and associated events
                    if (eventEntries.length === 0) {
                        document.querySelectorAll('h2, h3, h4, [class*="date-header"]').forEach(header => {
                            const headerText = header.textContent.trim();
                            if (!headerText) return;
                            
                            // Check if it looks like a date
                            const isDateLike = headerText.match(/\\d{1,2}[,\\s]+\\d{4}|\\w+\\s+\\d{1,2}/i);
                            if (!isDateLike) return;
                            
                            // Look at siblings until next header
                            let current = header.nextElementSibling;
                            while (current && !current.matches('h2, h3, h4, [class*="date-header"]')) {
                                const eventTitle = current.textContent.trim();
                                if (eventTitle && eventTitle.length > 5) {
                                    let link = '';
                                    const linkEl = current.querySelector('a');
                                    if (linkEl && linkEl.href) {
                                        link = linkEl.href;
                                    }
                                    
                                    eventEntries.push({
                                        title: eventTitle,
                                        date: headerText,
                                        time: '',
                                        location: '',
                                        link
                                    });
                                }
                                current = current.nextElementSibling;
                            }
                        });
                    }
                    
                    return eventEntries;
                }
            """)
            
            print(f"Extracted {len(events_data)} events via JavaScript")
            
            for event_data in events_data:
                title = event_data.get('title', '').strip()
                if not title:
                    continue
                    
                location = event_data.get('location', '').strip()
                event_date_text = event_data.get('date', '').strip()
                event_time_text = event_data.get('time', '').strip()
                link = event_data.get('link', '').strip()
                
                if not link and title:
                    link = f"{self.base_url}#{urllib.parse.quote(title)}"
                    
                # Try to parse the date
                event_date = datetime.datetime.now()  # Default to now
                
                date_formats = [
                    "%B %d, %Y",    # March 19, 2025
                    "%b %d, %Y",    # Mar 19, 2025
                    "%Y-%m-%d",     # 2025-03-19
                    "%m/%d/%Y",     # 03/19/2025
                    "%d %B %Y",     # 19 March 2025
                    "%d %b %Y",     # 19 Mar 2025
                ]
                
                # Parse just the date portion first if present
                if event_date_text:
                    for fmt in date_formats:
                        try:
                            event_date = datetime.datetime.strptime(event_date_text, fmt)
                            break
                        except ValueError:
                            continue
                
                # Then try to add the time if present
                if event_time_text:
                    try:
                        # Try common time formats
                        if ":" in event_time_text:
                            time_parts = event_time_text.split()
                            time_value = time_parts[0]
                            am_pm = time_parts[1] if len(time_parts) > 1 else ""
                            
                            hour, minute = time_value.split(":")
                            hour = int(hour)
                            minute = int(minute)
                            
                            if am_pm.lower() == "pm" and hour < 12:
                                hour += 12
                            
                            event_date = event_date.replace(hour=hour, minute=minute)
                    except Exception as e:
                        print(f"Error parsing time '{event_time_text}': {e}")
                
                # Create description with all available info
                description = f"<p><strong>{title}</strong></p>"
                if event_date_text:
                    description += f"<p>Date: {event_date_text}</p>"
                if event_time_text:
                    description += f"<p>Time: {event_time_text}</p>"
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
            
            print(f"Processed and found {len(events)} events for {date}")
            return events
            
        except Exception as e:
            print(f"Error fetching events for {date}: {e}")
            return []
    
    async def fetch_all_events(self):
        """Fetch events for all months in the date range."""
        all_events = []
        date_range = self.get_date_range()
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={'width': 1280, 'height': 720},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            )
            page = await context.new_page()
            
            for date in date_range:
                monthly_events = await self.fetch_events_for_month(page, date)
                all_events.extend(monthly_events)
                await asyncio.sleep(1)  # Small delay between requests
            
            await browser.close()
            
        return all_events
    
    def create_rss_feed(self, events, output_path="docs/flograppling_events.xml"):
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


async def main():
    scraper = FloGrapplingEventScraper()
    events = await scraper.fetch_all_events()
    
    # Create docs directory if it doesn't exist
    os.makedirs("docs", exist_ok=True)
    
    # Save the RSS feed in the docs directory
    scraper.create_rss_feed(events)
    
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
                .event-list { margin-top: 20px; }
                .event-item { border-bottom: 1px solid #ddd; padding: 10px 0; }
                .event-title { font-weight: bold; }
                .event-date { color: #666; }
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
            <div class="event-list">
                <h2>Events Found: """ + str(len(events)) + """</h2>
                """ + 
                "\n".join([
                    f"""<div class="event-item">
                        <div class="event-title">{event['title']}</div>
                        <div class="event-date">{event['pubDate'].strftime('%Y-%m-%d')}</div>
                        <div>{event['description']}</div>
                    </div>"""
                    for event in sorted(events, key=lambda x: x['pubDate'])[:10]  # Show first 10 events
                ]) if events else "<p>No events found in the latest scrape.</p>"
                + """
            </div>
            <p>This feed is updated daily via GitHub Actions.</p>
        </body>
        </html>
        """)


if __name__ == "__main__":
    asyncio.run(main())
