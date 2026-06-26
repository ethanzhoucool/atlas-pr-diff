<!-- atlas-pr-diff -->
## 🟡 Atlas map diff

**Map changed — review impact** &nbsp;·&nbsp; base `main-512d672` → head `main-20260522-105156`

`+9` new · `~5` changed · `-1` removed · `1` flows affected · `0` untested

### 🆕 New screens (9)
- `trip_receipt_itemized` (detail) · _Account settings_ — Display a detailed financial breakdown of a completed trip fare, including taxes, fees, and payment method used.
- `uber_one_benefits_list` (list) · _Account settings_ — Display a comprehensive list of all membership benefits categorized by service type like Eats, Rides, and Grocery.
- `uber_one_checkout` (checkout) · _Account settings_ — Review and confirm a subscription membership plan and payment method to start a free trial or paid membership.
- `uber_one_membership_detail` (detail) · _Account settings_ — Explain the benefits of the Uber One membership and provide an entry point for users to subscribe or start a trial.
- `uber_one_signup_success` (onboarding) · _Account settings_ — Confirm that the user has successfully started their Uber One membership and highlight the active benefits.
- `package_delivery_checkout_review` (checkout) · _Commerce_ — Review package details, pickup/drop-off locations, and estimated cost before confirming the delivery request.
- `package_pickup_details_form` (form) · _Commerce_ — Capture the pickup address, sender contact information, and specific driver instructions for a package delivery request.
- `airline_selection_list` (list) · _Home_ — Allows users to select their airline to help drivers identify the correct terminal for airport drop-offs or pickups.
- `ride_receipt_rating` (checkout) · _Home_ — To provide a trip summary including cost and distance, and to allow the user to rate and tip the driver after arrival.

### ✏️ Changed screens (5)
- `account_profile_hub` · _Account settings_
  - now navigates to new screen `uber_one_membership_detail`
- `package_details_entry` · _Commerce_
  - now navigates to new screen `package_pickup_details_form`
- `ride_destination_search_results` · _Home_
  - now navigates to new screen `airline_selection_list`
- `ride_en_route_tracking` · _Home_
  - now navigates to new screen `ride_receipt_rating`
- `ride_service_selection` · _Home_
  - no longer navigates to removed screen `ride_matching_status`

### 🗑️ Removed / no longer reached (1)
- `ride_matching_status` (loading) · _Home_

### 🔀 Flows affected downstream (1)
- **Select a ride** — touches `ride_destination_search_results`, `ride_service_selection`

### 📉 Lost test coverage (7)
- `ride_service_selection` → `ride_matching_status` (Device action: tap)
- `ride_service_selection` → `ride_matching_status` (the black button at the bottom with white 'Confirm UberX' text)
- `delivery_home_feed` → `home_courier_landing` (Device action: tap)
- `ride_matching_status` → `rides_home_personalized_dashboard` (Device action: tap)
- `ride_matching_status` → `ride_en_route_tracking` (Waiting for the 'Finding your driver' process to complete and transition to the 'Driver Matched' screen where 'Start Trip' will be available.)
- `shops_home_feed` → `rides_home_personalized_dashboard` (Device action: tap)
- `help_landing` → `rides_home_personalized_dashboard` (the left-pointing arrow icon in the top-left corner)

---
<sub>🗺️ atlas-pr-diff · 15 screen deltas · base 46 → head 54 screens</sub>