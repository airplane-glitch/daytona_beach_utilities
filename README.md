# Daytona Beach Utilities

> **Early test version.** This is the first test of this integration. If you hit any errors, please [open an issue](https://github.com/airplane-glitch/daytona_beach_utilities/issues) and include the message from the Home Assistant log (remove any personal details first). Inspired by the [FPL integration](https://github.com/dotKrad/hass-fpl).

A Home Assistant integration for the City of Daytona Beach utility bill (water, sewer, garbage, stormwater). It reads the
customer portal at [cc.codb.us](https://cc.codb.us) the way the website does, so there is nothing to apply for.

Unofficial, and not affiliated with the City of Daytona Beach. It only reads; it never pays a bill or changes anything.

## Install

1. In HACS, open the menu, choose **Custom repositories**, and add `https://github.com/airplane-glitch/daytona_beach_utilities` as an **Integration**.
2. Download **Daytona Beach Utilities** and restart Home Assistant.
3. Go to **Settings, Devices & services, Add integration**, pick **Daytona Beach Utilities**, and enter the portal username and password.

Every account on the login is added as its own device, one for each house. The portal is checked every 6 hours, since bills change about once a month.

## Sensors, for each account

- Amount due, latest bill, balance carried forward, average bill (last 12)
- Payment due date and latest bill date
- Water used on the latest bill (`kgal`; the portal does not state the unit, and 1 kgal is 1,000 gallons)
- A charge for each service on the latest bill: water, sewer, garbage, stormwater, utility tax

The latest bill sensor also carries the last 12 bills (date, amount, usage) as an attribute.

## Notes

- The username and password are kept in Home Assistant's own config storage, like any integration, and are sent only to cc.codb.us.
- Devices are named after the account's street address and keyed by account number. Both stay inside your Home Assistant.
- If the city changes its website, the integration may stop working until it is updated. Open an issue if that happens.

## Tests

`pip install pytest pytest-asyncio pytest-aiohttp aiohttp`, then `pytest`. The tests use made-up data and a fake portal.
