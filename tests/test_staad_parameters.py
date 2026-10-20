import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from civtools.core.staad_parameters import (
    Member,
    Parameter,
    StaadService,
    STEEL_PARAMETERS,
)
from civtools.jobs import GeneratedParameterCommands, run_staad_parameter_generation


class StaadParameterGenerationTests(unittest.TestCase):
    def test_default_strength_parameters_have_separate_scopes_and_values(self):
        fyld_parameters = [
            parameter
            for parameter in STEEL_PARAMETERS
            if parameter.name.startswith(("FYLD", "FU"))
        ]

        self.assertEqual(
            [
                (parameter.name, parameter.value, parameter.scope)
                for parameter in fyld_parameters
            ],
            [
                (
                    "FYLD",
                    355000.0,
                    "Steel beams except channels and angles",
                ),
                (
                    "FYLD (CHANNELS AND ANGLES)",
                    250000.0,
                    "Channel and angle steel beams",
                ),
                (
                    "FU",
                    490000.0,
                    "Steel beams except channels and angles",
                ),
                (
                    "FU (CHANNELS AND ANGLES)",
                    410000.0,
                    "Channel and angle steel beams",
                ),
            ],
        )

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

    def test_beam_1_includes_all_steel_members(self):
        members = [
            Member(3, 1, 2, 5.0, "W36X925", "STEEL", False, True, False, True, False),
            Member(4, 2, 3, 5.0, "C8X11.5", "STEEL", False, True, False, False, True),
            Member(5, 3, 4, 5.0, "RECT", "CONCRETE", True, False, False, True, False),
            Member(6, 4, 5, 5.0, "W36X925", "STEEL", False, True, True, False, False),
        ]
        with patch("civtools.core.staad_parameters.StaadService") as service_type:
            service = service_type.return_value
            service.load_model.return_value = members
            service.members = members
            service.model_path = "model.std"

            result = run_staad_parameter_generation(
                "steel",
                [Parameter(True, "BEAM", 1.0, "All steel", "Beam design parameter")],
                lambda kind, value: None,
            )

        self.assertEqual(result.text, "BEAM 1 MEMB 3 4 6\n")

    def test_tmain_includes_only_steel_beams_and_columns(self):
        members = [
            Member(1, 1, 2, 5.0, "W", "STEEL", False, True, False, True, False),
            Member(2, 2, 3, 5.0, "W", "STEEL", False, True, False, False, True),
            Member(3, 3, 4, 5.0, "W", "STEEL", False, True, True, False, False),
            Member(4, 4, 5, 5.0, "W", "STEEL", False, True, False, False, False),
            Member(5, 5, 6, 5.0, "RECT", "CONCRETE", True, False, False, True, False),
        ]
        with patch("civtools.core.staad_parameters.StaadService") as service_type:
            service = service_type.return_value
            service.load_model.return_value = members
            service.members = members
            service.model_path = "model.std"

            result = run_staad_parameter_generation(
                "steel",
                [Parameter(True, "TMAIN", 250.0, "All steel beams and columns", "Main reinforcement")],
                lambda kind, value: None,
            )

        self.assertEqual(result.text, "TMAIN 250 MEMB 1 TO 3\n")

    def test_main_includes_only_steel_plan_braces(self):
        members = [
            Member(1, 1, 2, 5.0, "W", "STEEL", False, True, False, True, False),
            Member(2, 2, 3, 5.0, "W", "STEEL", False, True, False, False, True),
            Member(3, 3, 4, 5.0, "W", "STEEL", False, True, True, False, False),
            Member(4, 4, 5, 5.0, "W", "STEEL", False, True, False, False, False, plan_brace=True),
            Member(5, 5, 6, 5.0, "W", "STEEL", False, True, False, False, False),
            Member(6, 6, 7, 5.0, "RECT", "CONCRETE", True, False, False, False, False, plan_brace=True),
        ]
        with patch("civtools.core.staad_parameters.StaadService") as service_type:
            service = service_type.return_value
            service.load_model.return_value = members
            service.members = members
            service.model_path = "model.std"

            result = run_staad_parameter_generation(
                "steel",
                [Parameter(True, "MAIN", 250.0, "All steel plan braces", "Main reinforcement")],
                lambda kind, value: None,
            )

        self.assertEqual(result.text, "MAIN 250 MEMB 4\n")

    def test_stp_column_brace_and_lateral_parameters_use_their_scopes(self):
        members = [
            Member(1, 1, 2, 5.0, "W", "STEEL", False, True, False, True, False),
            Member(2, 2, 3, 5.0, "W", "STEEL", False, True, False, False, True),
            Member(3, 3, 4, 5.0, "W", "STEEL", False, True, True, False, False),
            Member(4, 4, 5, 5.0, "W", "STEEL", False, True, False, False, False, plan_brace=True),
            Member(5, 5, 6, 5.0, "W", "STEEL", False, True, False, False, False),
            Member(6, 6, 7, 5.0, "RECT", "CONCRETE", True, False, False, True, False),
        ]
        with patch("civtools.core.staad_parameters.StaadService") as service_type:
            service = service_type.return_value
            service.load_model.return_value = members
            service.members = members
            service.model_path = "model.std"

            result = run_staad_parameter_generation(
                "steel",
                [
                    Parameter(True, "STP", 1.0, "All steel", "Steel parameter"),
                    Parameter(True, "IMM", 1.0, "All steel columns", "Column parameter"),
                    Parameter(True, "CMX", 0.9, "All steel columns", "Column parameter"),
                    Parameter(True, "CMZ", 0.9, "All steel columns", "Column parameter"),
                    Parameter(True, "NSF", 1.0, "All steel braces", "Brace parameter"),
                    Parameter(True, "LAT", 1.0, "Steel beams except columns and braces", "Beam parameter"),
                ],
                lambda kind, value: None,
            )

        self.assertEqual(
            result.text,
            "STP 1 MEMB 1 TO 5\n\n"
            "IMM 1 MEMB 3\n\n"
            "CMX 0.9 MEMB 3\n\n"
            "CMZ 0.9 MEMB 3\n\n"
            "NSF 1 MEMB 4 5\n\n"
            "LAT 1 MEMB 1 2\n",
        )

    def test_load_model_classifies_only_horizontal_diagonal_plan_braces(self):
        service = StaadService()
        service.os = MagicMock()
        service.os.Geometry.GetBeamList.return_value = [1, 2, 3]
        service.os.Geometry.GetMemberIncidence.side_effect = [(1, 2), (3, 4), (5, 6)]
        service.os.Geometry.GetNodeCoordinates.side_effect = {
            1: (0.0, 0.0, 0.0),
            2: (3.0, 0.0, 4.0),
            3: (0.0, 0.0, 0.0),
            4: (3.0, 2.0, 4.0),
            5: (0.0, 0.0, 0.0),
            6: (3.0, 0.0, 0.0),
        }.__getitem__
        service.os.Property.GetBeamSectionName.return_value = "W"
        service.os.Property.GetBeamMaterialName.return_value = "STEEL"

        with patch.object(service, "connect"):
            members = service.load_model(0.10)

        self.assertEqual([member.plan_brace for member in members], [True, False, False])

    def test_fyld_includes_only_non_channel_angle_steel_beams(self):
        members = [
            Member(
                1, 1, 2, 5.0, "W36X925", "STEEL", False, True, False, True,
                False, 610,
            ),
            Member(
                2, 2, 3, 5.0, "C8X11.5", "STEEL", False, True, False, True,
                False, 630,
            ),
            Member(
                3, 3, 4, 5.0, "L20205", "STEEL", False, True, False, False,
                True, 640,
            ),
            Member(
                4, 4, 5, 5.0, "W36X925", "STEEL", False, True, True, False,
                False, 610,
            ),
            Member(
                5, 5, 6, 5.0, "W36X925", "STEEL", False, True, False, False,
                True, 610,
            ),
            Member(
                6, 6, 7, 5.0, "ISMC100", "STEEL", False, True, False, True,
                False, 635,
            ),
            Member(
                7, 7, 8, 5.0, "ISA50X50X6", "STEEL", False, True, False,
                False, True, 645,
            ),
            Member(
                8, 8, 9, 5.0, "C10X20", "STEEL", False, True, False, True,
                False,
            ),
            Member(
                9, 9, 10, 5.0, "L40404", "STEEL", False, True, False,
                False, True,
            ),
            Member(
                10, 10, 11, 5.0, "W36X925", "STEEL", False, False, False,
                True, False, 610,
            ),
        ]
        with patch("civtools.core.staad_parameters.StaadService") as service_type:
            service = service_type.return_value
            service.load_model.return_value = members
            service.members = members
            service.model_path = "model.std"

            result = run_staad_parameter_generation(
                "steel",
                [Parameter(True, "FYLD", 355000.0, "All steel", "Yield strength")],
                lambda kind, value: None,
            )

        self.assertEqual(result.text, "FYLD 355000 MEMB 1 5\n")
        service.load_model.assert_called_once_with(
            0.10,
            False,
            include_section_types=True,
        )

    def test_channel_angle_fyld_parameter_uses_its_value_and_scope(self):
        members = [
            Member(
                1, 1, 2, 5.0, "W36X925", "STEEL", False, True, False, True,
                False, 610,
            ),
            Member(
                2, 2, 3, 5.0, "C8X11.5", "STEEL", False, True, False, True,
                False, 630,
            ),
            Member(
                3, 3, 4, 5.0, "L20205", "STEEL", False, True, False, False,
                True, 640,
            ),
            Member(
                4, 4, 5, 5.0, "W36X925", "STEEL", False, True, True, False,
                False, 610,
            ),
        ]
        with patch("civtools.core.staad_parameters.StaadService") as service_type:
            service = service_type.return_value
            service.load_model.return_value = members
            service.members = members
            service.model_path = "model.std"

            result = run_staad_parameter_generation(
                "steel",
                [
                    Parameter(
                        True,
                        "FYLD",
                        355000.0,
                        "Steel beams except channels and angles",
                        "Yield strength",
                    ),
                    Parameter(
                        True,
                        "FYLD (CHANNELS AND ANGLES)",
                        250000.0,
                        "Channel and angle steel beams",
                        "Yield strength",
                    ),
                    Parameter(
                        True,
                        "FU",
                        490000.0,
                        "Steel beams except channels and angles",
                        "Ultimate strength",
                    ),
                    Parameter(
                        True,
                        "FU (CHANNELS AND ANGLES)",
                        410000.0,
                        "Channel and angle steel beams",
                        "Ultimate strength",
                    ),
                ],
                lambda kind, value: None,
            )

        self.assertEqual(
            result.text,
            "FYLD 355000 MEMB 1\n\n"
            "FYLD 250000 MEMB 2 3\n\n"
            "FU 490000 MEMB 1\n\n"
            "FU 410000 MEMB 2 3\n",
        )

    def test_load_model_reads_openstaad_section_type_as_integer(self):
        service = StaadService()
        service.os = MagicMock()
        service.os.Geometry.GetBeamList.return_value = [7]
        service.os.Geometry.GetMemberIncidence.return_value = (1, 2)
        service.os.Geometry.GetNodeCoordinates.side_effect = {
            1: (0.0, 0.0, 0.0),
            2: (5.0, 0.0, 0.0),
        }.__getitem__
        service.os.Property.GetBeamSectionName.return_value = "W36X925"
        service.os.Property.GetBeamMaterialName.return_value = "STEEL"
        service.os.Property.GetBeamSectionPropertyTypeNo.return_value = 610

        with patch.object(service, "connect"):
            members = service.load_model(0.10, include_section_types=True)

        self.assertEqual(members[0].section_type, 610)
        service.os.Property.GetBeamSectionPropertyTypeNo.assert_called_once_with(7)


if __name__ == "__main__":
    unittest.main()
