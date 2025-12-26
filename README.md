# Meta Ad Builder

A lightweight Python application to automate Campaign, Ad Set, and Ad creation in Meta Ads using CSV configuration files.

## Project Structure

```
MetaAdBuilder/
├── creative/                    # Store your ad images and videos here
├── campaigns/
│   ├── _template/               # Template folder - copy for new campaigns
│   │   ├── campaign.csv         # Campaign configuration
│   │   ├── adsets.csv           # Ad set configurations
│   │   ├── ads.csv              # Ad configurations
│   │   └── FIELDS.md            # Field reference documentation
│   └── my_campaign/             # Your campaign folders go here
│       ├── campaign.csv
│       ├── adsets.csv
│       └── ads.csv
├── src/
│   └── meta_ad_builder.py       # Main automation script
├── config.example.json          # Example configuration file
├── config.json                  # Your configuration (git-ignored)
└── requirements.txt             # Python dependencies
```

## Prerequisites

1. **Python 3.8+**
2. **Meta Business Account** with an Ad Account
3. **Meta Developer App** with Marketing API access

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Create Your Config File

Copy the example config and fill in your credentials:

```bash
cp config.example.json config.json
```

Edit `config.json`:

```json
{
  "access_token": "YOUR_ACCESS_TOKEN",
  "ad_account_id": "act_XXXXXXXXXX",
  "app_id": "YOUR_APP_ID",
  "app_secret": "YOUR_APP_SECRET",
  "page_id": "YOUR_PAGE_ID",
  "api_version": "v21.0"
}
```

### 3. Get Your Access Token

1. Go to [Meta Business Suite](https://business.facebook.com/)
2. Navigate to Settings → Users → System Users
3. Create a System User with `ads_management` and `ads_read` permissions
4. Generate an access token

Or for development, use the [Graph API Explorer](https://developers.facebook.com/tools/explorer/):
- Select your app
- Add permissions: `ads_management`, `ads_read`
- Generate token

## Usage

### 1. Create a New Campaign

Copy the template folder:

```bash
cp -r campaigns/_template campaigns/my_summer_sale
```

### 2. Edit the CSV Files

Edit the CSV files in your campaign folder:

- **campaign.csv** - Define your campaign settings
- **adsets.csv** - Define your ad sets (targeting, budget, schedule)
- **ads.csv** - Define your ads (creative, copy, CTA)

See `campaigns/_template/FIELDS.md` for field documentation.

### 3. Add Your Creative

Place your images and videos in the `creative/` folder, then reference them in `ads.csv`.

### 4. Validate (Dry Run)

```bash
python src/meta_ad_builder.py campaigns/my_summer_sale --dry-run
```

### 5. Build the Campaign

```bash
python src/meta_ad_builder.py campaigns/my_summer_sale
```

## CSV Field Reference

See [campaigns/_template/FIELDS.md](campaigns/_template/FIELDS.md) for complete field documentation.

### Quick Reference

**Campaign Objectives:**
- `OUTCOME_AWARENESS` - Brand awareness
- `OUTCOME_TRAFFIC` - Website traffic
- `OUTCOME_ENGAGEMENT` - Post engagement
- `OUTCOME_LEADS` - Lead generation
- `OUTCOME_SALES` - Conversions/Sales
- `OUTCOME_APP_PROMOTION` - App installs

**Call to Action Types:**
- `SHOP_NOW`, `LEARN_MORE`, `SIGN_UP`, `SUBSCRIBE`
- `CONTACT_US`, `DOWNLOAD`, `GET_OFFER`, `BOOK_NOW`
- `APPLY_NOW`, `GET_QUOTE`

## Example

Create a traffic campaign:

**campaign.csv:**
```csv
name,objective,status,daily_budget_cents
Summer Sale 2024,OUTCOME_TRAFFIC,PAUSED,5000
```

**adsets.csv:**
```csv
name,status,billing_event,optimization_goal,start_time,targeting_age_min,targeting_age_max,targeting_genders,targeting_geo_locations_countries
US Adults,PAUSED,IMPRESSIONS,LINK_CLICKS,2024-06-01T00:00:00,18,65,all,US
```

**ads.csv:**
```csv
name,adset_name,status,creative_image_filename,headline,primary_text,call_to_action,destination_url
Summer Ad 1,US Adults,PAUSED,summer_banner.jpg,50% Off Everything,Don't miss our biggest sale of the year!,SHOP_NOW,https://example.com/sale
```

## Troubleshooting

### "Invalid OAuth access token"
- Your access token has expired. Generate a new one.

### "Ad Account ID is invalid"
- Ensure your `ad_account_id` starts with `act_`

### "User does not have permission"
- Your access token needs `ads_management` permission

## License

MIT
