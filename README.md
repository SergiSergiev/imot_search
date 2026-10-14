# Imot.bg Agency Property Assistant

This project scrapes property listings from **imot.bg** for one or more selected real estate agencies, stores the listings in a structured database, and provides an interface where a user can ask natural-language questions to find the best matching properties.

The goal is not only to collect listings, but to make them searchable and useful: “Find me the best 2-bedroom apartment near a metro station under 250,000 EUR”, “Which listings look overpriced?”, “Show me properties suitable for investment”, or “Compare these three offers.”

## Goals

- Scrape listings from imot.bg for selected agencies.
- Extract structured property data such as price, location, size, rooms, floor, building type, description, agency, broker contact, photos, and listing URL.
- Keep historical snapshots so price changes and removed listings can be tracked.
- Create a searchable database of listings.
- Provide a natural-language assistant that helps users find the best match based on their criteria.
- Rank and explain recommended properties, not just return keyword matches.

## Important Notes

Before implementing scraping, review imot.bg terms of service and `robots.txt`.

The scraper should be polite and conservative:

- Use low request rates.
- Cache pages where possible.
- Avoid aggressive crawling.
- Respect blocked pages or anti-bot signals.
- Do not collect personal data beyond what is publicly shown on listing pages.
- Store source URLs for traceability.

## Main Use Case

1. The user selects one or more agencies from imot.bg.
2. The scraper collects all current listings for those agencies.
3. The system parses each listing into structured fields.
4. Listings are stored in a database.
5. The user opens an interface and asks questions in natural language.
6. The assistant filters, ranks, compares, and explains the best matches.

Example user questions:

- “Find me a 2-bedroom apartment in Sofia under 250k EUR with parking.”
- “Show the best investment properties from this agency.”
- “Which properties have the lowest price per square meter?”
- “Find listings similar to this one, but cheaper.”
- “Which listings look like they have stale prices or weak descriptions?”
- “Compare the top 5 matches and explain the trade-offs.”

## Proposed Architecture

```mermaid
flowchart TD
    A["Agency URLs"] --> B["Scraper"]
    B --> C["Listing Parser"]
    C --> D["Database"]
    D --> E["Search & Ranking"]
    E --> F["Chat Interface"]
```

## Suggested Tech Stack

The exact stack can be changed, but this is a practical starting point:

- **Python** for scraping, parsing, ranking, and backend logic.
- **Playwright** if pages require browser rendering.
- **Requests + BeautifulSoup** if static HTML is enough.
- **PostgreSQL** for structured listing storage.
- **pgvector** or a vector database for semantic search over descriptions.
- **FastAPI** for the backend API.
- **Streamlit** for a fast internal prototype UI, or React/Next.js for a more polished product.
- **OpenAI API or another LLM provider** for natural-language interpretation and answer generation.

## Data Model

Recommended initial database tables:

### `agencies`

| Field | Description |
| --- | --- |
| `id` | Internal agency ID |
| `name` | Agency name |
| `imot_bg_url` | Agency page URL |
| `is_active` | Whether scraping is enabled |
| `created_at` | Creation timestamp |

### `listings`

| Field | Description |
| --- | --- |
| `id` | Internal listing ID |
| `source_listing_id` | Listing ID from imot.bg if available |
| `agency_id` | Related agency |
| `url` | Original listing URL |
| `title` | Listing title |
| `property_type` | Apartment, house, office, land, etc. |
| `city` | City |
| `district` | District or neighborhood |
| `address_text` | Raw location text |
| `price` | Listing price |
| `currency` | EUR, BGN, etc. |
| `area_sqm` | Area in square meters |
| `price_per_sqm` | Calculated price per square meter |
| `rooms` | Number of rooms if available |
| `bedrooms` | Number of bedrooms if available |
| `floor` | Floor |
| `total_floors` | Total floors |
| `building_type` | Brick, panel, new construction, etc. |
| `year_built` | Construction year if available |
| `description` | Full listing description |
| `features` | Extracted amenities and tags |
| `image_urls` | Listing images |
| `contact_name` | Broker/contact name if public |
| `contact_phone` | Broker/contact phone if public |
| `first_seen_at` | First scrape timestamp |
| `last_seen_at` | Last scrape timestamp |
| `status` | Active, removed, changed |

### `listing_snapshots`

Use this table to track changes over time.

| Field | Description |
| --- | --- |
| `id` | Snapshot ID |
| `listing_id` | Related listing |
| `scraped_at` | Snapshot timestamp |
| `price` | Price at scrape time |
| `description` | Description at scrape time |
| `raw_html_path` | Optional saved raw HTML path |
| `raw_json` | Parsed raw data |

## Scraping Flow

1. Start from selected agency page URLs.
2. Discover pagination and listing URLs.
3. Visit each listing page.
4. Parse structured fields.
5. Normalize values:
   - Convert prices to numeric values.
   - Standardize currencies.
   - Normalize area and price per square meter.
   - Extract city, district, and property type.
6. Deduplicate listings by source listing ID or canonical URL.
7. Save current listing state.
8. Save a snapshot for historical comparison.
9. Mark listings as removed if they disappear from the agency page after repeated checks.

## Matching and Ranking Logic

The assistant should combine structured filters with semantic understanding.

Recommended approach:

1. Parse the user query into constraints:
   - Budget
   - Location
   - Property type
   - Size
   - Rooms
   - Must-have features
   - Nice-to-have features
   - Investment or personal-use intent
2. Apply hard filters first.
3. Score remaining listings using:
   - Price fit
   - Location fit
   - Area and room fit
   - Feature match
   - Price per square meter
   - Listing freshness
   - Description quality
   - Semantic similarity between query and description
4. Return ranked matches.
5. Explain why each listing is recommended.
6. Highlight trade-offs and missing information.

Example ranking output:

| Rank | Listing | Why It Matches | Trade-off |
| --- | --- | --- | --- |
| 1 | 2-bedroom, Lozenets | Good location, within budget, strong size/price ratio | Older building |
| 2 | 3-room, Manastirski Livadi | Larger area, newer building | Weaker transport access |
| 3 | 2-bedroom, Mladost | Near metro, lower price | Smaller area |

## Interface Requirements

The first version can be simple, but should support:

- Agency selector.
- Scrape status view.
- Listing table with filters.
- Natural-language question box.
- Ranked answer results.
- Listing comparison view.
- Link back to the original imot.bg listing.
- Explanation for every recommendation.

Suggested Streamlit prototype pages:

- `Agencies`: add and manage agency URLs.
- `Scraper`: run scraping and inspect logs.
- `Listings`: browse and filter collected listings.
- `Ask`: ask questions and get ranked recommendations.
- `Compare`: compare selected listings side by side.

## Example User Interface Flow

1. User adds an agency URL.
2. User clicks “Scrape agency”.
3. The system shows:
   - Number of discovered listings.
   - Number of successfully parsed listings.
   - Number of changed or removed listings.
4. User goes to the “Ask” page.
5. User asks: “Find the best apartments for investment in Sofia under 200k EUR.”
6. The assistant returns:
   - Top matching listings.
   - Short reasoning.
   - Price per square meter comparison.
   - Potential concerns.
   - Original links.

## Suggested Project Structure

```text
imot-agency-assistant/
├── README.md
├── pyproject.toml
├── .env.example
├── app/
│   ├── main.py
│   ├── config.py
│   ├── db.py
│   ├── models.py
│   ├── scraper/
│   │   ├── agency_scraper.py
│   │   ├── listing_parser.py
│   │   └── normalizer.py
│   ├── search/
│   │   ├── query_parser.py
│   │   ├── ranking.py
│   │   └── embeddings.py
│   └── api/
│       ├── agencies.py
│       ├── listings.py
│       └── assistant.py
├── ui/
│   └── streamlit_app.py
├── tests/
│   ├── test_parser.py
│   ├── test_normalizer.py
│   └── test_ranking.py
└── data/
    ├── raw/
    └── exports/
```

## Environment Variables

Create a `.env` file based on `.env.example`.

```env
DATABASE_URL=postgresql://user:password@localhost:5432/imot_assistant
OPENAI_API_KEY=
SCRAPER_USER_AGENT=ImotAgencyAssistant/0.1
SCRAPER_DELAY_SECONDS=3
```

## Development Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Run the backend:

```bash
uvicorn app.main:app --reload
```

Run the Streamlit prototype:

```bash
streamlit run ui/streamlit_app.py
```

## MVP Scope

The first useful version should include:

- Add selected agency URL manually.
- Scrape agency listings.
- Parse core fields: title, URL, price, area, location, property type, description, photos.
- Store listings in PostgreSQL or SQLite for the first prototype.
- Basic filters by price, area, location, and property type.
- Natural-language query converted into filters.
- Basic ranking and explanation.
- Links back to original listings.

## Later Improvements

- Automatic scheduled scraping.
- Price-change alerts.
- Removed-listing detection.
- Similar-listing recommendations.
- Investment scoring.
- Location enrichment with metro, schools, parks, and travel time.
- Duplicate detection across agencies.
- Broker performance analysis.
- Export shortlists to PDF or Excel.
- User preferences saved over time.

## Testing Strategy

Start with tests for the parts most likely to break:

- Listing parser with saved HTML examples.
- Price and area normalization.
- Deduplication.
- Query parsing.
- Ranking logic.

Recommended parser test cases:

- Listing with EUR price.
- Listing with BGN price.
- Listing without area.
- Listing without floor.
- Listing with unclear district.
- Listing removed or unavailable.
- Listing with changed price.

## Success Criteria

The MVP is successful when:

- A user can select an agency and collect its active listings.
- Listings are stored consistently and can be refreshed.
- The assistant can answer practical property-search questions.
- Recommendations include clear reasoning.
- The user can open the original listing and verify the source.

## Non-Goals for the First Version

- Scraping all of imot.bg.
- Fully automated buyer-agent negotiation.
- Legal or financial advice.
- Guaranteed property valuation.
- Replacing human review of listings.

## Product Direction

The long-term product should become a decision-support layer for real estate search. The value is not just scraping listings, but helping the user understand which properties best fit their criteria, why they match, what trade-offs exist, and which offers deserve attention first.
