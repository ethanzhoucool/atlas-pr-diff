<!-- atlas-pr-diff -->
## 🔴 Atlas map diff

**New/changed screens are untested** &nbsp;·&nbsp; base `main-512d672` → head `main-c6739d8-ipad`

`+10` new · `~9` changed · `-4` removed · `1` flows affected · `3` untested
<sub>1 more screen(s) differ only by low-confidence navigation noise (hidden — likely exploration variance, not a real change).</sub>

<details><summary>🔴 Now untested (3)</summary>

New or changed screens that **no test reaches** — the gap this PR introduces:

- [`uber_one_membership_marketing`](https://app.revyl.ai/apps/3ccf53c0-314a-498a-b9c8-0b7bd173c57f/atlas?focus=screen&entityId=0f988fbf-1cd3-40bd-af33-0ad67a0566be) · _Account settings_ (new)
  - reach it: `rides_home_personalized_dashboard` → `account_profile_hub` → `uber_one_membership_marketing`
  - cover it: `revyl test create --app "Ubert"` then exercise this screen
- [`trip_summary_rating`](https://app.revyl.ai/apps/3ccf53c0-314a-498a-b9c8-0b7bd173c57f/atlas?focus=screen&entityId=3038b3d4-0448-44ac-9b51-43b176b89ebc) · _Commerce_ (new)
  - reach it: `ride_en_route_tracking` → `trip_summary_rating`
  - cover it: `revyl test create --app "Ubert"` then exercise this screen
- [`airline_selection_list`](https://app.revyl.ai/apps/3ccf53c0-314a-498a-b9c8-0b7bd173c57f/atlas?focus=screen&entityId=a2ae31f4-2b2a-4b20-946d-07155470134d) · _Home_ (new)
  - entry screen (reached directly)
  - cover it: `revyl test create --app "Ubert"` then exercise this screen
</details>

<details><summary>🆕 New screens (10)</summary>

- [`uber_one_checkout`](https://app.revyl.ai/apps/3ccf53c0-314a-498a-b9c8-0b7bd173c57f/atlas?focus=screen&entityId=1b3a5a5a-680d-4024-a476-f91bc7135794) (checkout) · _Account settings_ — Review and confirm a subscription membership plan and payment method to start a free trial or paid membership.
- [`uber_one_membership_detail`](https://app.revyl.ai/apps/3ccf53c0-314a-498a-b9c8-0b7bd173c57f/atlas?focus=screen&entityId=6ad07ae7-8a07-4e30-bce6-81624bd90430) (detail) · _Account settings_ — Explain the benefits of the Uber One membership and provide an entry point for users to subscribe or start a trial.
- [`uber_one_membership_marketing`](https://app.revyl.ai/apps/3ccf53c0-314a-498a-b9c8-0b7bd173c57f/atlas?focus=screen&entityId=0f988fbf-1cd3-40bd-af33-0ad67a0566be) (onboarding) · _Account settings_ — Promote and sell the Uber One subscription membership by highlighting benefits and offering a free trial.
- [`uber_one_signup_success`](https://app.revyl.ai/apps/3ccf53c0-314a-498a-b9c8-0b7bd173c57f/atlas?focus=screen&entityId=21e47d5a-fe24-4571-ba81-58ad43a63755) (onboarding) · _Account settings_ — Confirm that the user has successfully started their Uber One membership and highlight the active benefits.
- [`package_delivery_checkout_review`](https://app.revyl.ai/apps/3ccf53c0-314a-498a-b9c8-0b7bd173c57f/atlas?focus=screen&entityId=5e11dec4-633b-4468-b70b-db68f025a644) (checkout) · _Commerce_ — Review package details, pickup/drop-off locations, and estimated cost before confirming the delivery request.
- [`package_pickup_details_form`](https://app.revyl.ai/apps/3ccf53c0-314a-498a-b9c8-0b7bd173c57f/atlas?focus=screen&entityId=2b1078c0-831d-4e19-9f97-0acbddb11de4) (form) · _Commerce_ — Capture the pickup address, sender contact information, and specific driver instructions for a package delivery request.
- [`shops_cart_empty`](https://app.revyl.ai/apps/3ccf53c0-314a-498a-b9c8-0b7bd173c57f/atlas?focus=screen&entityId=2ccd3e73-1c87-422d-bb22-2390adb7f497) (empty_state) · _Commerce_ — Displays a message to the user when no items have been added to their shopping cart.
- [`trip_summary_rating`](https://app.revyl.ai/apps/3ccf53c0-314a-498a-b9c8-0b7bd173c57f/atlas?focus=screen&entityId=3038b3d4-0448-44ac-9b51-43b176b89ebc) (checkout) · _Commerce_ — Allows users to review trip statistics, rate their driver, and provide a tip after arriving at their destination.
- [`airline_selection_list`](https://app.revyl.ai/apps/3ccf53c0-314a-498a-b9c8-0b7bd173c57f/atlas?focus=screen&entityId=a2ae31f4-2b2a-4b20-946d-07155470134d) (list) · _Home_ — Allows users to select their airline to help drivers identify the correct terminal for airport drop-offs or pickups.
- [`ride_receipt_rating`](https://app.revyl.ai/apps/3ccf53c0-314a-498a-b9c8-0b7bd173c57f/atlas?focus=screen&entityId=0d8aa552-e396-4096-906a-145537874a77) (checkout) · _Home_ — To provide a trip summary including cost and distance, and to allow the user to rate and tip the driver after arrival.
</details>

<details><summary>✏️ Changed screens (9)</summary>

- [`account_profile_hub`](https://app.revyl.ai/apps/3ccf53c0-314a-498a-b9c8-0b7bd173c57f/atlas?focus=screen&entityId=24caf738-ca8f-4c52-8d52-f2435ca940f2) · _Account settings_
  - now navigates to new screen `uber_one_membership_marketing`
  - now navigates to new screen `uber_one_membership_detail`
- [`account_settings`](https://app.revyl.ai/apps/3ccf53c0-314a-498a-b9c8-0b7bd173c57f/atlas?focus=screen&entityId=1286c8f6-97c8-46f0-9707-e79468cb5cf1) · _Account settings_
  - no longer navigates to removed screen `account_settings_language_picker`
  - no longer navigates to removed screen `notification_preferences`
- [`help_landing`](https://app.revyl.ai/apps/3ccf53c0-314a-498a-b9c8-0b7bd173c57f/atlas?focus=screen&entityId=b5b990af-5be2-407c-9943-11b670674c20) · _Account settings_
  - no longer navigates to removed screen `contact_support_form`
- [`car_rental_checkout`](https://app.revyl.ai/apps/3ccf53c0-314a-498a-b9c8-0b7bd173c57f/atlas?focus=screen&entityId=1e6c7905-7fa3-4dce-8bb5-81f897a03d46) · _Commerce_
  - no longer navigates to removed screen `car_rental_checkout_confirmation`
- [`package_details_entry`](https://app.revyl.ai/apps/3ccf53c0-314a-498a-b9c8-0b7bd173c57f/atlas?focus=screen&entityId=0bd516d7-b7f0-4d4e-8538-3d8200adc2d3) · _Commerce_
  - now navigates to new screen `package_pickup_details_form`
- [`shops_storefront_grocery`](https://app.revyl.ai/apps/3ccf53c0-314a-498a-b9c8-0b7bd173c57f/atlas?focus=screen&entityId=7230ce6b-4cee-422e-becc-3667788e2a16) · _Commerce_
  - now navigates to new screen `shops_cart_empty`
- [`ride_destination_search_results`](https://app.revyl.ai/apps/3ccf53c0-314a-498a-b9c8-0b7bd173c57f/atlas?focus=screen&entityId=00ea4bb5-7b7f-4907-b8e0-d0a277bed1e6) · _Home_
  - now navigates to new screen `airline_selection_list`
- [`ride_en_route_tracking`](https://app.revyl.ai/apps/3ccf53c0-314a-498a-b9c8-0b7bd173c57f/atlas?focus=screen&entityId=02f6f04b-fc75-4648-aa0d-cd9a95e17ea5) · _Home_
  - now navigates to new screen `trip_summary_rating`
  - now navigates to new screen `ride_receipt_rating`
- [`ride_matching_status`](https://app.revyl.ai/apps/3ccf53c0-314a-498a-b9c8-0b7bd173c57f/atlas?focus=screen&entityId=2fe1bdac-b34e-4d25-95a6-0ca4d42c73e5) · _Home_
  - purpose/description changed
  - primary actions +1 -1
</details>

### 🗑️ Removed / no longer reached (4)
- [`account_settings_language_picker`](https://app.revyl.ai/apps/3ccf53c0-314a-498a-b9c8-0b7bd173c57f/atlas?focus=screen&entityId=4267c660-9df2-467a-be0b-7b126a8af605) (list) · _Account settings_
- [`contact_support_form`](https://app.revyl.ai/apps/3ccf53c0-314a-498a-b9c8-0b7bd173c57f/atlas?focus=screen&entityId=18355c76-761f-49b8-9468-84028c275e89) (form) · _Account settings_
- [`notification_preferences`](https://app.revyl.ai/apps/3ccf53c0-314a-498a-b9c8-0b7bd173c57f/atlas?focus=screen&entityId=5a03f397-ac31-4661-8c44-5434d29d0a4e) (settings) · _Account settings_
- [`car_rental_checkout_confirmation`](https://app.revyl.ai/apps/3ccf53c0-314a-498a-b9c8-0b7bd173c57f/atlas?focus=screen&entityId=470d4f01-b666-46f3-9254-b40c92b6a7f0) (checkout) · _Commerce_

### 🔀 Flows affected downstream (1)
- **Select a ride** — touches `help_landing`, `ride_destination_search_results`

<details><summary>📉 Lost test coverage (36)</summary>

- `rides_home_personalized_dashboard` → `account_profile_hub` (the 'Account' tab icon and text at the bottom right of the screen)
- `account_profile_hub` → `help_landing` (the row labeled 'Help' with a question mark icon to its left)
- `rides_home_personalized_dashboard` → `account_profile_hub` (the 'Account' tab with a person icon at the bottom right)
- `rides_home_personalized_dashboard` → `account_profile_hub` (the 'Account' icon and text in the bottom navigation bar)
- `rides_home_personalized_dashboard` → `account_profile_hub` (the 'Account' tab icon with a person silhouette at the bottom right)
- `rides_home_personalized_dashboard` → `account_profile_hub` (the 'Account' tab with a person icon and the text 'Account')
- `support_ai_chat` → `help_landing` (the white left-pointing arrow icon inside a black circular button in the top left corner)
- `delivery_checkout_confirmation` → `order_status_tracking` (the green button at the bottom containing the text 'Place order' and '$26.14')
- `activity_history` → `ride_trip_receipt` (the trip card with 'JFK Airport - Terminal 4' and '$48.70')
- `activity_history` → `ride_trip_receipt` (the trip entry with 'JFK Airport - Terminal 4' and '$48.70')
- `ride_service_selection` → `ride_en_route_tracking` (the black rectangular button with white 'Confirm UberX' text)
- `account_settings` → `account_settings_language_picker` (the row labeled 'App language' with 'English' and a right chevron)
- …(+24 more)
</details>

---
<sub>🗺️ <a href="https://github.com/ethanzhoucool/atlas-pr-diff">atlas-pr-diff</a> · 23 screen deltas · base 46 → head 52 screens</sub>