<!-- atlas-pr-diff -->
## 🟡 Atlas map diff

**Map changed — review impact** &nbsp;·&nbsp; base `main-512d672` → head `main-20260522-105156`

`+9` new · `~5` changed · `-1` removed · `1` flows affected · `0` untested

<details><summary>🆕 New screens (9)</summary>

- [`trip_receipt_itemized`](https://app.revyl.ai/apps/3ccf53c0-314a-498a-b9c8-0b7bd173c57f/atlas?focus=screen&entityId=6c93ac9c-9252-4ff6-b81d-ac61369aa536) (detail) · _Account settings_ — Display a detailed financial breakdown of a completed trip fare, including taxes, fees, and payment method used.
- [`uber_one_benefits_list`](https://app.revyl.ai/apps/3ccf53c0-314a-498a-b9c8-0b7bd173c57f/atlas?focus=screen&entityId=c722ecc0-c7d1-445d-9d16-5d7145b5697f) (list) · _Account settings_ — Display a comprehensive list of all membership benefits categorized by service type like Eats, Rides, and Grocery.
- [`uber_one_checkout`](https://app.revyl.ai/apps/3ccf53c0-314a-498a-b9c8-0b7bd173c57f/atlas?focus=screen&entityId=1b3a5a5a-680d-4024-a476-f91bc7135794) (checkout) · _Account settings_ — Review and confirm a subscription membership plan and payment method to start a free trial or paid membership.
- [`uber_one_membership_detail`](https://app.revyl.ai/apps/3ccf53c0-314a-498a-b9c8-0b7bd173c57f/atlas?focus=screen&entityId=6ad07ae7-8a07-4e30-bce6-81624bd90430) (detail) · _Account settings_ — Explain the benefits of the Uber One membership and provide an entry point for users to subscribe or start a trial.
- [`uber_one_signup_success`](https://app.revyl.ai/apps/3ccf53c0-314a-498a-b9c8-0b7bd173c57f/atlas?focus=screen&entityId=21e47d5a-fe24-4571-ba81-58ad43a63755) (onboarding) · _Account settings_ — Confirm that the user has successfully started their Uber One membership and highlight the active benefits.
- [`package_delivery_checkout_review`](https://app.revyl.ai/apps/3ccf53c0-314a-498a-b9c8-0b7bd173c57f/atlas?focus=screen&entityId=5e11dec4-633b-4468-b70b-db68f025a644) (checkout) · _Commerce_ — Review package details, pickup/drop-off locations, and estimated cost before confirming the delivery request.
- [`package_pickup_details_form`](https://app.revyl.ai/apps/3ccf53c0-314a-498a-b9c8-0b7bd173c57f/atlas?focus=screen&entityId=2b1078c0-831d-4e19-9f97-0acbddb11de4) (form) · _Commerce_ — Capture the pickup address, sender contact information, and specific driver instructions for a package delivery request.
- [`airline_selection_list`](https://app.revyl.ai/apps/3ccf53c0-314a-498a-b9c8-0b7bd173c57f/atlas?focus=screen&entityId=a2ae31f4-2b2a-4b20-946d-07155470134d) (list) · _Home_ — Allows users to select their airline to help drivers identify the correct terminal for airport drop-offs or pickups.
- [`ride_receipt_rating`](https://app.revyl.ai/apps/3ccf53c0-314a-498a-b9c8-0b7bd173c57f/atlas?focus=screen&entityId=0d8aa552-e396-4096-906a-145537874a77) (checkout) · _Home_ — To provide a trip summary including cost and distance, and to allow the user to rate and tip the driver after arrival.
</details>

<details><summary>✏️ Changed screens (5)</summary>

- [`account_profile_hub`](https://app.revyl.ai/apps/3ccf53c0-314a-498a-b9c8-0b7bd173c57f/atlas?focus=screen&entityId=24caf738-ca8f-4c52-8d52-f2435ca940f2) · _Account settings_
  - now navigates to new screen `uber_one_membership_detail`
- [`package_details_entry`](https://app.revyl.ai/apps/3ccf53c0-314a-498a-b9c8-0b7bd173c57f/atlas?focus=screen&entityId=0bd516d7-b7f0-4d4e-8538-3d8200adc2d3) · _Commerce_
  - now navigates to new screen `package_pickup_details_form`
- [`ride_destination_search_results`](https://app.revyl.ai/apps/3ccf53c0-314a-498a-b9c8-0b7bd173c57f/atlas?focus=screen&entityId=00ea4bb5-7b7f-4907-b8e0-d0a277bed1e6) · _Home_
  - now navigates to new screen `airline_selection_list`
- [`ride_en_route_tracking`](https://app.revyl.ai/apps/3ccf53c0-314a-498a-b9c8-0b7bd173c57f/atlas?focus=screen&entityId=02f6f04b-fc75-4648-aa0d-cd9a95e17ea5) · _Home_
  - now navigates to new screen `ride_receipt_rating`
- [`ride_service_selection`](https://app.revyl.ai/apps/3ccf53c0-314a-498a-b9c8-0b7bd173c57f/atlas?focus=screen&entityId=0f5c504e-1a93-440f-bbff-42f3a8cb7f07) · _Home_
  - no longer navigates to removed screen `ride_matching_status`
</details>

### 🗑️ Removed / no longer reached (1)
- [`ride_matching_status`](https://app.revyl.ai/apps/3ccf53c0-314a-498a-b9c8-0b7bd173c57f/atlas?focus=screen&entityId=778e0e09-3f18-4088-b24c-0a3d07ee77f2) (loading) · _Home_

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
<sub>🗺️ <a href="https://github.com/ethanzhoucool/atlas-pr-diff">atlas-pr-diff</a> · 15 screen deltas · base 46 → head 54 screens</sub>