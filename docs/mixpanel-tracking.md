# Argo usage tracking

Quick Start uses the browser SDK and two events, after explicit visitor consent.
This measures website usage, separately from the GitHub contributor dataset.

| Event | Trigger | Properties |
| --- | --- | --- |
| dashboard_viewed | First dashboard view after consent in a page load | platform: web |
| prediction_completed | Successful prediction API response initiated by a visitor | platform: web; prediction_source: manual or preset |

No signup or login exists, so visitors remain anonymous: no identify calls or
user profiles are created. No contributor identifiers, feature values, model
outputs, form text, or URL query parameters are sent. Autocapture, session replay,
automatic pageviews, referrer persistence and IP geolocation are disabled.
DNT and Global Privacy Control prevent initialization. Analytics failures do not
affect predictions.

## Configuration

Copy frontend/.env.example to frontend/.env.local and enter the project token.
Set NEXT_PUBLIC_MIXPANEL_TOKEN in the frontend hosting environment before building.
Use a separate development project for verification; do not test against production.
Match NEXT_PUBLIC_MIXPANEL_API_HOST to the project's data residency.
Public environment variables are included in the browser bundle; never use an API
secret or service account credential here.

## Consent and verification

The SDK loads only after Accept analytics. Decline analytics sends no events;
Analytics preferences lets visitors withdraw consent. Withdrawal clears SDK
persistence and stops future events. Browser privacy signals override acceptance.
Blocked local storage leaves tracking disabled.

Verify on a development build:
1. With clean storage, check that no Mixpanel requests occur before consent.
2. Decline and run a prediction: no events should occur.
3. Accept: dashboard_viewed appears once, including under React Strict Mode.
4. Complete manual and preset predictions: one prediction_completed per successful
   response, with only the approved custom properties. Failed requests emit none.
5. Withdraw consent and repeat: no new events. Reload retains the choice.
6. Check DNT/GPC, SDK load failure, and local-storage failure.
7. Confirm at least one real event in Mixpanel Live View before calling setup live.

The connector currently exposes only a demo E-Commerce project and rejects
business-context access. Live View verification and project residency/identity
settings remain unverified. No production events have been intentionally sent
during implementation.
