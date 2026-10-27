"""Read-only Nova Poshta account API. No Home Assistant dependency."""
import asyncio
from datetime import datetime, timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo

import aiohttp

API_URL = "https://api.novaposhta.ua/v2.0/json/"
TRACKING_URL = "https://api.novaposhta.ua/site/v.1.0/shipments/tracking/"
METHODS = {
    "incoming": "getIncomingDocumentsByPhone",
    "outgoing": "getOutgoingDocumentsByPhone",
}
TERMINAL = {"2", "3", "9", "10", "11", "102", "103", "106"}
PICKUP = {"7", "8"}
TRANSIT = {"4", "5", "6", "12", "41", "101", "104", "111", "112"}


class ApiError(Exception):
    """Service rejected the query or changed its response format."""


class AuthenticationError(ApiError):
    """API key is invalid or no longer authorized."""


def unpack(payload):
    """Accept JSON and the text/plain JSON occasionally returned by this API."""
    if not isinstance(payload, dict) or payload.get("success") is not True:
        errors = str(payload.get("errors", [])) if isinstance(payload, dict) else ""
        if any(word in errors.lower() for word in ("api key", "apikey", "auth", "token")):
            raise AuthenticationError("API key was rejected")
        # Never expose arbitrary provider messages, keys or customer data in logs.
        raise ApiError("Nova Poshta did not return a successful response")
    data = payload.get("data")
    if not isinstance(data, list):
        raise ApiError("Unexpected data format")
    if not data:
        return []
    if len(data) != 1 or not isinstance(data[0], dict) or not isinstance(data[0].get("result"), list):
        raise ApiError("Unexpected account parcel-list format")
    rows = data[0]["result"]
    if any(not isinstance(row, dict) or not row.get("Number") for row in rows):
        raise ApiError("Unexpected parcel format")
    return rows


def real_date(value):
    value = str(value or "")
    return value if value and not value.startswith(("0001-", "0000-", "0000.")) else None


def delivery_datetime(value):
    """Account API dates use Ukrainian local time; tracking API dates include UTC."""
    value = real_date(value)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo("Europe/Kyiv"))
    return parsed.isoformat()


def apply_tracking_details(parcel, payload, language="uk"):
    """Use current or latest completed event; planned events are never statuses."""
    if not isinstance(payload, dict) or not isinstance(payload.get("tracking"), list):
        raise ApiError("Unexpected tracking history format")
    events = [event for event in payload["tracking"] if isinstance(event, dict)
              and event.get("event_status") in ("now", "passed")
              and event.get("event_name") and delivery_datetime(event.get("date"))]
    current = [event for event in events if event["event_status"] == "now"]
    latest = None
    if current or events:
        latest = max(current or events, key=lambda event: datetime.fromisoformat(delivery_datetime(event["date"])))
        parcel["status_detail"] = latest["event_name"]
        parcel["status_detail_language"] = language
        parcel.setdefault("status_details", {})[language] = latest["event_name"]
        parcel["status_updated_at"] = delivery_datetime(latest["date"])
    estimate = delivery_datetime(payload.get("scheduled_delivery_date"))
    if estimate:
        parcel["expected_delivery"] = estimate
    return latest


def apply_event_translation(parcel, payload, language, reference):
    """Translate the same actual event, even if tracking advanced between calls."""
    if not reference or not isinstance(payload, dict) or not isinstance(payload.get("tracking"), list):
        return
    for event in payload["tracking"]:
        if (isinstance(event, dict) and event.get("event_status") in ("now", "passed")
                and event.get("event") == reference.get("event")
                and delivery_datetime(event.get("date")) == delivery_datetime(reference.get("date"))
                and event.get("event_name")):
            parcel.setdefault("status_details", {})[language] = event["event_name"]
            return


def normalize(row, direction):
    """Keep only display fields; exclude phones, payment data and customer IDs."""
    code = str(row.get("TrackingStatusCode", ""))
    if code in TERMINAL or row.get("DeletionMark") in (True, 1, "1", "true") or real_date(row.get("ReceivingDateTime")):
        return None
    state = "at_pickup_point" if code in PICKUP else "in_transit" if code in TRANSIT else "registered" if code == "1" else "unknown"
    return {
        "tracking_number": str(row["Number"]),
        "direction": direction,
        "status": state,
        "status_code": code,
        "status_text": row.get("TrackingStatusName") or "",
        "description": row.get("CargoDescription") or "",
        "sender": row.get("CounterpartySenderDescription") or row.get("SenderName") or "",
        "city": row.get("CityRecipientDescription") or "",
        "address": row.get("RecipientAddressDescription") or "",
        "expected_delivery": delivery_datetime(row.get("ScheduledDeliveryDate")) or delivery_datetime(row.get("ArrivalDateTime")),
        "tracking_url": "https://novaposhta.ua/tracking/" + str(row["Number"]),
    }


class NovaPoshtaApi:
    def __init__(self, session, api_key):
        self.session = session
        self._api_key = api_key

    async def _page(self, method, properties):
        try:
            async with self.session.post(
                API_URL,
                json={"apiKey": self._api_key, "modelName": "InternetDocument", "calledMethod": method, "methodProperties": properties},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status in (401, 403):
                    raise AuthenticationError("API key was rejected")
                response.raise_for_status()
                payload = await response.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            raise ApiError("Unable to read the Nova Poshta API") from err
        return unpack(payload)

    async def _tracking(self, number, language="uk"):
        try:
            async with self.session.get(
                TRACKING_URL + quote(number, safe=""), headers={"Accept-Language": language},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as response:
                response.raise_for_status()
                return await response.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            raise ApiError("Unable to read detailed tracking") from err

    async def _enrich(self, parcels):
        semaphore = asyncio.Semaphore(4)

        async def enrich(parcel):
            async def localized(language):
                async with semaphore:
                    try:
                        return await self._tracking(parcel["tracking_number"], language)
                    except ApiError:
                        return None
            languages = ("uk", "en", "ru")
            payloads = dict(zip(languages, await asyncio.gather(*(localized(lang) for lang in languages))))
            for language in languages:
                if payloads[language] is None:
                    continue
                try:
                    reference = apply_tracking_details(parcel, payloads[language], language)
                except ApiError:
                    continue
                if reference is not None:
                    for other in languages:
                        if other != language:
                            apply_event_translation(parcel, payloads[other], other, reference)
                    break
        await asyncio.gather(*(enrich(parcel) for parcel in parcels))

    async def parcels(self, now, days=365, direction="both"):
        directions = tuple(METHODS) if direction == "both" else (direction,)
        found = {}
        for kind in directions:
            seen = set()
            for page in range(1, 101):
                rows = await self._page(METHODS[kind], {
                    "DateTimeFrom": (now - timedelta(days=days)).strftime("%d.%m.%Y"),
                    "DateTimeTo": (now + timedelta(days=1)).strftime("%d.%m.%Y"),
                    "Page": str(page),
                })
                if not rows:
                    break
                numbers = {str(row["Number"]) for row in rows}
                if not numbers - seen:
                    raise ApiError("API repeated a page; parcel list may be incomplete")
                seen.update(numbers)
                for row in rows:
                    parcel = normalize(row, kind)
                    if parcel:
                        found.setdefault(parcel["tracking_number"], parcel)
                # The service uses pages of up to 100 records. Always request
                # the next page, even after a short page, to avoid silent loss.
            else:
                raise ApiError("Pagination limit reached; parcel list may be incomplete")
        await self._enrich(list(found.values()))
        return sorted(found.values(), key=lambda p: (p["status"] != "at_pickup_point", p["expected_delivery"] or "9999", p["tracking_number"]))
