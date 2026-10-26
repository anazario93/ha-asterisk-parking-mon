# Asterisk Parking Monitor

A Home Assistant custom integration that monitors Asterisk parking slots over AMI.

## Features

- Configure AMI host, port, username, password, and parking lot from the Home Assistant UI.
- Configure an inclusive parking-slot range (defaults to **401–403**).
- Creates one sensor per slot with state `free`, `waiting`, or `unknown`.
- Reconnects to AMI after connection failures.
- Changes states to `unknown` on disconnect rather than incorrectly reporting slots as free.

## Installation via HACS

1. In Home Assistant, open **HACS → Integrations**.
2. Open the three-dot menu and select **Custom repositories**.
3. Add `https://github.com/anazario93/ha-asterisk-parking-mon` and choose category **Integration**.
4. Install **Asterisk Parking Monitor**.
5. Restart Home Assistant.
6. Go to **Settings → Devices & services → Add integration**, search for **Asterisk Parking Monitor**, and configure the connection.

If HACS already lists the repository, install it directly from HACS instead.

## Configuration

- **AMI host**: hostname or IP address of the Asterisk server.
- **AMI port**: normally `5038`.
- **AMI username/password**: credentials for an AMI user allowed to log in and receive relevant events.
- **Parking lot**: the configured Asterisk parking lot name (defaults to `default`).
- **First/last slot**: inclusive numeric range (defaults to `401` through `403`).

You can edit settings after setup using the integration's **Configure** action.

## Entities

For the default range, the integration creates sensors for slots 401, 402, and 403. Each sensor reports:

- `free`: initial parking snapshot completed and no parked call was reported for the slot, or a release event was received.
- `waiting`: Asterisk reported a call parked in the slot.
- `unknown`: initial state is not yet known or the AMI connection is unavailable.

Caller ID and channel information may be exposed as entity attributes when supplied by AMI.

## Important notes

This integration needs validation against your specific Asterisk version and parking configuration. AMI event fields and parking status behavior can vary. Test call parking, pickup, timeout, disconnect, and startup-with-an-already-parked-call before relying on these sensors for critical automations.

Use a trusted LAN or VPN. Do not expose AMI port 5038 directly to the public internet. Use a least-privilege AMI account and protect Home Assistant backups, which may contain integration credentials.

## Troubleshooting

- Confirm AMI is enabled and reachable from Home Assistant.
- Confirm the AMI account has appropriate read/event permissions.
- Confirm the parking lot name and slot range match the Asterisk configuration.
- Check **Settings → System → Logs** for `asterisk_parking` messages.
