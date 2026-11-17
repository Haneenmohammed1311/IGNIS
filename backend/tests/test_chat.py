from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fastapi import HTTPException

from app import catalog, main
from app.ai_chat import ChatUpstreamError, validate_output
from app.chat_evidence import gather_analytical_facts
from app.rag_knowledge import retrieve
from .fixtures import release


class ChatTests(TestCase):
    def setUp(self):
        main.CHAT_CALL_TIMES.clear()

    def tearDown(self):
        main.CHAT_CALL_TIMES.clear()

    def test_summary_evidence_is_sequential_and_marks_missing_releases(self):
        call_order = []

        def analytical(kind, filters):
            call_order.append((filters.country, filters.year, filters.sensor))
            return {"metrics": {"detections": 12, "linked": 8, "unresolved": 3,
                                 "outside_scope": 1, "modis": 12,
                                 "mean_frp": 4.5, "frp_n": 2}}

        comparison_order = []

        def compare(filters):
            comparison_order.append(filters.country)
            return [{
                "year": year,
                "available": main.releases.get((filters.country, year), {}).get("status") == "ready",
                "total": 10 + year - 2020 if filters.country == "BR" else None,
            } for year in filters.years]

        with patch.object(main, "releases", {
            ("BR", 2020): {"status": "ready"},
            ("BR", 2021): {"status": "ready"},
        }), patch.object(main, "analytical", side_effect=analytical), patch.object(
            main, "compare", side_effect=compare,
        ) as compare_mock:
            result = gather_analytical_facts({
                "countries": ["BR", "AU"], "years": [2020, 2021],
                "sensor": "MODIS", "needs_analytics": True,
            })

        self.assertEqual(call_order, [
            ("BR", 2020, None), ("BR", 2020, "MODIS"),
            ("BR", 2021, None), ("BR", 2021, "MODIS"),
        ])
        self.assertEqual(compare_mock.call_count, 2)
        self.assertEqual(comparison_order, ["BR", "AU"])
        self.assertEqual(result["facts"]["BR.2020.overview.MODIS"]["metrics"]["mean_frp"], 4.5)
        self.assertEqual(result["facts"]["BR.2021.comparison"]["total_detections"], 11)
        self.assertEqual(result["facts"]["AU.2020.overview.MODIS"]["status"], "unavailable")

    def test_knowledge_retrieval_cites_relevant_markdown_heading(self):
        hits = retrieve("MODIS and VIIRS swath widths and equatorial orbit coverage gaps")
        self.assertTrue(hits)
        self.assertEqual(hits[0]["id"], "nasa_firms_knowledge#3_satellite")

    def test_chat_reads_sensor_frp_from_preaggregated_overview(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            data, runtime = root / "data", root / "runtime"
            with patch.multiple(catalog, DATA=data, RUNTIME=runtime):
                runtime.mkdir(parents=True)
                folder = release(data)
                prepared = catalog.prepare_release("AU", 2024, folder)
                main.analytics_cached.cache_clear()
                with patch.object(main, "releases", {("AU", 2024): prepared}):
                    result = gather_analytical_facts({
                        "countries": ["AU"], "years": [2024], "sensor": "MODIS",
                        "needs_analytics": True,
                    })
        metrics = result["facts"]["AU.2024.overview.MODIS"]["metrics"]
        self.assertEqual(metrics["detections"], 1)
        self.assertEqual(metrics["mean_frp"], 5.0)
        self.assertEqual(metrics["frp_n"], 1)

    def test_chat_rejects_inconsistent_tracking_accounting(self):
        with patch.object(main, "releases", {("AU", 2024): {"status": "ready"}}), patch.object(
            main, "analytical", return_value={"metrics": {
                "detections": 10, "linked": 5, "unresolved": 2, "outside_scope": 2,
            }},
        ):
            with self.assertRaisesRegex(ValueError, "do not reconcile"):
                gather_analytical_facts({
                    "countries": ["AU"], "years": [2024], "needs_analytics": True,
                })

    def test_output_rejects_unknown_citations_and_falls_back_for_missing_data(self):
        state = {
            "route": {"needs_analytics": True},
            "analytical_facts": {
                "BR.2020.overview": {"status": "unavailable", "country": "Brazil", "year": 2020},
            },
            "knowledge_chunks": [],
            "scope_notes": [],
            "generated": {
                "answer": "There were 100 detections.",
                "analytical_citations": ["not-a-real-fact"],
                "knowledge_citations": ["not-a-real-section"],
                "suggested_questions": [],
            },
        }
        result = validate_output(state)["result"]
        self.assertIn("no validated release", result["answer"])
        self.assertEqual(result["analytical_citations"], [])
        self.assertEqual(result["knowledge_citations"], [])

    def test_output_strips_unknown_inline_source_tags(self):
        state = {
            "route": {"needs_analytics": True},
            "analytical_facts": {"AU.2024.overview": {"status": "available"}},
            "knowledge_chunks": [],
            "scope_notes": [],
            "generated": {
                "answer": "Evidence [AU.2024.overview] and invented [BR.2020.overview].",
                "analytical_citations": ["AU.2024.overview"],
                "knowledge_citations": [],
                "suggested_questions": [],
            },
        }
        answer = validate_output(state)["result"]["answer"]
        self.assertIn("[AU.2024.overview]", answer)
        self.assertNotIn("[BR.2020.overview]", answer)

    def test_chat_endpoint_maps_upstream_errors_to_502(self):
        payload = main.ChatRequest(message="Question", current_filters=main.Filters(country="BR", year=2020))
        with patch.object(main, "run_chat", side_effect=ChatUpstreamError("upstream failed")):
            with self.assertRaises(HTTPException) as raised:
                main.chat_endpoint(payload)
        self.assertEqual(raised.exception.status_code, 502)
