#!/usr/bin/env python3
"""
Meta Ads Builder - Automate Campaign, Ad Set, and Ad creation from CSV files.
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.adcreative import AdCreative
from facebook_business.adobjects.adimage import AdImage
from facebook_business.adobjects.advideo import AdVideo
from facebook_business.adobjects.campaign import Campaign
from facebook_business.adobjects.adset import AdSet
from facebook_business.adobjects.ad import Ad
from facebook_business.adobjects.targeting import Targeting
from facebook_business.api import FacebookAdsApi


class MetaAdBuilder:
    """Build and deploy Meta Ads campaigns from CSV configuration files."""

    def __init__(self, config_path: str = "config.json"):
        """Initialize the Meta Ads API connection."""
        self.config = self._load_config(config_path)
        self.api = FacebookAdsApi.init(
            app_id=self.config.get("app_id"),
            app_secret=self.config.get("app_secret"),
            access_token=self.config["access_token"],
            api_version=self.config.get("api_version", "v21.0"),
        )
        self.ad_account = AdAccount(self.config["ad_account_id"])
        self.creative_path = Path("creative")
        self._uploaded_images = {}
        self._uploaded_videos = {}
        self._created_campaigns = {}
        self._created_adsets = {}

    def _load_config(self, config_path: str) -> dict:
        """Load configuration from JSON file."""
        with open(config_path, "r") as f:
            return json.load(f)

    def _parse_bool(self, value) -> bool:
        """Parse a boolean value from CSV."""
        if pd.isna(value):
            return False
        if isinstance(value, bool):
            return value
        return str(value).lower() in ("true", "1", "yes")

    def _parse_list(self, value) -> list:
        """Parse a comma-separated list from CSV."""
        if pd.isna(value) or value == "":
            return []
        return [item.strip() for item in str(value).split(",")]

    def _upload_image(self, filename: str) -> str:
        """Upload an image and return its hash."""
        if filename in self._uploaded_images:
            return self._uploaded_images[filename]

        image_path = self.creative_path / filename
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        image = AdImage(parent_id=self.config["ad_account_id"])
        image[AdImage.Field.filename] = str(image_path)
        image.remote_create()

        image_hash = image[AdImage.Field.hash]
        self._uploaded_images[filename] = image_hash
        print(f"  ✓ Uploaded image: {filename} (hash: {image_hash})")
        return image_hash

    def _upload_video(self, filename: str) -> str:
        """Upload a video and return its ID."""
        if filename in self._uploaded_videos:
            return self._uploaded_videos[filename]

        video_path = self.creative_path / filename
        if not video_path.exists():
            raise FileNotFoundError(f"Video not found: {video_path}")

        video = AdVideo(parent_id=self.config["ad_account_id"])
        video[AdVideo.Field.filepath] = str(video_path)
        video.remote_create()

        video_id = video.get_id()
        self._uploaded_videos[filename] = video_id
        print(f"  ✓ Uploaded video: {filename} (id: {video_id})")
        return video_id

    def create_campaign(self, row: pd.Series) -> Campaign:
        """Create a campaign from a CSV row."""
        params = {
            Campaign.Field.name: row["name"],
            Campaign.Field.objective: row["objective"],
            Campaign.Field.status: row["status"],
            Campaign.Field.special_ad_categories: self._parse_list(
                row.get("special_ad_categories", "")
            ) or ["NONE"],
        }

        # Budget settings
        if pd.notna(row.get("daily_budget_cents")):
            params[Campaign.Field.daily_budget] = int(row["daily_budget_cents"])
        if pd.notna(row.get("lifetime_budget_cents")):
            params[Campaign.Field.lifetime_budget] = int(row["lifetime_budget_cents"])
        if pd.notna(row.get("bid_strategy")):
            params[Campaign.Field.bid_strategy] = row["bid_strategy"]
        if pd.notna(row.get("buying_type")):
            params[Campaign.Field.buying_type] = row["buying_type"]

        campaign = self.ad_account.create_campaign(params=params)
        print(f"  ✓ Created campaign: {row['name']} (id: {campaign.get_id()})")
        return campaign

    def create_adset(self, row: pd.Series, campaign_id: str) -> AdSet:
        """Create an ad set from a CSV row."""
        # Build targeting spec
        targeting = {
            Targeting.Field.age_min: int(row["targeting_age_min"]),
            Targeting.Field.age_max: int(row["targeting_age_max"]),
            Targeting.Field.geo_locations: {
                "countries": self._parse_list(row["targeting_geo_locations_countries"])
            },
        }

        # Gender targeting
        genders = row.get("targeting_genders", "all")
        if genders != "all":
            targeting[Targeting.Field.genders] = [1] if genders == "male" else [2]

        # Interest targeting
        interests = self._parse_list(row.get("targeting_interests", ""))
        if interests:
            targeting[Targeting.Field.interests] = [
                {"id": i} for i in interests
            ]

        # Custom audiences
        custom_audiences = self._parse_list(row.get("targeting_custom_audiences", ""))
        if custom_audiences:
            targeting[Targeting.Field.custom_audiences] = [
                {"id": a} for a in custom_audiences
            ]

        excluded_audiences = self._parse_list(
            row.get("targeting_excluded_custom_audiences", "")
        )
        if excluded_audiences:
            targeting[Targeting.Field.excluded_custom_audiences] = [
                {"id": a} for a in excluded_audiences
            ]

        params = {
            AdSet.Field.name: row["name"],
            AdSet.Field.campaign_id: campaign_id,
            AdSet.Field.status: row["status"],
            AdSet.Field.billing_event: row["billing_event"],
            AdSet.Field.optimization_goal: row["optimization_goal"],
            AdSet.Field.targeting: targeting,
            AdSet.Field.start_time: row["start_time"],
        }

        # Optional fields
        if pd.notna(row.get("end_time")):
            params[AdSet.Field.end_time] = row["end_time"]
        if pd.notna(row.get("daily_budget_cents")):
            params[AdSet.Field.daily_budget] = int(row["daily_budget_cents"])
        if pd.notna(row.get("lifetime_budget_cents")):
            params[AdSet.Field.lifetime_budget] = int(row["lifetime_budget_cents"])
        if pd.notna(row.get("bid_amount_cents")):
            params[AdSet.Field.bid_amount] = int(row["bid_amount_cents"])

        # Placement targeting
        publisher_platforms = []
        facebook_positions = []
        instagram_positions = []

        if self._parse_bool(row.get("placements_facebook_feeds")):
            publisher_platforms.append("facebook")
            facebook_positions.append("feed")
        if self._parse_bool(row.get("placements_instagram_feed")):
            if "instagram" not in publisher_platforms:
                publisher_platforms.append("instagram")
            instagram_positions.append("stream")
        if self._parse_bool(row.get("placements_instagram_stories")):
            if "instagram" not in publisher_platforms:
                publisher_platforms.append("instagram")
            instagram_positions.append("story")
        if self._parse_bool(row.get("placements_audience_network")):
            publisher_platforms.append("audience_network")

        if publisher_platforms:
            targeting["publisher_platforms"] = publisher_platforms
            if facebook_positions:
                targeting["facebook_positions"] = facebook_positions
            if instagram_positions:
                targeting["instagram_positions"] = instagram_positions
            params[AdSet.Field.targeting] = targeting

        adset = self.ad_account.create_ad_set(params=params)
        print(f"  ✓ Created ad set: {row['name']} (id: {adset.get_id()})")
        return adset

    def create_ad(self, row: pd.Series, adset_id: str) -> Ad:
        """Create an ad from a CSV row."""
        # Build creative
        creative_params = {
            AdCreative.Field.name: f"{row['name']} Creative",
            AdCreative.Field.object_story_spec: {
                "page_id": self.config.get("page_id"),
                "link_data": {
                    "link": row["destination_url"],
                    "message": row["primary_text"],
                    "name": row["headline"],
                    "call_to_action": {
                        "type": row["call_to_action"],
                        "value": {"link": row["destination_url"]},
                    },
                },
            },
        }

        # Add description if provided
        if pd.notna(row.get("description")):
            creative_params[AdCreative.Field.object_story_spec]["link_data"][
                "description"
            ] = row["description"]

        # Handle image or video creative
        if pd.notna(row.get("creative_image_filename")):
            image_hash = self._upload_image(row["creative_image_filename"])
            creative_params[AdCreative.Field.object_story_spec]["link_data"][
                "image_hash"
            ] = image_hash
        elif pd.notna(row.get("creative_video_filename")):
            video_id = self._upload_video(row["creative_video_filename"])
            creative_params[AdCreative.Field.object_story_spec]["video_data"] = {
                "video_id": video_id,
                "message": row["primary_text"],
                "title": row["headline"],
                "call_to_action": {
                    "type": row["call_to_action"],
                    "value": {"link": row["destination_url"]},
                },
            }
            # Remove link_data when using video
            del creative_params[AdCreative.Field.object_story_spec]["link_data"]

        creative = self.ad_account.create_ad_creative(params=creative_params)
        print(f"  ✓ Created creative: {row['name']} Creative (id: {creative.get_id()})")

        # Create ad
        ad_params = {
            Ad.Field.name: row["name"],
            Ad.Field.adset_id: adset_id,
            Ad.Field.creative: {"creative_id": creative.get_id()},
            Ad.Field.status: row["status"],
        }

        ad = self.ad_account.create_ad(params=ad_params)
        print(f"  ✓ Created ad: {row['name']} (id: {ad.get_id()})")
        return ad

    def build_campaign_folder(
        self, campaign_folder: str, dry_run: bool = False
    ) -> dict:
        """Build all objects from a campaign folder."""
        folder_path = Path(campaign_folder)
        results = {"campaigns": [], "adsets": [], "ads": []}

        print(f"\n{'[DRY RUN] ' if dry_run else ''}Building campaign from: {folder_path}")

        # Read CSV files
        campaign_df = pd.read_csv(folder_path / "campaign.csv")
        adsets_df = pd.read_csv(folder_path / "adsets.csv")
        ads_df = pd.read_csv(folder_path / "ads.csv")

        if dry_run:
            print(f"\n  Campaign: {campaign_df.iloc[0]['name']}")
            print(f"  Ad Sets: {len(adsets_df)}")
            print(f"  Ads: {len(ads_df)}")
            return results

        # Create campaign
        campaign_row = campaign_df.iloc[0]
        campaign = self.create_campaign(campaign_row)
        campaign_id = campaign.get_id()
        results["campaigns"].append(campaign_id)
        self._created_campaigns[campaign_row["name"]] = campaign_id

        # Create ad sets
        adset_map = {}
        for _, adset_row in adsets_df.iterrows():
            adset = self.create_adset(adset_row, campaign_id)
            adset_id = adset.get_id()
            adset_map[adset_row["name"]] = adset_id
            results["adsets"].append(adset_id)
            self._created_adsets[adset_row["name"]] = adset_id

        # Create ads
        for _, ad_row in ads_df.iterrows():
            adset_name = ad_row["adset_name"]
            if adset_name not in adset_map:
                print(f"  ✗ Error: Ad set '{adset_name}' not found for ad '{ad_row['name']}'")
                continue
            ad = self.create_ad(ad_row, adset_map[adset_name])
            results["ads"].append(ad.get_id())

        print(f"\n✓ Campaign build complete!")
        print(f"  Campaigns: {len(results['campaigns'])}")
        print(f"  Ad Sets: {len(results['adsets'])}")
        print(f"  Ads: {len(results['ads'])}")

        return results


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Build Meta Ads campaigns from CSV files"
    )
    parser.add_argument(
        "campaign_folder",
        help="Path to the campaign folder containing CSV files",
    )
    parser.add_argument(
        "--config",
        default="config.json",
        help="Path to config file (default: config.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate without creating campaigns",
    )

    args = parser.parse_args()

    try:
        builder = MetaAdBuilder(config_path=args.config)
        builder.build_campaign_folder(args.campaign_folder, dry_run=args.dry_run)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
