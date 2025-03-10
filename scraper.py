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
                title = event_data.get('
