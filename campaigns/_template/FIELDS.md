# Meta Ads CSV Field Reference

## campaign.csv

| Field | Required | Description | Valid Values |
|-------|----------|-------------|--------------|
| name | Yes | Campaign name | Any string |
| objective | Yes | Campaign objective | OUTCOME_AWARENESS, OUTCOME_ENGAGEMENT, OUTCOME_LEADS, OUTCOME_SALES, OUTCOME_TRAFFIC, OUTCOME_APP_PROMOTION |
| status | Yes | Campaign status | ACTIVE, PAUSED |
| special_ad_categories | No | Special ad category | NONE, EMPLOYMENT, HOUSING, CREDIT, ISSUES_ELECTIONS_POLITICS (comma-separated) |
| daily_budget_cents | No* | Daily budget in cents | Integer (min 100 = $1.00) |
| lifetime_budget_cents | No* | Lifetime budget in cents | Integer |
| bid_strategy | No | Bidding strategy | LOWEST_COST_WITHOUT_CAP, LOWEST_COST_WITH_BID_CAP, COST_CAP |
| buying_type | No | Buying type | AUCTION, RESERVED |

*Either daily_budget_cents or lifetime_budget_cents is required at campaign or ad set level

---

## adsets.csv

| Field | Required | Description | Valid Values |
|-------|----------|-------------|--------------|
| name | Yes | Ad set name | Any string |
| status | Yes | Ad set status | ACTIVE, PAUSED |
| daily_budget_cents | No* | Daily budget in cents | Integer |
| lifetime_budget_cents | No* | Lifetime budget in cents | Integer |
| bid_amount_cents | No | Bid cap in cents | Integer |
| billing_event | Yes | When you're charged | IMPRESSIONS, LINK_CLICKS, APP_INSTALLS, PAGE_LIKES, POST_ENGAGEMENT |
| optimization_goal | Yes | What to optimize for | REACH, IMPRESSIONS, LINK_CLICKS, LANDING_PAGE_VIEWS, OFFSITE_CONVERSIONS, LEAD_GENERATION, APP_INSTALLS |
| start_time | Yes | Start date/time | ISO 8601 format (YYYY-MM-DDTHH:MM:SS) |
| end_time | No | End date/time | ISO 8601 format |
| targeting_age_min | Yes | Minimum age | 18-65 |
| targeting_age_max | Yes | Maximum age | 18-65 |
| targeting_genders | Yes | Gender targeting | all, male, female |
| targeting_geo_locations_countries | Yes | Target countries | Comma-separated country codes (US, CA, GB, etc.) |
| targeting_interests | No | Interest targeting | Comma-separated interest IDs |
| targeting_custom_audiences | No | Custom audience IDs | Comma-separated audience IDs |
| targeting_excluded_custom_audiences | No | Excluded audience IDs | Comma-separated audience IDs |
| placements_facebook_feeds | No | Facebook Feed placement | true, false |
| placements_instagram_feed | No | Instagram Feed placement | true, false |
| placements_instagram_stories | No | Instagram Stories placement | true, false |
| placements_audience_network | No | Audience Network placement | true, false |

---

## ads.csv

| Field | Required | Description | Valid Values |
|-------|----------|-------------|--------------|
| name | Yes | Ad name | Any string |
| adset_name | Yes | Name of ad set this ad belongs to | Must match a name in adsets.csv |
| status | Yes | Ad status | ACTIVE, PAUSED |
| creative_image_filename | No* | Image filename | Filename in creative/ folder |
| creative_video_filename | No* | Video filename | Filename in creative/ folder |
| headline | Yes | Ad headline | Max 40 characters recommended |
| primary_text | Yes | Main ad text | Max 125 characters recommended |
| description | No | Link description | Max 30 characters recommended |
| call_to_action | Yes | CTA button | SHOP_NOW, LEARN_MORE, SIGN_UP, SUBSCRIBE, CONTACT_US, DOWNLOAD, GET_OFFER, BOOK_NOW, APPLY_NOW, GET_QUOTE |
| destination_url | Yes | Landing page URL | Valid URL |
| display_url | No | Display URL | Shortened display URL |

*Either creative_image_filename or creative_video_filename is required

---

## Notes

1. **Budgets**: All budget values are in cents (e.g., 10000 = $100.00)
2. **Dates**: Use ISO 8601 format with timezone or UTC
3. **Creative files**: Place all images and videos in the `creative/` folder in the repository root
4. **Campaign folders**: Copy the `_template` folder and rename it for each campaign
