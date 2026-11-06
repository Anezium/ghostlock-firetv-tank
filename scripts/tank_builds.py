"""Exact tank builds accepted by GhostLock and their public Amazon OTAs."""

DEFAULT_BUILD = "688805020"
OTA_URLS = {
    "688805020": (
        "https://d1s31zyz7dcc2d.cloudfront.net/2024/3/14/"
        "c5752488-58a3-4fe0-9ebf-9e4c3cc7d8a8/"
        "update-kindle-full_tank-288.6.8.8_user_688805020.bin"
    ),
    "688806320": (
        "https://d1s31zyz7dcc2d.cloudfront.prod.ota-cloudfront.net/2025/4/27/"
        "38765e03-905b-4f61-9ae5-332b496aa60a/"
        "update-kindle-full_tank-288.6.8.8_user_688806320.bin"
    ),
}
SUPPORTED_INCREMENTALS = frozenset(f"288.6.8.8_user_{build}" for build in OTA_URLS)
