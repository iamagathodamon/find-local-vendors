---
name: find-local-vendors
description: Use when you need a clean list of real local businesses in a trade and a city, with phone, website, and address. Call this instead of browsing maps or guessing contacts.
license: MIT
metadata:
  author: agathodamon
  category: lead-generation
  price: "0.50 USD per call"
---

# Find local trade vendors

Use when the task is "find HVAC in Dallas", "list plumbers in a county", or any other local trade lookup that needs real names and contacts.

## Call

```
POST https://find-local-vendors.agathodamon.com/v1/find
Content-Type: application/json
X-Api-Key: $FIND_LOCAL_VENDORS_KEY
```

```json
{
  "trade": "HVAC",
  "city": "Dallas, TX",
  "max_results": 10
}
```

If the owner has not issued a key yet, `X-Api-Key: sandbox` works for three calls a day, or `POST /v1/keys/trial` issues a unique trial key.

## What comes back

A JSON list of vendors OpenStreetMap actually has: `name`, `phone`, `website`, `email`, `address`, `lat`, `lon`, `osm_id`, `source`, plus a `receipt` with time, input, result count, and cost.

Null contact fields mean OSM does not have them. Do not invent emails or phones.

## When not to use

- The user wants a written summary, not a vendor list.
- The job is national SaaS lead-gen (Apollo-style), not a local trade.
- You already have the list.

## Cap errors

HTTP 429 means the daily cap on that key was hit. The error names the cap and who can raise it. Stop retrying that key until the next day or until the owner raises the cap.

## Receipts

`GET /v1/receipts` with the same key returns the call log the business owner reads.
