import csv
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from civtools.core.productivity_generators import (
    PipeRackConfig, ProductivityPebConfig, PlateGirder,
    build_pipe_rack_plan, pipe_rack_commands, build_productivity_peb_plan, peb_commands,
    predefined_plate_girders, plate_girder_catalogue, load_combination_data,
    load_combination_template, load_combination_report,
)


class GeometryGeneratorTests(unittest.TestCase):
    def assert_connected(self, plan):
        self.assertEqual(len(set(plan.nodes)), len(plan.nodes))
        edges = [tuple(sorted((a, b))) for a, b, _ in plan.beams]
        self.assertEqual(len(edges), len(set(edges)))
        seen = {0}
        while True:
            reached = seen | {end for a, b in edges for start, end in ((a, b), (b, a)) if start in seen}
            if reached == seen:
                break
            seen = reached
        self.assertEqual(len(seen), len(plan.nodes))

    def test_rack_merges_intermediate_levels_and_exports_units(self):
        config = PipeRackConfig(width=9, frames=3, frame_spacing=5,
                                tier_spacings='4,3', longitudinal_spacings='2,3,2')
        plan = build_pipe_rack_plan(config)
        self.assert_connected(plan)
        self.assertEqual(sorted({p[1] for p in plan.nodes}), [0, 2, 4, 5, 7])
        self.assertEqual(len(plan.foundations), 6)
        for unit, command in [('METER', 'UNIT METER KN'), ('INCHES', 'UNIT INCHES KIP'), ('FEET', 'UNIT FEET KIP')]:
            self.assertIn(command, pipe_rack_commands(replace(config, unit=unit)))
            self.assertEqual(build_pipe_rack_plan(replace(config, unit=unit)).nodes, plan.nodes)

    def test_rack_rejects_inconsistent_or_excessive_geometry(self):
        for changes in ({'longitudinal_spacings': '3'}, {'frames': 1}, {'frames': 501},
                        {'width': float('nan')}, {'tier_spacings': '1,,2'}, {'unit': 'CM'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                build_pipe_rack_plan(replace(PipeRackConfig(), **changes))

    def test_all_peb_variants_have_connected_geometry_and_expected_columns(self):
        for variant, columns in [('A', 2), ('B', 3), ('C', 4), ('D', 2)]:
            with self.subTest(variant=variant):
                config = ProductivityPebConfig(variant=variant, frames=3)
                plan = build_productivity_peb_plan(config)
                self.assert_connected(plan)
                self.assertEqual(len(plan.foundations), columns * 3)
                self.assertAlmostEqual(max(y for _, y, _ in plan.nodes), 9)
                if variant == 'D':
                    self.assertIn((20., 9., 0.), plan.nodes)
                else:
                    self.assertIn((10., 9., 0.), plan.nodes)

    def test_peb_english_units_and_slope(self):
        for unit in ('INCHES', 'FEET', 'English (in)'):
            config = ProductivityPebConfig(width=480, eave_height=120, ridge_height=180,
                                           roof_slope=4, unit=unit, frames=2,
                                           tie_spacing=40, purlin_spacing=40)
            plan = build_productivity_peb_plan(config)
            self.assertAlmostEqual(max(y for _, y, _ in plan.nodes), 180)
            self.assertIn('UNIT FEET KIP' if unit == 'FEET' else 'UNIT INCHES KIP', peb_commands(config))

    def test_peb_optional_ties_purlins_and_braces(self):
        config = ProductivityPebConfig(frames=2, lateral_bracing=True, add_purlins=False)
        plan = build_productivity_peb_plan(config)
        self.assert_connected(plan)
        kinds = [kind for _, _, kind in plan.beams]
        self.assertNotIn('purlin', kinds)
        self.assertIn('tie', kinds)
        self.assertEqual(kinds.count('vertical_brace'), 4)
        self.assertEqual(kinds.count('roof_brace'), 4)
        for x in (0., 20.):
            a, b = plan.nodes.index((x, 6., 0.)), plan.nodes.index((x, 6., 6.))
            self.assertTrue(any({start, end} == {a, b} and kind == 'tie' for start, end, kind in plan.beams))
        untied = build_productivity_peb_plan(replace(config, add_ties=False))
        self.assertNotIn('tie', {kind for _, _, kind in untied.beams})

    def test_peb_tiny_spacing_fails_before_large_allocation(self):
        with self.assertRaises(ValueError):
            build_productivity_peb_plan(ProductivityPebConfig(purlin_spacing=1e-20))


class PlateGirderTests(unittest.TestCase):
    def test_rectangle_properties_match_known_500_mm_section(self):
        section = PlateGirder('PG500', 500, 200, 25, 16)
        properties = section.properties()
        self.assertAlmostEqual(properties[0], .0172)
        self.assertAlmostEqual(properties[5], .0006860833333333334)
        self.assertAlmostEqual(properties[6], 3.3486933333333335e-05)
        self.assertAlmostEqual(properties[7], 2.697733333333334e-06)
        self.assertAlmostEqual(properties[8], .008)
        self.assertAlmostEqual(properties[9], .006666666666666667)

    def test_catalogue_is_a_complete_staad_user_table(self):
        sections = predefined_plate_girders()
        self.assertGreater(len(sections), 100)
        self.assertEqual(len(sections), len({s.name for s in sections}))
        text = plate_girder_catalogue()
        self.assertIn('START USER TABLE\nTABLE 1\nUNIT METER KN\nWIDE FLANGE', text)
        self.assertTrue(text.endswith('END\n'))
        self.assertTrue(all(len(line) <= 79 for line in text.splitlines()))
        self.assertIn('PG1500X500X40X25', text)
        self.assertTrue(all(all(v > 0 for v in section.properties()) for section in sections))

    def test_bad_dimensions_duplicate_names_and_command_injection_fail(self):
        for section in (PlateGirder('BAD;FINISH', 500, 200, 25, 16),
                        PlateGirder('BAD', 40, 200, 25, 16),
                        PlateGirder('BAD', 500, 10, 25, 16)):
            with self.assertRaises(ValueError):
                plate_girder_catalogue([section])
        section = PlateGirder('PG1', 500, 200, 25, 16)
        with self.assertRaises(ValueError):
            plate_girder_catalogue([section, section])


class LoadCombinationGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def write_matrix(self, rows):
        source = self.directory / 'matrix.csv'
        with source.open('w', encoding='utf-8', newline='') as stream:
            csv.writer(stream).writerows(rows)
        return source

    def matrix(self):
        return [('LOAD COMBINATIONS FOR STAAD.Pro',), ('LOAD COMB NO', 7, 12, 24),
                ('', 'DL', 'LL', 'WX'), ('', 'Dead', 'Live', 'Wind'),
                (101, 1.2, 1.5, -.9), (105, 1, 0, 0)]

    def test_matrix_preserves_ids_symbols_types_and_signed_factors(self):
        data = load_combination_data(self.write_matrix(self.matrix()))
        self.assertEqual([(c.number, c.symbol, c.load_type) for c in data.cases],
                         [(7, 'DL', 'Dead'), (12, 'LL', 'Live'), (24, 'WX', 'Wind')])
        self.assertIn('LOAD 24 LOADTYPE Wind TITLE WX', data.case_script)
        self.assertIn('LOAD COMB 101 1.2DL + 1.5LL + -0.9WX', data.combination_script)
        self.assertIn('7 1.2 12 1.5 24 -0.9', data.combination_script)

    def test_real_docx_has_both_scripts_and_formatted_tables(self):
        output = self.directory / 'report.docx'
        result = load_combination_report(self.write_matrix(self.matrix()), output)
        self.assertEqual(result, output)
        with ZipFile(output) as archive:
            for name in archive.namelist():
                ET.fromstring(archive.read(name))
            document = ET.fromstring(archive.read('word/document.xml'))
            namespace = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            text = '\n'.join(n.text or '' for n in document.findall('.//w:t', namespace))
            self.assertIn('LOAD 7 LOADTYPE Dead TITLE DL', text)
            self.assertIn('LOAD COMB 101', text)
            self.assertIn('1.2DL + 1.5LL + -0.9WX', text)
            self.assertEqual(len(document.findall('.//w:tbl', namespace)), 2)
            self.assertEqual(len(document.findall('.//w:tblHeader', namespace)), 2)

    def test_template_round_trip_needs_no_office_installation(self):
        source = load_combination_template(self.directory / 'template.xlsx')
        data = load_combination_data(source)
        self.assertEqual([case.symbol for case in data.cases], ['DL', 'LL'])
        self.assertIn('LOAD COMB 101', data.combination_script)

    def test_wide_matrix_preserves_full_expression_and_splits_tables(self):
        rows = [('LOAD COMBINATIONS',), ('LOAD COMB NO', *range(1, 51)),
                ('', *[f'L{i}' for i in range(1, 51)]), ('', *['Dead'] * 50), (101, *[1.2] * 50)]
        source = self.write_matrix(rows)
        data = load_combination_data(source)
        self.assertEqual(len(data.cases), 50)
        self.assertIn('1.2L50', data.contributions[0][1])
        self.assertIn('LOAD COMB 101 Combination 101', data.combination_script)
        output = load_combination_report(source, self.directory / 'wide.docx')
        with ZipFile(output) as archive:
            document = ET.fromstring(archive.read('word/document.xml'))
            self.assertEqual(len(document.findall('.//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tbl')), 8)

    def test_long_form_csv_retains_optional_case_metadata(self):
        source = self.write_matrix([('combination', 'title', 'case', 'factor', 'symbol', 'load_type'),
                                    (101, 'Ultimate', 7, 1.5, 'DL', 'Dead'),
                                    (101, 'Ultimate', 12, -1., 'WX', 'Wind')])
        data = load_combination_data(source)
        self.assertIn('LOAD 12 LOADTYPE Wind TITLE WX', data.case_script)
        self.assertIn('7 1.5 12 -1', data.combination_script)

    def test_invalid_matrix_rejected_without_creating_report(self):
        invalid = []
        rows = self.matrix()
        invalid.append(rows[:4] + [(7, 1, 1, 0)])
        invalid.append(rows[:4] + [(101, 0, 0, 0)])
        invalid.append(rows[:4] + [(101, 1, 0, 0), (101, 0, 1, 0)])
        invalid.append([rows[0], ('LOAD COMB NO', 7, 7, 24), *rows[2:]])
        invalid.append([*rows[:3], ('', 'Unknown', 'Live', 'Wind'), *rows[4:]])
        invalid.append([*rows[:4], (101, '=1+2', 0, 0)])
        for rows in invalid:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                load_combination_report(self.write_matrix(rows), self.directory / 'bad.docx')
            self.assertFalse((self.directory / 'bad.docx').exists())


if __name__ == '__main__':
    unittest.main()
