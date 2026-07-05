import unittest

from Data.fetch_data import add_ranking_population_totals


class EmployeeOrgTotalsTest(unittest.TestCase):
    def test_counts_unique_people_in_province_and_business_department(self):
        person = {
            "job_id": "001",
            "province": "浙西省区",
            "business_department": "城市焕新事业部",
        }
        configs = [
            {"job_id": "001", "province": "浙西省区", "business_department": "城市焕新事业部"},
            {"job_id": "002", "province": "浙西省区", "business_department": "城市焕新事业部"},
            {"job_id": "002", "province": "浙西省区", "business_department": "城市焕新事业部"},
            {"job_id": "003", "province": "浙东省区", "business_department": "城市焕新事业部"},
        ]

        enriched = add_ranking_population_totals(person, configs)

        self.assertEqual(enriched["province_ranking_total"], 2)
        self.assertEqual(enriched["business_ranking_total"], 3)

    def test_leaves_totals_absent_when_organization_is_missing(self):
        enriched = add_ranking_population_totals({"job_id": "001"}, [])

        self.assertNotIn("province_ranking_total", enriched)
        self.assertNotIn("business_ranking_total", enriched)


if __name__ == "__main__":
    unittest.main()
