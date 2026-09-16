# Find local trade vendors

Use when an agent needs a clean list of real local businesses in a trade and a city, with phone, website, and address.

One URL. One job. Paid per call.

Public: https://find-local-vendors.agathodamon.com

```
POST https://find-local-vendors.agathodamon.com/v1/find
{"trade":"HVAC","city":"Dallas, TX","max_results":10}
```

Skill listing:

```
npx skills add iamagathodamon/find-local-vendors
```

Returns name, phone, website, address, coordinates, OSM id, and a receipt.

## Door

Double-click `FIND_LOCAL_VENDORS.cmd`. It starts the endpoint, waits for health, and prints one status block.

Sandbox key: `sandbox` (3 free calls per day).

Paid key: `$0.50` per call, `$25` daily cap unless raised.

## Why this exists

Agents only use software they can call. This endpoint is the callable form of a job businesses already pay for: find the local trades in a city and hand back contacts.
