import json
import unittest

from src.discover import parse_overpass, patterns_for, vendor_from_element, find_vendors


OSM_FIXTURE = {
    "elements": [
        {
            "type": "node",
            "id": 1,
            "lat": 32.78,
            "lon": -96.8,
            "tags": {
                "name": "Metro Mechanical HVAC",
                "phone": "+1 214 555 0142",
                "website": "https://metro.example",
                "addr:housenumber": "100",
                "addr:street": "Main St",
                "addr:city": "Dallas",
                "addr:state": "TX",
            },
        },
        {
            "type": "way",
            "id": 2,
            "center": {"lat": 32.79, "lon": -96.81},
            "tags": {
                "name": "NorthStar Heating",
                "contact:phone": "+1 972 555 0198",
                "email": "service@northstar.example",
            },
        },
        {"type": "node", "id": 3, "lat": 32.7, "lon": -96.7, "tags": {"amenity": "cafe"}},
        {
            "type": "node",
            "id": 1,
            "lat": 32.78,
            "lon": -96.8,
            "tags": {"name": "Metro Mechanical HVAC"},
        },
    ]
}


class DiscoverTests(unittest.TestCase):
    def test_hvac_pattern(self):
        self.assertIn("hvac", patterns_for("HVAC"))

    def test_parse_skips_nameless_and_duplicates(self):
        vendors = parse_overpass(OSM_FIXTURE, 10)
        self.assertEqual(len(vendors), 2)
        self.assertEqual(vendors[0]["name"], "Metro Mechanical HVAC")
        self.assertEqual(vendors[0]["phone"], "+1 214 555 0142")
        self.assertEqual(vendors[0]["address"], "100 Main St, Dallas, TX")
        self.assertEqual(vendors[1]["email"], "service@northstar.example")
        self.assertTrue(vendors[0]["source"].endswith("/node/1"))

    def test_vendor_without_name_is_dropped(self):
        self.assertIsNone(vendor_from_element({"type": "node", "id": 9, "tags": {}}))

    def test_find_vendors_uses_injected_io(self):
        def geocode(_city):
            return {"lat": 32.78, "lon": -96.8, "display_name": "Dallas, Texas, USA"}

        def search(_trade, _city, _limit):
            return [
                {
                    "osm_type": "node",
                    "osm_id": 1,
                    "lat": "32.78",
                    "lon": "-96.8",
                    "name": "Metro Mechanical HVAC",
                    "display_name": "Metro Mechanical HVAC, Dallas, TX",
                    "class": "craft",
                    "extratags": {"phone": "+1 214 555 0142", "website": "https://metro.example"},
                    "address": {
                        "house_number": "100",
                        "road": "Main St",
                        "city": "Dallas",
                        "state": "TX",
                    },
                }
            ]

        def lookup(_ids):
            return {}

        result = find_vendors("HVAC", "Dallas, TX", geocode=geocode, search=search, lookup=lookup)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["provider"], "openstreetmap-nominatim")
        self.assertEqual(result["vendors"][0]["name"], "Metro Mechanical HVAC")
        self.assertEqual(result["vendors"][0]["phone"], "+1 214 555 0142")

    def test_requires_trade_and_city(self):
        with self.assertRaises(ValueError):
            find_vendors("", "Dallas, TX")


if __name__ == "__main__":
    unittest.main()
