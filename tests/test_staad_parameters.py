import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from civtools.core.staad_parameters import Member, Parameter
from civtools.jobs import GeneratedParameterCommands, run_staad_parameter_generation


class StaadParameterGenerationTests(unittest.TestCase):
    def test_worker_generates_concrete_commands_and_reports_model(self):
        member = Member(
            1, 1, 2, 5.0, "RECT", "CONCRETE", True, False,
            False, True, False,
        )
        with patch("civtools.core.staad_parameters.StaadService") as service_type:
            service = service_type.return_value
            service.load_model.return_value = [member]
            service.members = [member]
            service.model_path = "model.std"
            events = []

            result = run_staad_parameter_generation(
                "concrete",
                [Parameter(True, "FC", 30.0, "All concrete", "Strength")],
                lambda kind, value: events.append((kind, value)),
            )

        self.assertIsInstance(result, GeneratedParameterCommands)
        self.assertEqual(result.text, "FC 30000 MEMB 1\n")
        self.assertEqual(result.model_path, "model.std")
        self.assertEqual(result.member_count, 1)
        self.assertEqual(result.warning_count, 0)
        self.assertEqual(events[0][0], "stage")

    def test_steel_generator_includes_detected_member_ids(self):
        member = Member(
            14, 1, 2, 5.0, "I", "STEEL", False, True,
            False, True, False,
        )
        with patch("civtools.core.staad_parameters.StaadService") as service_type:
            service = service_type.return_value
            service.load_model.return_value = [member]
            service.members = [member]
            service.model_path = "model.std"
            result = run_staad_parameter_generation(
                "steel",
                [Parameter(True, "CHECK CODE", None, "All steel", "Check")],
                lambda kind, value: None,
            )

        self.assertEqual(result.text, "CHECK CODE MEMB 14\n")


if __name__ == "__main__":
    unittest.main()
