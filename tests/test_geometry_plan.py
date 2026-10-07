import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from civtools.core.geometry import build_rack_plan, rack_size
from civtools.core.piperack import PipeRackGenerator


def configuration():
    return {"transverse_spacing": [0, 6], "longitudinal_spacing": [0, 8, 16, 24],
            "trans_beam_elevations": [3, 6], "long_beam_elevations": [3, 6],
            "base_elevation": 2, "foundation_depth": 1.5, "support_type": "Fixed", "bracing_enabled": True}


class RackPlanTests(unittest.TestCase):
    def test_absolute_elevations_and_size_match_plan(self):
        config = configuration()
        plan = build_rack_plan(config)
        self.assertEqual(set(y for x, y, z in plan.nodes), {.5, 2, 3, 6})
        self.assertEqual(len(plan.nodes), len(set(plan.nodes)))
        self.assertTrue(all(a != b for a, b, kind in plan.beams))
        self.assertEqual(rack_size(config), (len(plan.nodes), len(plan.beams), plan.com_calls))
        self.assertEqual(sum(kind == "brace" for a, b, kind in plan.beams), 8)

    def test_oversized_geometry_rejected_before_connecting(self):
        config = configuration()
        config.update(transverse_spacing=list(range(100)), longitudinal_spacing=list(range(100)),
                      trans_beam_elevations=list(range(3, 53)), long_beam_elevations=list(range(3, 53)))
        with patch("civtools.core.piperack.connect_staad") as connect:
            with self.assertRaisesRegex(ValueError, "Model too large"):
                PipeRackGenerator().create_comprehensive_pipe_rack(config)
            connect.assert_not_called()

    def test_nonempty_model_is_not_modified(self):
        staad = MagicMock()
        staad.Geometry.GetNodeCount.return_value = 3
        staad.Geometry.GetMemberCount.return_value = 2
        with patch("civtools.core.piperack.connect_staad", return_value=(staad, "test.std")):
            with self.assertRaisesRegex(RuntimeError, "blank STAAD model"):
                PipeRackGenerator().create_comprehensive_pipe_rack(configuration())
        staad.Geometry.AddNode.assert_not_called()
        staad.Geometry.AddBeam.assert_not_called()

    def test_execution_uses_exact_preview_plan(self):
        config = configuration()
        plan = build_rack_plan(config)
        staad = MagicMock()
        staad.Geometry.GetNodeCount.return_value = 0
        staad.Geometry.GetMemberCount.return_value = 0
        staad.Geometry.AddNode.side_effect = range(1, len(plan.nodes) + 1)
        staad.Geometry.AddBeam.side_effect = range(1, len(plan.beams) + 1)
        staad.Support.CreateSupportFixed.return_value = 1
        events = []
        with patch("civtools.core.piperack.connect_staad", return_value=(staad, "test.std")), patch("civtools.core.piperack.staad_model_name", return_value="test.std"):
            generator = PipeRackGenerator(lambda *event: events.append(event))
            self.assertTrue(generator.create_comprehensive_pipe_rack(config))
        self.assertEqual([call.args for call in staad.Geometry.AddNode.call_args_list], plan.nodes)
        self.assertEqual([call.args for call in staad.Geometry.AddBeam.call_args_list], [(a + 1, b + 1) for a, b, kind in plan.beams])
        self.assertEqual(staad.Support.AssignSupportToNode.call_count, len(plan.foundations))
        self.assertIn(("progress", 100), events)

    def test_support_failure_reports_partial_changes(self):
        staad = MagicMock()
        staad.Geometry.GetNodeCount.return_value = 0
        staad.Geometry.GetMemberCount.return_value = 0
        staad.Geometry.AddNode.return_value = 1
        staad.Geometry.AddBeam.return_value = 1
        staad.Support.CreateSupportFixed.return_value = 1
        staad.Support.AssignSupportToNode.side_effect = RuntimeError("Support failure")
        with patch("civtools.core.piperack.connect_staad", return_value=(staad, "test.std")), patch("civtools.core.piperack.staad_model_name", return_value="test.std"):
            with self.assertRaisesRegex(RuntimeError, "partial changes.*Support failure"):
                PipeRackGenerator().create_comprehensive_pipe_rack(configuration())


if __name__ == "__main__":
    unittest.main()
