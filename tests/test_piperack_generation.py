import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from civtools.piperack_generator import PipeRackGenerator


class FakeGeometry:
    def __init__(self):
        self.next_node = 1
        self.beams = []

    def AddNode(self, x, y, z):
        node_id = self.next_node
        self.next_node += 1
        return node_id

    def AddBeam(self, start_node, end_node):
        beam_id = len(self.beams) + 1
        self.beams.append((start_node, end_node))
        return beam_id


class PipeRackGenerationTests(unittest.TestCase):
    def test_bracing_uses_transverse_tier_grid_tags(self):
        generator = PipeRackGenerator()
        generator.geometry = FakeGeometry()
        generator.nodes = []
        generator.beams = []
        generator.beam_counter = 1

        generator._create_all_nodes(
            2,
            4,
            [0.0, 6.0],
            [0.0, 8.0, 16.0, 24.0],
            [3.0, 6.0],
            [],
            0.0,
            1.5,
        )
        generator._create_longitudinal_bracing_system(2, 4, [3.0, 6.0])

        brace_beams = [
            beam for beam in generator.beams
            if beam["type"] == "longitudinal_v_brace"
        ]
        self.assertEqual(len(brace_beams), 8)
        self.assertEqual(len(generator.geometry.beams), 8)

    def test_support_assignment_failure_is_not_reported_as_success(self):
        class FailingSupport:
            def CreateSupportFixed(self):
                return 1

            def AssignSupportToNode(self, node_id, support_id):
                if node_id == 2:
                    raise RuntimeError("support assignment failed")

        generator = PipeRackGenerator()
        generator.support = FailingSupport()
        generator.nodes = [
            {"staad_id": 1, "grid": [0, 0, -1]},
            {"staad_id": 2, "grid": [1, 0, -1]},
        ]

        with self.assertRaisesRegex(RuntimeError, "support assignment failed"):
            generator._assign_supports(2, 1, "Fixed")

    def test_shared_transverse_and_longitudinal_elevations_reuse_nodes(self):
        generator = PipeRackGenerator()
        generator.geometry = FakeGeometry()
        generator.nodes = []
        generator.beams = []
        generator.beam_counter = 1

        generator._create_all_nodes(
            2,
            2,
            [0.0, 6.0],
            [0.0, 8.0],
            [3.0],
            [3.0],
            0.0,
            1.5,
        )

        trans_node = generator._get_node_by_grid(0, 0, ("T", 0))
        long_node = generator._get_node_by_grid(0, 0, ("L", 0))
        self.assertEqual(trans_node["staad_id"], long_node["staad_id"])

        generator._create_columns(2, 2, [3.0], [3.0])
        self.assertTrue(
            all(start != end for start, end in generator.geometry.beams)
        )


if __name__ == "__main__":
    unittest.main()
