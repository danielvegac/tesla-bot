# Home and work navigation

Home is a fixed pin (4.700454, -74.027738), not a Tesla favorite.
Work is the same pattern: only a pin captured from live Fleet GPS while
parked at the office. Set `WORK_LAT` / `WORK_LON` / optional `WORK_LABEL`
in Desktop `.env`. Until those exist, `marca oficina` must not send anything.

If the vehicle is asleep, `navigation_gps_request` returns 408.
Do not fall back to `navigation_request` with the string "casa" or "oficina"
— Tesla rejects free-text home/work (`value_not_supported`).
Wake first, then GPS request.

Geofence radius is 80 m for both pins. "marca casa" inside the home fence
does not POST. Same rule for work once the pin exists.
