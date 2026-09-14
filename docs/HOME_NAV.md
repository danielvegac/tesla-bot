# Home navigation

Home is a fixed pin (4.700454, -74.027738), not a Tesla favorite.
If the vehicle is asleep, `navigation_gps_request` returns 408.
Do not fall back to `navigation_request` with the string "casa" — Tesla rejects it (`value_not_supported`).
Wake first, then GPS request.
