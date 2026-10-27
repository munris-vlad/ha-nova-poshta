"""Filtering, pagination, failure handling and privacy regression tests."""
import importlib.util
import pathlib
import unittest
from datetime import datetime

spec = importlib.util.spec_from_file_location("parcel_api", pathlib.Path(__file__).parents[1] / "custom_components/nova_poshta_account/api.py")
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


def parcel(number="12345678901234", code="6", **kwargs):
    return {"Number": number, "TrackingStatusCode": code, **kwargs}


class FilteringTests(unittest.TestCase):
    def test_translation_matches_actual_event_instead_of_future_or_newer_event(self):
        row = api.normalize(parcel(), "incoming")
        reference = api.apply_tracking_details(row, {"tracking": [
            {"event":"Arrival", "event_status":"now", "date":"2026-10-27T15:00:00Z", "event_name":"Прибула"}
        ]})
        api.apply_event_translation(row, {"tracking": [
            {"event":"Arrival", "event_status":"passed", "date":"2026-10-27T15:00:00Z", "event_name":"Arrived"},
            {"event":"Received", "event_status":"now", "date":"2026-10-27T16:00:00Z", "event_name":"Received"},
        ]}, "en", reference)
        self.assertEqual(row["status_details"], {"uk":"Прибула", "en":"Arrived"})
        api.apply_event_translation(row, {"tracking": [
            {"event":"Arrival", "event_status":"future", "date":"2026-10-27T15:00:00Z", "event_name":"Wrong"}
        ]}, "ru", reference)
        self.assertNotIn("ru", row["status_details"])

    def test_actual_detail_excludes_future_and_handles_unsorted_history(self):
        p = api.normalize(parcel(), "incoming")
        api.apply_tracking_details(p, {"tracking": [
            {"event_status": "future", "date": "2026-10-28T16:00:00Z", "event_name": "Will arrive"},
            {"event_status": "now", "date": "2026-10-27T15:31:44Z", "event_name": "Виїхала з адресного депо"},
            {"event_status": "passed", "date": "2026-10-27T14:54:00Z", "event_name": "Arrived"},
        ], "scheduled_delivery_date": "2026-10-28T16:00:00Z"})
        self.assertEqual(p["status_detail"], "Виїхала з адресного депо")
        self.assertEqual(datetime.fromisoformat(p["expected_delivery"]).astimezone(api.ZoneInfo("Europe/Kyiv")).hour, 18)

    def test_latest_completed_event_without_now(self):
        p = api.normalize(parcel(), "incoming")
        api.apply_tracking_details(p, {"tracking": [
            {"event_status": "passed", "date": "2026-10-27T14:00:00Z", "event_name": "New"},
            {"event_status": "passed", "date": "2026-10-26T14:00:00Z", "event_name": "Old"},
        ]})
        self.assertEqual(p["status_detail"], "New")

    def test_account_delivery_is_ukrainian_local_time(self):
        self.assertEqual(api.delivery_datetime("2026-10-28 18:00:00"), "2026-10-28T18:00:00+02:00")
        self.assertEqual(api.delivery_datetime("2026-07-01 18:00:00"), "2026-07-01T18:00:00+03:00")
        self.assertIsNone(api.delivery_datetime("bad date"))

    def test_delivered_deleted_and_received_are_hidden(self):
        for code in api.TERMINAL:
            self.assertIsNone(api.normalize(parcel(code=code), "incoming"))
        self.assertIsNone(api.normalize(parcel(DeletionMark=True), "incoming"))
        self.assertIsNone(api.normalize(parcel(ReceivingDateTime="2026-10-27 14:00:00"), "incoming"))

    def test_pickup_transit_created_unknown_and_missing_dates(self):
        for code, expected in [("7", "at_pickup_point"), ("8", "at_pickup_point"), ("6", "in_transit"), ("1", "registered"), ("999", "unknown")]:
            result = api.normalize(parcel(code=code, ReceivingDateTime="0001-01-01 00:00:00", ScheduledDeliveryDate="0001-01-01 00:00:00"), "incoming")
            self.assertEqual(result["status"], expected)
            self.assertIsNone(result["expected_delivery"])

    def test_customer_payment_and_phone_data_are_not_exposed(self):
        result = api.normalize(parcel(PhoneRecipient="secret-phone", MarketplacePartnerToken="secret-token", CardMaskedNumber="secret-card"), "incoming")
        self.assertNotIn("secret", str(result))

    def test_bad_responses_do_not_become_empty_lists(self):
        for payload in ({"success": False}, {"success": True, "data": None}, {"success": True, "data": [{}]}, {"success": True, "data": [{"result": [{}]}]}):
            with self.assertRaises(api.ApiError):
                api.unpack(payload)
        self.assertEqual(api.unpack({"success": True, "data": [{"result": []}]}), [])
        with self.assertRaises(api.AuthenticationError):
            api.unpack({"success": False, "errors": ["API key expired"]})


class PaginationTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_supported_status_languages_have_a_shared_concurrency_limit(self):
        import asyncio
        client = api.NovaPoshtaApi(None, "test")
        active = maximum = calls = 0
        async def tracking(number, language="uk"):
            nonlocal active, maximum, calls
            active += 1; calls += 1; maximum = max(maximum, active)
            await asyncio.sleep(0)
            active -= 1
            return {"tracking":[{"event":"Arrival", "event_status":"now", "date":"2026-10-27T15:00:00Z", "event_name":language}]}
        client._tracking = tracking
        rows = [api.normalize(parcel(str(i)), "incoming") for i in range(3)]
        await client._enrich(rows)
        self.assertEqual(calls, 9)
        self.assertLessEqual(maximum, 4)
        self.assertTrue(all(set(row["status_details"]) == {"en","uk","ru"} for row in rows))

    async def test_primary_history_failure_uses_another_available_language(self):
        client = api.NovaPoshtaApi(None, "test")
        async def tracking(number, language="uk"):
            if language == "uk":
                raise api.ApiError("Unavailable")
            return {"tracking":[{"event":"Arrival", "event_status":"now", "date":"2026-10-27T15:00:00Z", "event_name":language}]}
        client._tracking = tracking
        row = api.normalize(parcel(), "incoming")
        await client._enrich([row])
        self.assertEqual(row["status_detail_language"], "en")
        self.assertEqual(set(row["status_details"]), {"en","ru"})

    async def test_short_pages_deduplication_and_pickup_first(self):
        client = api.NovaPoshtaApi(None, "test")
        calls = []

        async def page(method, props):
            calls.append((method, props["Page"]))
            if props["Page"] == "1":
                return [parcel(), parcel("22222222222222", "7")]
            if props["Page"] == "2":
                return [parcel("33333333333333", "9")]
            return []
        client._page = page
        async def tracking(number, language="uk"):
            return {"tracking": []}
        client._tracking = tracking
        rows = await client.parcels(datetime(2026, 10, 27))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["status"], "at_pickup_point")
        self.assertEqual(len(calls), 6)

    async def test_detail_failure_keeps_summary_without_old_detail(self):
        client = api.NovaPoshtaApi(None, "test")
        async def page(method, props):
            return [parcel(TrackingStatusName="У дорозі")] if props["Page"] == "1" else []
        async def tracking(number, language="uk"):
            raise api.ApiError("Unavailable")
        client._page = page
        client._tracking = tracking
        rows = await client.parcels(datetime(2026, 10, 27), direction="incoming")
        self.assertEqual(rows[0]["status_text"], "У дорозі")
        self.assertNotIn("status_detail", rows[0])

    async def test_repeated_pages_fail_instead_of_silently_truncating(self):
        client = api.NovaPoshtaApi(None, "test")
        async def page(*args):
            return [parcel()]
        client._page = page
        with self.assertRaises(api.ApiError):
            await client.parcels(datetime(2026, 10, 27), direction="incoming")

    async def test_direction_failure_does_not_return_partial_success(self):
        client = api.NovaPoshtaApi(None, "test")
        async def page(method, props):
            if "Outgoing" in method:
                raise api.ApiError("Unavailable")
            return [parcel()] if props["Page"] == "1" else []
        client._page = page
        with self.assertRaises(api.ApiError):
            await client.parcels(datetime(2026, 10, 27))


if __name__ == "__main__":
    unittest.main()
