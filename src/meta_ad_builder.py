#!/usr/bin/env python3
"""
Meta Ads Builder - Automate Campaign, Ad Set, and Ad creation from CSV files.

This script reads CSV configuration files and creates corresponding objects
in Meta Ads Manager using the Marketing API. It supports:
- Creating new campaigns, ad sets, and ads
- Updating existing campaigns by ID
- Resuming failed builds
- Validating data before API calls
- Processing multiple campaigns at once

Author: Auto-generated for MetaAdBuilder project
"""

# =============================================================================
# IMPORTS
# =============================================================================

import json          # For reading/writing JSON config and state files
import os            # For file path operations
import sys           # For system exit codes
from pathlib import Path  # Modern path handling (cross-platform)
from typing import Optional, Dict, List, Any  # Type hints for better code clarity
from datetime import datetime  # For date validation and timestamps

import pandas as pd  # Data manipulation library - reads CSV files into DataFrames

# Facebook/Meta Ads SDK imports
# These are the official Meta classes for interacting with the Marketing API
from facebook_business.adobjects.adaccount import AdAccount      # Your ad account
from facebook_business.adobjects.adcreative import AdCreative    # Ad creative (image/video + text)
from facebook_business.adobjects.adimage import AdImage          # Image uploads
from facebook_business.adobjects.advideo import AdVideo          # Video uploads
from facebook_business.adobjects.campaign import Campaign        # Campaign object
from facebook_business.adobjects.adset import AdSet              # Ad Set object
from facebook_business.adobjects.ad import Ad                    # Ad object
from facebook_business.adobjects.targeting import Targeting      # Targeting spec fields
from facebook_business.api import FacebookAdsApi                 # Main API connection
from facebook_business.exceptions import FacebookRequestError    # API error handling


# =============================================================================
# CUSTOM EXCEPTIONS
# =============================================================================

class MetaAdBuilderError(Exception):
    """Base exception for all Meta Ad Builder errors."""
    pass


class ValidationError(MetaAdBuilderError):
    """Raised when CSV data fails validation before API calls."""
    pass


class TokenExpiredError(MetaAdBuilderError):
    """Raised when the access token has expired."""
    pass


class PaymentRequiredError(MetaAdBuilderError):
    """Raised when the ad account has no payment method."""
    pass


class PermissionError(MetaAdBuilderError):
    """Raised when the app lacks required permissions."""
    pass


# =============================================================================
# MAIN CLASS
# =============================================================================

class MetaAdBuilder:
    """
    Build and deploy Meta Ads campaigns from CSV configuration files.

    This class handles:
    1. Loading configuration (API credentials)
    2. Validating CSV data before making API calls
    3. Creating campaigns, ad sets, and ads
    4. Updating existing objects
    5. Tracking state for resume capability
    6. Generating status reports

    Attributes:
        config (dict): API credentials and settings from config.json
        api (FacebookAdsApi): Initialized API connection
        ad_account (AdAccount): The ad account to create ads in
        creative_path (Path): Directory containing creative files (images/videos)
        state (dict): Tracks created objects for resume capability
        report (dict): Collects results for status reporting
    """

    def __init__(self, config_path: str = "config.json"):
        """
        Initialize the Meta Ads API connection.

        Args:
            config_path: Path to the JSON file containing API credentials.
                        Required fields: access_token, ad_account_id
                        Optional fields: app_id, app_secret, page_id, api_version

        The config.json file should look like:
        {
            "access_token": "EAAxxxx...",
            "ad_account_id": "act_123456789",
            "app_id": "123456789",
            "app_secret": "abc123...",
            "page_id": "987654321",
            "api_version": "v21.0"
        }
        """
        # Load configuration from JSON file
        self.config = self._load_config(config_path)

        # Initialize the Facebook Ads API with our credentials
        # This sets up the global API instance that all SDK calls will use
        self.api = FacebookAdsApi.init(
            app_id=self.config.get("app_id"),
            app_secret=self.config.get("app_secret"),
            access_token=self.config["access_token"],
            api_version=self.config.get("api_version", "v21.0"),
        )

        # Create an AdAccount object - this represents your Meta ad account
        # All campaigns, ad sets, and ads are created under this account
        self.ad_account = AdAccount(self.config["ad_account_id"])

        # Path to the directory containing images and videos for ads
        self.creative_path = Path("creative")

        # Cache for uploaded media to avoid re-uploading the same files
        self._uploaded_images: Dict[str, str] = {}  # filename -> image_hash
        self._uploaded_videos: Dict[str, str] = {}  # filename -> video_id

        # State tracking for resume capability
        # This maps names to IDs for objects we've created
        self.state: Dict[str, Any] = {
            "campaigns": {},    # campaign_name -> campaign_id
            "adsets": {},       # adset_name -> adset_id
            "ads": {},          # ad_name -> ad_id
            "creatives": {},    # creative_name -> creative_id
        }

        # Report data for status output
        self.report: Dict[str, Any] = {
            "started_at": datetime.now().isoformat(),
            "completed_at": None,
            "success": False,
            "campaigns_created": [],
            "campaigns_updated": [],
            "adsets_created": [],
            "ads_created": [],
            "errors": [],
        }

    # =========================================================================
    # CONFIGURATION & UTILITY METHODS
    # =========================================================================

    def _load_config(self, config_path: str) -> dict:
        """
        Load configuration from a JSON file.

        Args:
            config_path: Path to the config JSON file

        Returns:
            Dictionary containing configuration values

        Raises:
            FileNotFoundError: If config file doesn't exist
            json.JSONDecodeError: If config file is not valid JSON
        """
        with open(config_path, "r") as f:
            return json.load(f)

    def _parse_bool(self, value) -> bool:
        """
        Parse a boolean value from CSV data.

        CSV files store everything as strings, so we need to convert
        string representations of booleans to actual Python bools.

        Args:
            value: The value to parse (could be string, bool, or NaN)

        Returns:
            True if value represents a truthy value, False otherwise

        Examples:
            _parse_bool("true")  -> True
            _parse_bool("false") -> False
            _parse_bool("1")     -> True
            _parse_bool("")      -> False
            _parse_bool(NaN)     -> False
        """
        # Handle pandas NaN (missing values in CSV)
        if pd.isna(value):
            return False
        # If it's already a boolean, return as-is
        if isinstance(value, bool):
            return value
        # Convert string to lowercase and check against truthy values
        return str(value).lower() in ("true", "1", "yes")

    def _parse_list(self, value) -> list:
        """
        Parse a comma-separated string into a Python list.

        Many CSV fields contain comma-separated values (like country codes).
        This method splits them into a proper list.

        Args:
            value: Comma-separated string or empty/NaN value

        Returns:
            List of stripped string values, or empty list if input is empty

        Examples:
            _parse_list("US,CA,GB") -> ["US", "CA", "GB"]
            _parse_list("US")       -> ["US"]
            _parse_list("")         -> []
            _parse_list(NaN)        -> []
        """
        if pd.isna(value) or value == "":
            return []
        # Split by comma and strip whitespace from each item
        return [item.strip() for item in str(value).split(",")]

    def _handle_api_error(self, error: FacebookRequestError, context: str) -> None:
        """
        Handle Facebook API errors and convert to friendly messages.

        The Meta API returns specific error codes. This method interprets
        those codes and raises appropriate custom exceptions with helpful messages.

        Args:
            error: The FacebookRequestError from the API
            context: Description of what operation was being attempted

        Raises:
            TokenExpiredError: If access token has expired
            PaymentRequiredError: If no payment method on account
            PermissionError: If app lacks permissions
            MetaAdBuilderError: For other API errors
        """
        error_code = error.api_error_code()
        error_subcode = error.api_error_subcode()
        error_message = error.api_error_message()

        # Error code 190 = Invalid/expired access token
        if error_code == 190:
            raise TokenExpiredError(
                f"Access token has expired. Please generate a new token at:\n"
                f"https://developers.facebook.com/tools/explorer/\n"
                f"Then update your config.json file."
            )

        # Error subcode 1359188 = No payment method
        if error_subcode == 1359188:
            raise PaymentRequiredError(
                f"No payment method on ad account. Please add one at:\n"
                f"https://www.facebook.com/ads/manager/billing/"
            )

        # Error subcode 1870227 = Advantage Audience flag required
        if error_subcode == 1870227:
            raise MetaAdBuilderError(
                f"Advantage Audience flag is required. Make sure your adsets.csv "
                f"has the 'advantage_audience' column set to 'true' or 'false'."
            )

        # Error subcode 1885183 = App in development mode
        if error_subcode == 1885183:
            raise PermissionError(
                f"Your Meta app is in Development Mode. To create ads:\n"
                f"1. Go to https://developers.facebook.com/apps/\n"
                f"2. Select your app\n"
                f"3. Switch 'App Mode' from 'Development' to 'Live'"
            )

        # Error code 100 = Invalid parameter (generic)
        if error_code == 100:
            raise MetaAdBuilderError(
                f"Invalid parameter in {context}:\n{error_message}"
            )

        # Error code 10 = Permission denied
        if error_code == 10:
            raise PermissionError(
                f"Permission denied. Make sure your access token has:\n"
                f"- ads_management\n"
                f"- ads_read\n"
                f"permissions granted."
            )

        # Generic error - include all details
        raise MetaAdBuilderError(
            f"API Error during {context}:\n"
            f"Code: {error_code}, Subcode: {error_subcode}\n"
            f"Message: {error_message}"
        )

    # =========================================================================
    # VALIDATION METHODS
    # =========================================================================

    def validate_campaign_data(self, df: pd.DataFrame) -> List[str]:
        """
        Validate campaign CSV data before making API calls.

        Checks for:
        - Required fields are present and not empty
        - Objective is a valid Meta objective
        - Status is valid (ACTIVE or PAUSED)
        - Budget values are positive integers

        Args:
            df: DataFrame containing campaign data

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        required_fields = ["name", "objective", "status"]

        # Check required fields exist
        for field in required_fields:
            if field not in df.columns:
                errors.append(f"Campaign CSV missing required column: {field}")

        if errors:
            return errors

        # Validate each row
        for idx, row in df.iterrows():
            # Check required fields have values
            for field in required_fields:
                if pd.isna(row.get(field)) or str(row.get(field)).strip() == "":
                    errors.append(f"Campaign row {idx + 1}: '{field}' is required")

            # Validate objective
            valid_objectives = [
                "OUTCOME_AWARENESS", "OUTCOME_ENGAGEMENT", "OUTCOME_LEADS",
                "OUTCOME_SALES", "OUTCOME_TRAFFIC", "OUTCOME_APP_PROMOTION"
            ]
            if row.get("objective") not in valid_objectives:
                errors.append(
                    f"Campaign row {idx + 1}: Invalid objective '{row.get('objective')}'. "
                    f"Must be one of: {', '.join(valid_objectives)}"
                )

            # Validate status
            if row.get("status") not in ["ACTIVE", "PAUSED"]:
                errors.append(
                    f"Campaign row {idx + 1}: Invalid status '{row.get('status')}'. "
                    f"Must be ACTIVE or PAUSED"
                )

            # Validate budget if provided
            if pd.notna(row.get("daily_budget_cents")):
                try:
                    budget = int(row["daily_budget_cents"])
                    if budget < 100:
                        errors.append(
                            f"Campaign row {idx + 1}: daily_budget_cents must be at least 100 ($1.00)"
                        )
                except ValueError:
                    errors.append(
                        f"Campaign row {idx + 1}: daily_budget_cents must be an integer"
                    )

        return errors

    def validate_adset_data(self, df: pd.DataFrame) -> List[str]:
        """
        Validate ad set CSV data before making API calls.

        Checks for:
        - Required fields are present
        - Age values are valid (18-65)
        - Dates are in ISO 8601 format
        - Country codes are valid

        Args:
            df: DataFrame containing ad set data

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        required_fields = [
            "name", "status", "billing_event", "optimization_goal",
            "start_time", "targeting_age_min", "targeting_age_max",
            "targeting_genders", "targeting_geo_locations_countries"
        ]

        # Check required fields exist
        for field in required_fields:
            if field not in df.columns:
                errors.append(f"Ad Set CSV missing required column: {field}")

        if errors:
            return errors

        # Validate each row
        for idx, row in df.iterrows():
            row_num = idx + 1

            # Check required fields have values
            for field in required_fields:
                if pd.isna(row.get(field)) or str(row.get(field)).strip() == "":
                    errors.append(f"Ad Set row {row_num}: '{field}' is required")

            # Validate age range
            try:
                age_min = int(row.get("targeting_age_min", 0))
                age_max = int(row.get("targeting_age_max", 0))
                if age_min < 18 or age_min > 65:
                    errors.append(f"Ad Set row {row_num}: targeting_age_min must be 18-65")
                if age_max < 18 or age_max > 65:
                    errors.append(f"Ad Set row {row_num}: targeting_age_max must be 18-65")
                if age_min > age_max:
                    errors.append(f"Ad Set row {row_num}: targeting_age_min cannot be greater than targeting_age_max")
            except (ValueError, TypeError):
                errors.append(f"Ad Set row {row_num}: Age values must be integers")

            # Validate start_time format
            try:
                start_time = str(row.get("start_time", ""))
                if start_time:
                    datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            except ValueError:
                errors.append(
                    f"Ad Set row {row_num}: start_time must be ISO 8601 format (e.g., 2024-01-15T00:00:00)"
                )

            # Validate countries are provided
            countries = self._parse_list(row.get("targeting_geo_locations_countries", ""))
            if not countries:
                errors.append(f"Ad Set row {row_num}: At least one country code is required")

        return errors

    def validate_ad_data(self, df: pd.DataFrame, adset_names: List[str]) -> List[str]:
        """
        Validate ad CSV data before making API calls.

        Checks for:
        - Required fields are present
        - adset_name references a valid ad set
        - Creative file exists (if specified)
        - URL is valid format

        Args:
            df: DataFrame containing ad data
            adset_names: List of valid ad set names to reference

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        required_fields = [
            "name", "adset_name", "status", "headline",
            "primary_text", "call_to_action", "destination_url"
        ]

        # Check required fields exist
        for field in required_fields:
            if field not in df.columns:
                errors.append(f"Ads CSV missing required column: {field}")

        if errors:
            return errors

        # Validate each row
        for idx, row in df.iterrows():
            row_num = idx + 1

            # Check required fields have values
            for field in required_fields:
                if pd.isna(row.get(field)) or str(row.get(field)).strip() == "":
                    errors.append(f"Ad row {row_num}: '{field}' is required")

            # Validate adset_name references a valid ad set
            adset_name = row.get("adset_name", "")
            if adset_name and adset_name not in adset_names:
                errors.append(
                    f"Ad row {row_num}: adset_name '{adset_name}' not found in adsets.csv"
                )

            # Validate creative file exists (if specified)
            image_file = row.get("creative_image_filename", "")
            video_file = row.get("creative_video_filename", "")

            if pd.notna(image_file) and image_file:
                image_path = self.creative_path / image_file
                if not image_path.exists():
                    errors.append(
                        f"Ad row {row_num}: Image file not found: {image_path}"
                    )

            if pd.notna(video_file) and video_file:
                video_path = self.creative_path / video_file
                if not video_path.exists():
                    errors.append(
                        f"Ad row {row_num}: Video file not found: {video_path}"
                    )

            # Check at least one creative is specified
            if (pd.isna(image_file) or not image_file) and (pd.isna(video_file) or not video_file):
                errors.append(
                    f"Ad row {row_num}: Either creative_image_filename or creative_video_filename is required"
                )

            # Validate URL format (basic check)
            url = row.get("destination_url", "")
            if url and not (url.startswith("http://") or url.startswith("https://")):
                errors.append(
                    f"Ad row {row_num}: destination_url must start with http:// or https://"
                )

            # Validate call_to_action
            valid_ctas = [
                "SHOP_NOW", "LEARN_MORE", "SIGN_UP", "SUBSCRIBE",
                "CONTACT_US", "DOWNLOAD", "GET_OFFER", "BOOK_NOW",
                "APPLY_NOW", "GET_QUOTE", "WATCH_MORE", "SEE_MORE"
            ]
            cta = row.get("call_to_action", "")
            if cta and cta not in valid_ctas:
                errors.append(
                    f"Ad row {row_num}: Invalid call_to_action '{cta}'. "
                    f"Must be one of: {', '.join(valid_ctas)}"
                )

        return errors

    def validate_campaign_folder(self, folder_path: Path) -> List[str]:
        """
        Validate all CSV files in a campaign folder.

        This is the main validation entry point that checks:
        1. All required CSV files exist
        2. Each CSV file passes its specific validation

        Args:
            folder_path: Path to the campaign folder

        Returns:
            List of all validation errors (empty if valid)
        """
        errors = []

        # Check required files exist
        required_files = ["campaign.csv", "adsets.csv", "ads.csv"]
        for filename in required_files:
            if not (folder_path / filename).exists():
                errors.append(f"Missing required file: {folder_path / filename}")

        if errors:
            return errors

        # Load and validate each CSV
        try:
            campaign_df = pd.read_csv(folder_path / "campaign.csv")
            errors.extend(self.validate_campaign_data(campaign_df))
        except Exception as e:
            errors.append(f"Error reading campaign.csv: {e}")

        try:
            adsets_df = pd.read_csv(folder_path / "adsets.csv")
            errors.extend(self.validate_adset_data(adsets_df))
            adset_names = adsets_df["name"].tolist() if "name" in adsets_df.columns else []
        except Exception as e:
            errors.append(f"Error reading adsets.csv: {e}")
            adset_names = []

        try:
            ads_df = pd.read_csv(folder_path / "ads.csv")
            errors.extend(self.validate_ad_data(ads_df, adset_names))
        except Exception as e:
            errors.append(f"Error reading ads.csv: {e}")

        return errors

    # =========================================================================
    # STATE MANAGEMENT (for resume capability)
    # =========================================================================

    def _get_state_file_path(self, campaign_folder: str) -> Path:
        """
        Get the path to the state file for a campaign folder.

        The state file tracks what objects have been created, allowing
        the build to resume if it fails partway through.

        Args:
            campaign_folder: Path to the campaign folder

        Returns:
            Path to the state JSON file
        """
        return Path(campaign_folder) / ".build_state.json"

    def load_state(self, campaign_folder: str) -> Dict[str, Any]:
        """
        Load the build state from a previous run.

        If a build fails partway through, the state file records what
        was already created, allowing us to resume without duplicating.

        Args:
            campaign_folder: Path to the campaign folder

        Returns:
            State dictionary with created object IDs
        """
        state_file = self._get_state_file_path(campaign_folder)
        if state_file.exists():
            with open(state_file, "r") as f:
                return json.load(f)
        return {
            "campaigns": {},
            "adsets": {},
            "ads": {},
            "creatives": {},
        }

    def save_state(self, campaign_folder: str) -> None:
        """
        Save the current build state to a file.

        Called after each successful object creation to enable resume.

        Args:
            campaign_folder: Path to the campaign folder
        """
        state_file = self._get_state_file_path(campaign_folder)
        with open(state_file, "w") as f:
            json.dump(self.state, f, indent=2)

    def clear_state(self, campaign_folder: str) -> None:
        """
        Clear the build state file after successful completion.

        Args:
            campaign_folder: Path to the campaign folder
        """
        state_file = self._get_state_file_path(campaign_folder)
        if state_file.exists():
            state_file.unlink()

    # =========================================================================
    # MEDIA UPLOAD METHODS
    # =========================================================================

    def _upload_image(self, filename: str) -> str:
        """
        Upload an image file to Meta and return its hash.

        Meta stores images by hash, which is then referenced when
        creating ad creatives. This method handles the upload process.

        Args:
            filename: Name of the image file in the creative/ folder

        Returns:
            The image hash string from Meta

        Raises:
            FileNotFoundError: If the image file doesn't exist
        """
        # Check if we've already uploaded this image (avoid duplicates)
        if filename in self._uploaded_images:
            return self._uploaded_images[filename]

        # Build the full path to the image
        image_path = self.creative_path / filename
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        # Create an AdImage object and upload it
        # parent_id must be the ad account ID
        image = AdImage(parent_id=self.config["ad_account_id"])
        image[AdImage.Field.filename] = str(image_path)
        image.remote_create()  # This uploads the image to Meta

        # Get the hash that Meta assigned to this image
        image_hash = image[AdImage.Field.hash]

        # Cache it to avoid re-uploading
        self._uploaded_images[filename] = image_hash
        print(f"    ✓ Uploaded image: {filename} (hash: {image_hash[:16]}...)")

        return image_hash

    def _upload_video(self, filename: str) -> str:
        """
        Upload a video file to Meta and return its ID.

        Unlike images (which use hashes), videos are referenced by ID.
        Video uploads may take longer depending on file size.

        Args:
            filename: Name of the video file in the creative/ folder

        Returns:
            The video ID string from Meta

        Raises:
            FileNotFoundError: If the video file doesn't exist
        """
        # Check if we've already uploaded this video
        if filename in self._uploaded_videos:
            return self._uploaded_videos[filename]

        # Build the full path to the video
        video_path = self.creative_path / filename
        if not video_path.exists():
            raise FileNotFoundError(f"Video not found: {video_path}")

        # Create an AdVideo object and upload it
        video = AdVideo(parent_id=self.config["ad_account_id"])
        video[AdVideo.Field.filepath] = str(video_path)
        video.remote_create()  # This uploads the video to Meta

        # Get the ID that Meta assigned to this video
        video_id = video.get_id()

        # Cache it to avoid re-uploading
        self._uploaded_videos[filename] = video_id
        print(f"    ✓ Uploaded video: {filename} (id: {video_id})")

        return video_id

    # =========================================================================
    # CAMPAIGN CREATION & UPDATE METHODS
    # =========================================================================

    def create_campaign(self, row: pd.Series) -> Campaign:
        """
        Create a new campaign from a CSV row.

        A Campaign is the top-level container in Meta Ads. It defines:
        - The advertising objective (traffic, conversions, etc.)
        - The overall budget (optional, can be at ad set level)
        - The buying type (usually AUCTION)

        Args:
            row: A pandas Series containing campaign data from CSV

        Returns:
            The created Campaign object
        """
        # Build the parameters dictionary for the API call
        # Campaign.Field.xxx are constants that map to API field names
        params = {
            Campaign.Field.name: row["name"],
            Campaign.Field.objective: row["objective"],
            Campaign.Field.status: row["status"],
            # special_ad_categories is required - use NONE if not specified
            Campaign.Field.special_ad_categories: self._parse_list(
                row.get("special_ad_categories", "")
            ) or ["NONE"],
        }

        # Add optional budget settings
        # Note: Budgets are in cents (e.g., 5000 = $50.00)
        if pd.notna(row.get("daily_budget_cents")):
            params[Campaign.Field.daily_budget] = int(row["daily_budget_cents"])
        if pd.notna(row.get("lifetime_budget_cents")):
            params[Campaign.Field.lifetime_budget] = int(row["lifetime_budget_cents"])
        if pd.notna(row.get("bid_strategy")):
            params[Campaign.Field.bid_strategy] = row["bid_strategy"]
        if pd.notna(row.get("buying_type")):
            params[Campaign.Field.buying_type] = row["buying_type"]

        # Make the API call to create the campaign
        try:
            campaign = self.ad_account.create_campaign(params=params)
            print(f"  ✓ Created campaign: {row['name']} (id: {campaign.get_id()})")
            return campaign
        except FacebookRequestError as e:
            self._handle_api_error(e, f"creating campaign '{row['name']}'")

    def update_campaign(self, campaign_id: str, row: pd.Series) -> Campaign:
        """
        Update an existing campaign with new settings.

        Use this when you want to modify a campaign that already exists
        rather than creating a new one.

        Args:
            campaign_id: The ID of the existing campaign to update
            row: A pandas Series containing the new campaign data

        Returns:
            The updated Campaign object
        """
        # Load the existing campaign by ID
        campaign = Campaign(campaign_id)

        # Build update parameters (only include fields that should change)
        params = {
            Campaign.Field.name: row["name"],
            Campaign.Field.status: row["status"],
        }

        # Add optional fields if provided
        if pd.notna(row.get("daily_budget_cents")):
            params[Campaign.Field.daily_budget] = int(row["daily_budget_cents"])
        if pd.notna(row.get("lifetime_budget_cents")):
            params[Campaign.Field.lifetime_budget] = int(row["lifetime_budget_cents"])

        # Make the API call to update
        try:
            campaign.api_update(params=params)
            print(f"  ✓ Updated campaign: {row['name']} (id: {campaign_id})")
            return campaign
        except FacebookRequestError as e:
            self._handle_api_error(e, f"updating campaign '{row['name']}'")

    # =========================================================================
    # AD SET CREATION & UPDATE METHODS
    # =========================================================================

    def create_adset(self, row: pd.Series, campaign_id: str) -> AdSet:
        """
        Create a new ad set from a CSV row.

        An Ad Set defines:
        - The target audience (age, gender, location, interests)
        - The budget and schedule
        - The optimization goal
        - Where ads will be shown (placements)

        Args:
            row: A pandas Series containing ad set data from CSV
            campaign_id: The ID of the parent campaign

        Returns:
            The created AdSet object
        """
        # Parse the Advantage+ Audience flag (required by Meta API)
        # This controls whether Meta can expand your targeting using AI
        # 0 = Use exact targeting, 1 = Allow Meta to expand audience
        advantage_audience_value = 1 if self._parse_bool(row.get("advantage_audience", False)) else 0

        # Build the targeting specification
        # This defines WHO will see your ads
        targeting = {
            # Age range (18-65)
            Targeting.Field.age_min: int(row["targeting_age_min"]),
            Targeting.Field.age_max: int(row["targeting_age_max"]),

            # Geographic targeting - which countries
            Targeting.Field.geo_locations: {
                "countries": self._parse_list(row["targeting_geo_locations_countries"])
            },

            # Advantage+ Audience setting (required)
            "targeting_automation": {
                "advantage_audience": advantage_audience_value
            },
        }

        # Add gender targeting if not "all"
        # Meta uses: 1 = male, 2 = female
        genders = row.get("targeting_genders", "all")
        if genders != "all":
            targeting[Targeting.Field.genders] = [1] if genders == "male" else [2]

        # Add interest targeting if specified
        # Interests require specific IDs from Meta's targeting search API
        interests = self._parse_list(row.get("targeting_interests", ""))
        if interests:
            targeting[Targeting.Field.interests] = [
                {"id": i} for i in interests
            ]

        # Add custom audience targeting if specified
        # Custom audiences are lists you've uploaded (email lists, website visitors, etc.)
        custom_audiences = self._parse_list(row.get("targeting_custom_audiences", ""))
        if custom_audiences:
            targeting[Targeting.Field.custom_audiences] = [
                {"id": a} for a in custom_audiences
            ]

        # Add excluded audiences if specified
        excluded_audiences = self._parse_list(
            row.get("targeting_excluded_custom_audiences", "")
        )
        if excluded_audiences:
            targeting[Targeting.Field.excluded_custom_audiences] = [
                {"id": a} for a in excluded_audiences
            ]

        # Build the ad set parameters
        params = {
            AdSet.Field.name: row["name"],
            AdSet.Field.campaign_id: campaign_id,
            AdSet.Field.status: row["status"],
            # billing_event: When you get charged (IMPRESSIONS = per view)
            AdSet.Field.billing_event: row["billing_event"],
            # optimization_goal: What Meta optimizes for (LINK_CLICKS = clicks)
            AdSet.Field.optimization_goal: row["optimization_goal"],
            AdSet.Field.targeting: targeting,
            AdSet.Field.start_time: row["start_time"],
        }

        # Add optional fields
        if pd.notna(row.get("end_time")):
            params[AdSet.Field.end_time] = row["end_time"]
        if pd.notna(row.get("daily_budget_cents")):
            params[AdSet.Field.daily_budget] = int(row["daily_budget_cents"])
        if pd.notna(row.get("lifetime_budget_cents")):
            params[AdSet.Field.lifetime_budget] = int(row["lifetime_budget_cents"])
        if pd.notna(row.get("bid_amount_cents")):
            params[AdSet.Field.bid_amount] = int(row["bid_amount_cents"])

        # Build placement targeting (WHERE ads appear)
        # If no placements specified, Meta uses automatic placements
        publisher_platforms = []      # Which platforms (facebook, instagram, etc.)
        facebook_positions = []       # Positions on Facebook
        instagram_positions = []      # Positions on Instagram

        # Check each placement option from CSV
        if self._parse_bool(row.get("placements_facebook_feeds")):
            publisher_platforms.append("facebook")
            facebook_positions.append("feed")
        if self._parse_bool(row.get("placements_instagram_feed")):
            if "instagram" not in publisher_platforms:
                publisher_platforms.append("instagram")
            instagram_positions.append("stream")  # "stream" is the API name for feed
        if self._parse_bool(row.get("placements_instagram_stories")):
            if "instagram" not in publisher_platforms:
                publisher_platforms.append("instagram")
            instagram_positions.append("story")
        if self._parse_bool(row.get("placements_audience_network")):
            publisher_platforms.append("audience_network")

        # Only add placement targeting if specific placements were requested
        if publisher_platforms:
            targeting["publisher_platforms"] = publisher_platforms
            if facebook_positions:
                targeting["facebook_positions"] = facebook_positions
            if instagram_positions:
                targeting["instagram_positions"] = instagram_positions
            params[AdSet.Field.targeting] = targeting

        # Make the API call to create the ad set
        try:
            adset = self.ad_account.create_ad_set(params=params)
            print(f"  ✓ Created ad set: {row['name']} (id: {adset.get_id()})")
            return adset
        except FacebookRequestError as e:
            self._handle_api_error(e, f"creating ad set '{row['name']}'")

    def update_adset(self, adset_id: str, row: pd.Series) -> AdSet:
        """
        Update an existing ad set with new settings.

        Args:
            adset_id: The ID of the existing ad set to update
            row: A pandas Series containing the new ad set data

        Returns:
            The updated AdSet object
        """
        adset = AdSet(adset_id)

        # Build update parameters
        params = {
            AdSet.Field.name: row["name"],
            AdSet.Field.status: row["status"],
        }

        # Add optional fields if provided
        if pd.notna(row.get("daily_budget_cents")):
            params[AdSet.Field.daily_budget] = int(row["daily_budget_cents"])
        if pd.notna(row.get("end_time")):
            params[AdSet.Field.end_time] = row["end_time"]

        try:
            adset.api_update(params=params)
            print(f"  ✓ Updated ad set: {row['name']} (id: {adset_id})")
            return adset
        except FacebookRequestError as e:
            self._handle_api_error(e, f"updating ad set '{row['name']}'")

    # =========================================================================
    # AD CREATION METHODS
    # =========================================================================

    def create_ad(self, row: pd.Series, adset_id: str) -> Ad:
        """
        Create a new ad from a CSV row.

        An Ad combines:
        - A Creative (the visual content + text)
        - An Ad Set (the targeting)

        This method first creates the creative, then creates the ad
        that references it.

        Args:
            row: A pandas Series containing ad data from CSV
            adset_id: The ID of the parent ad set

        Returns:
            The created Ad object
        """
        # First, create the ad creative
        # The creative contains the actual ad content (image/video, text, CTA)
        creative_params = {
            AdCreative.Field.name: f"{row['name']} Creative",
            # object_story_spec defines what appears in the ad
            AdCreative.Field.object_story_spec: {
                # page_id: The Facebook Page that the ad comes from
                "page_id": self.config.get("page_id"),
                # link_data: For link/traffic ads
                "link_data": {
                    "link": row["destination_url"],           # Where clicks go
                    "message": row["primary_text"],           # Main ad text
                    "name": row["headline"],                  # Bold headline
                    "call_to_action": {
                        "type": row["call_to_action"],        # CTA button text
                        "value": {"link": row["destination_url"]},
                    },
                },
            },
        }

        # Add description if provided (smaller text below headline)
        if pd.notna(row.get("description")):
            creative_params[AdCreative.Field.object_story_spec]["link_data"][
                "description"
            ] = row["description"]

        # Handle image creative
        if pd.notna(row.get("creative_image_filename")) and row.get("creative_image_filename"):
            # Upload the image and get its hash
            image_hash = self._upload_image(row["creative_image_filename"])
            # Add the image hash to the creative
            creative_params[AdCreative.Field.object_story_spec]["link_data"][
                "image_hash"
            ] = image_hash

        # Handle video creative (mutually exclusive with image)
        elif pd.notna(row.get("creative_video_filename")) and row.get("creative_video_filename"):
            # Upload the video and get its ID
            video_id = self._upload_video(row["creative_video_filename"])
            # Video ads use video_data instead of link_data
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

        # Create the creative via API
        try:
            creative = self.ad_account.create_ad_creative(params=creative_params)
            print(f"    ✓ Created creative: {row['name']} Creative (id: {creative.get_id()})")
        except FacebookRequestError as e:
            self._handle_api_error(e, f"creating creative for ad '{row['name']}'")

        # Now create the ad that uses this creative
        ad_params = {
            Ad.Field.name: row["name"],
            Ad.Field.adset_id: adset_id,
            # Reference the creative we just created
            Ad.Field.creative: {"creative_id": creative.get_id()},
            Ad.Field.status: row["status"],
        }

        try:
            ad = self.ad_account.create_ad(params=ad_params)
            print(f"  ✓ Created ad: {row['name']} (id: {ad.get_id()})")
            return ad
        except FacebookRequestError as e:
            self._handle_api_error(e, f"creating ad '{row['name']}'")

    # =========================================================================
    # MAIN BUILD METHODS
    # =========================================================================

    def build_campaign_folder(
        self,
        campaign_folder: str,
        dry_run: bool = False,
        resume: bool = False,
        update_mode: bool = False
    ) -> dict:
        """
        Build all objects from a campaign folder.

        This is the main entry point for building a campaign. It:
        1. Validates all CSV data
        2. Loads previous state if resuming
        3. Creates/updates the campaign
        4. Creates/updates all ad sets
        5. Creates all ads
        6. Saves state and generates report

        Args:
            campaign_folder: Path to the folder containing CSV files
            dry_run: If True, validate only without creating anything
            resume: If True, skip objects that were already created
            update_mode: If True, update existing objects by ID

        Returns:
            Dictionary containing results and any error messages
        """
        folder_path = Path(campaign_folder)
        results = {"campaigns": [], "adsets": [], "ads": [], "errors": []}

        print(f"\n{'[DRY RUN] ' if dry_run else ''}Building campaign from: {folder_path}")

        # =====================================================================
        # STEP 1: Validate all CSV data before making any API calls
        # =====================================================================
        print("\n📋 Validating CSV data...")
        validation_errors = self.validate_campaign_folder(folder_path)

        if validation_errors:
            print("\n❌ Validation failed:")
            for error in validation_errors:
                print(f"   • {error}")
            results["errors"] = validation_errors
            self.report["errors"] = validation_errors
            return results

        print("   ✓ All CSV data is valid")

        # =====================================================================
        # STEP 2: Read CSV files into DataFrames
        # =====================================================================
        campaign_df = pd.read_csv(folder_path / "campaign.csv")
        adsets_df = pd.read_csv(folder_path / "adsets.csv")
        ads_df = pd.read_csv(folder_path / "ads.csv")

        # If dry run, just show summary and exit
        if dry_run:
            print(f"\n📊 Campaign Summary:")
            print(f"   Campaign: {campaign_df.iloc[0]['name']}")
            print(f"   Ad Sets:  {len(adsets_df)}")
            print(f"   Ads:      {len(ads_df)}")
            print("\n✓ Dry run complete - no changes made")
            return results

        # =====================================================================
        # STEP 3: Load previous state if resuming
        # =====================================================================
        if resume:
            self.state = self.load_state(campaign_folder)
            if self.state["campaigns"]:
                print(f"\n🔄 Resuming from previous state...")
                print(f"   Found: {len(self.state['campaigns'])} campaign(s), "
                      f"{len(self.state['adsets'])} ad set(s), "
                      f"{len(self.state['ads'])} ad(s)")

        # =====================================================================
        # STEP 4: Create or update the campaign
        # =====================================================================
        print("\n🚀 Building campaign...")

        campaign_row = campaign_df.iloc[0]
        campaign_name = campaign_row["name"]

        # Check if we should skip (resume mode) or update (update mode)
        if campaign_name in self.state["campaigns"]:
            campaign_id = self.state["campaigns"][campaign_name]
            if update_mode:
                campaign = self.update_campaign(campaign_id, campaign_row)
                self.report["campaigns_updated"].append(campaign_id)
            else:
                print(f"  ⏭ Skipping campaign: {campaign_name} (already exists)")
                campaign_id = self.state["campaigns"][campaign_name]
        else:
            # Check if campaign_id is provided for update mode
            if update_mode and pd.notna(campaign_row.get("id")):
                campaign_id = campaign_row["id"]
                campaign = self.update_campaign(campaign_id, campaign_row)
                self.report["campaigns_updated"].append(campaign_id)
            else:
                campaign = self.create_campaign(campaign_row)
                campaign_id = campaign.get_id()
                self.report["campaigns_created"].append(campaign_id)

        results["campaigns"].append(campaign_id)
        self.state["campaigns"][campaign_name] = campaign_id
        self.save_state(campaign_folder)

        # =====================================================================
        # STEP 5: Create or update all ad sets
        # =====================================================================
        print("\n📦 Building ad sets...")

        adset_map = {}  # Maps ad set names to IDs for use when creating ads

        for _, adset_row in adsets_df.iterrows():
            adset_name = adset_row["name"]

            try:
                # Check if we should skip or update
                if adset_name in self.state["adsets"]:
                    adset_id = self.state["adsets"][adset_name]
                    if update_mode:
                        adset = self.update_adset(adset_id, adset_row)
                    else:
                        print(f"  ⏭ Skipping ad set: {adset_name} (already exists)")
                else:
                    if update_mode and pd.notna(adset_row.get("id")):
                        adset_id = adset_row["id"]
                        adset = self.update_adset(adset_id, adset_row)
                    else:
                        adset = self.create_adset(adset_row, campaign_id)
                        adset_id = adset.get_id()
                        self.report["adsets_created"].append(adset_id)

                adset_map[adset_name] = adset_id
                results["adsets"].append(adset_id)
                self.state["adsets"][adset_name] = adset_id
                self.save_state(campaign_folder)

            except MetaAdBuilderError as e:
                error_msg = f"Ad set '{adset_name}': {str(e)}"
                print(f"  ❌ {error_msg}")
                results["errors"].append(error_msg)
                self.report["errors"].append(error_msg)

        # =====================================================================
        # STEP 6: Create all ads
        # =====================================================================
        print("\n🎨 Building ads...")

        for _, ad_row in ads_df.iterrows():
            ad_name = ad_row["name"]
            adset_name = ad_row["adset_name"]

            # Skip if ad already created (resume mode)
            if ad_name in self.state["ads"] and not update_mode:
                print(f"  ⏭ Skipping ad: {ad_name} (already exists)")
                results["ads"].append(self.state["ads"][ad_name])
                continue

            # Check that the referenced ad set exists
            if adset_name not in adset_map:
                error_msg = f"Ad '{ad_name}': Ad set '{adset_name}' not found"
                print(f"  ❌ {error_msg}")
                results["errors"].append(error_msg)
                self.report["errors"].append(error_msg)
                continue

            try:
                ad = self.create_ad(ad_row, adset_map[adset_name])
                ad_id = ad.get_id()
                results["ads"].append(ad_id)
                self.state["ads"][ad_name] = ad_id
                self.report["ads_created"].append(ad_id)
                self.save_state(campaign_folder)

            except MetaAdBuilderError as e:
                error_msg = f"Ad '{ad_name}': {str(e)}"
                print(f"  ❌ {error_msg}")
                results["errors"].append(error_msg)
                self.report["errors"].append(error_msg)

        # =====================================================================
        # STEP 7: Final summary and cleanup
        # =====================================================================
        print(f"\n{'='*50}")
        if results["errors"]:
            print(f"⚠️  Build completed with errors:")
            print(f"   Campaigns: {len(results['campaigns'])}")
            print(f"   Ad Sets:   {len(results['adsets'])}")
            print(f"   Ads:       {len(results['ads'])}")
            print(f"   Errors:    {len(results['errors'])}")
        else:
            print(f"✅ Build completed successfully!")
            print(f"   Campaigns: {len(results['campaigns'])}")
            print(f"   Ad Sets:   {len(results['adsets'])}")
            print(f"   Ads:       {len(results['ads'])}")
            # Clear state file on success
            self.clear_state(campaign_folder)

        # Update report
        self.report["completed_at"] = datetime.now().isoformat()
        self.report["success"] = len(results["errors"]) == 0

        return results

    def build_all_campaigns(
        self,
        campaigns_dir: str = "campaigns",
        dry_run: bool = False,
        resume: bool = False
    ) -> Dict[str, dict]:
        """
        Build all campaign folders in a directory.

        This allows processing multiple campaigns in one run.
        Skips the _template folder.

        Args:
            campaigns_dir: Path to directory containing campaign folders
            dry_run: If True, validate only without creating anything
            resume: If True, skip objects that were already created

        Returns:
            Dictionary mapping campaign folder names to their results
        """
        campaigns_path = Path(campaigns_dir)
        all_results = {}

        # Find all subdirectories (each is a campaign folder)
        campaign_folders = [
            d for d in campaigns_path.iterdir()
            if d.is_dir() and d.name != "_template" and not d.name.startswith(".")
        ]

        if not campaign_folders:
            print(f"No campaign folders found in {campaigns_dir}")
            return all_results

        print(f"\n📂 Found {len(campaign_folders)} campaign folder(s)")

        for folder in campaign_folders:
            print(f"\n{'='*60}")
            result = self.build_campaign_folder(
                str(folder),
                dry_run=dry_run,
                resume=resume
            )
            all_results[folder.name] = result

        # Print overall summary
        print(f"\n{'='*60}")
        print("📊 OVERALL SUMMARY")
        print(f"{'='*60}")

        total_campaigns = sum(len(r.get("campaigns", [])) for r in all_results.values())
        total_adsets = sum(len(r.get("adsets", [])) for r in all_results.values())
        total_ads = sum(len(r.get("ads", [])) for r in all_results.values())
        total_errors = sum(len(r.get("errors", [])) for r in all_results.values())

        print(f"Total Campaigns: {total_campaigns}")
        print(f"Total Ad Sets:   {total_adsets}")
        print(f"Total Ads:       {total_ads}")
        print(f"Total Errors:    {total_errors}")

        return all_results

    def save_report(self, output_path: str = "build_report.json") -> None:
        """
        Save the build report to a JSON file.

        The report contains:
        - Timestamps for when the build started and finished
        - Lists of created/updated object IDs
        - Any errors that occurred

        Args:
            output_path: Path where the JSON report will be saved
        """
        with open(output_path, "w") as f:
            json.dump(self.report, f, indent=2)
        print(f"\n📄 Report saved to: {output_path}")


# =============================================================================
# COMMAND LINE INTERFACE
# =============================================================================

def main():
    """
    Main entry point for command-line usage.

    This function:
    1. Parses command-line arguments
    2. Creates a MetaAdBuilder instance
    3. Runs the appropriate build command
    4. Handles errors and generates reports

    Usage examples:
        # Validate a campaign (dry run)
        python meta_ad_builder.py campaigns/my_campaign --dry-run

        # Build a single campaign
        python meta_ad_builder.py campaigns/my_campaign

        # Build all campaigns
        python meta_ad_builder.py --all

        # Resume a failed build
        python meta_ad_builder.py campaigns/my_campaign --resume

        # Update existing objects
        python meta_ad_builder.py campaigns/my_campaign --update
    """
    import argparse

    # Set up command-line argument parser
    parser = argparse.ArgumentParser(
        description="Build Meta Ads campaigns from CSV files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s campaigns/my_campaign --dry-run    Validate without creating
  %(prog)s campaigns/my_campaign              Build a single campaign
  %(prog)s campaigns/my_campaign --resume     Resume a failed build
  %(prog)s --all                              Build all campaigns
  %(prog)s --all --dry-run                    Validate all campaigns
        """
    )

    # Positional argument: campaign folder path
    parser.add_argument(
        "campaign_folder",
        nargs="?",  # Optional if --all is used
        help="Path to the campaign folder containing CSV files",
    )

    # Optional arguments
    parser.add_argument(
        "--config",
        default="config.json",
        help="Path to config file (default: config.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate CSV data without creating campaigns",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume a failed build, skipping already-created objects",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Update existing objects instead of creating new ones",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Build all campaign folders in the campaigns directory",
    )
    parser.add_argument(
        "--report",
        help="Path to save the build report JSON (default: no report)",
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.all and not args.campaign_folder:
        parser.error("Either campaign_folder or --all is required")

    # Run the builder
    try:
        # Initialize the builder with config
        builder = MetaAdBuilder(config_path=args.config)

        if args.all:
            # Build all campaigns in the campaigns directory
            builder.build_all_campaigns(
                dry_run=args.dry_run,
                resume=args.resume
            )
        else:
            # Build a single campaign folder
            builder.build_campaign_folder(
                args.campaign_folder,
                dry_run=args.dry_run,
                resume=args.resume,
                update_mode=args.update
            )

        # Save report if requested
        if args.report:
            builder.save_report(args.report)

    except FileNotFoundError as e:
        print(f"\n❌ File not found: {e}")
        sys.exit(1)
    except TokenExpiredError as e:
        print(f"\n❌ Token expired: {e}")
        sys.exit(2)
    except PaymentRequiredError as e:
        print(f"\n❌ Payment required: {e}")
        sys.exit(3)
    except PermissionError as e:
        print(f"\n❌ Permission denied: {e}")
        sys.exit(4)
    except ValidationError as e:
        print(f"\n❌ Validation error: {e}")
        sys.exit(5)
    except MetaAdBuilderError as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)


# This block runs only when the script is executed directly (not imported)
if __name__ == "__main__":
    main()
