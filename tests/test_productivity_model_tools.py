"""Behavioral cases from the Dezign Link guide, using fake OpenSTAAD only."""
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from civtools.core.staad_productivity import ModelSnapshot, classify_members, renumber_steps
from civtools.core import productivity_model_tools as tools


def frame():
    # Split primary beams, reverse incidence on the last segment; a secondary
    # beam is split by a tertiary framing into its middle.
    return ModelSnapshot('test.std', 'Metric',
        {1: (0, 0, 0), 2: (0, 3, 0), 3: (4, 3, 0), 4: (8, 3, 0),
         5: (8, 0, 0), 6: (0, 0, 8), 7: (0, 3, 8), 8: (4, 3, 8),
         9: (8, 3, 8), 10: (8, 0, 8), 11: (4, 3, 4),
         12: (6, 3, 4), 13: (6, 3, 0)},
        {1: (1, 2), 2: (5, 4), 3: (6, 7), 4: (10, 9),
         10: (2, 3), 11: (13, 3), 12: (4, 13), 20: (7, 8), 21: (9, 8),
         30: (3, 11), 31: (8, 11), 40: (11, 12)}, [1, 5, 6, 10])


class FloorRenumberTests(unittest.TestCase):
    def test_documented_number_bands_and_incidence_independent_order(self):
        model = frame()
        mapping = tools.floor_renumber_plan(model)
        categories = classify_members(model)
        self.assertEqual(min(mapping[mid] for mid in mapping if categories[mid] == 'Columns'), 1501)
        self.assertEqual(min(mapping[mid] for mid in mapping if 'beams' in categories[mid]), 1001)
        self.assertEqual(len(mapping), len(set(mapping.values())))
        self.assertEqual(set(mapping), set(model.members))
        model.members = {mid: tuple(reversed(ends)) for mid, ends in reversed(list(model.members.items()))}
        self.assertEqual(tools.floor_renumber_plan(model), mapping)
        self.assertTrue(renumber_steps(mapping))

    def test_saved_sparse_classification_overrides_are_applied(self):
        model = frame()
        model.classifications = {40: 'Plan diagonals'}
        self.assertEqual(tools._categories(model)[40], 'Plan diagonals')
        self.assertEqual(tools._categories(model)[1], 'Columns')
        self.assertGreaterEqual(tools.floor_renumber_plan(model)[40], 1751)

    def test_ascending_floor_blocks_and_small_blocks(self):
        model = ModelSnapshot('test.std', 'Metric',
            {1: (0, 0, 0), 2: (0, 3, 0), 3: (0, 6, 0),
             4: (4, 0, 0), 5: (4, 3, 0), 6: (4, 6, 0)},
            {1: (1, 2), 2: (2, 3), 3: (4, 5), 4: (5, 6), 5: (2, 5), 6: (3, 6)}, [1, 4])
        mapping = tools.floor_renumber_plan(model)
        self.assertEqual(mapping[5], 1001)
        self.assertEqual(mapping[6], 2001)
        self.assertEqual(mapping[1], 1501)
        self.assertEqual(mapping[2], 2501)
        self.assertEqual(tools.floor_renumber_plan(model, 100)[5], 101)
        with self.assertRaises(ValueError):
            tools.floor_renumber_plan(model, 75)

    def test_overfull_category_fails_without_crossing_band(self):
        nodes = {i: (i, 3, 0) for i in range(1, 53)}
        model = ModelSnapshot('test.std', 'Metric', nodes, {i: (i, i + 1) for i in range(1, 52)})
        with self.assertRaisesRegex(ValueError, 'larger floor block'):
            tools.floor_renumber_plan(model, 100)


class PredefinedGroupTests(unittest.TestCase):
    def test_guide_legend_and_level_types(self):
        groups = tools.predefined_group_plan(frame())
        names = {group.name: group for group in groups}
        self.assertEqual(names['_RB_CND'].kind, 1)
        self.assertEqual(names['_RB_MEM'].ids, tuple(sorted(frame().members)))
        self.assertEqual(names['_RB_FLR'].kind, 6)
        self.assertEqual(names['_RB_PRI_BM'].ids, (10, 11, 12, 20, 21))
        self.assertEqual(names['_RB_SEC_TER_BM'].ids, (30, 31, 40))
        self.assertIn('_RB_FLR_LVL2', names)
        self.assertIn('FLOOR', tools.group_plan_commands(groups))

    def test_only_known_generated_group_names_may_be_replaced(self):
        for name in ('_RB_PRI_BM', '_rb_cnd_lvl2', '_RB_MEM_LVL15'):
            self.assertTrue(tools.is_generated_group(name))
        for name in ('_RB_USER_GROUP', '_RB_MEM_LVL0', '_MEM', '_RB2_MEM', '_RB_MEM_extra'):
            self.assertFalse(tools.is_generated_group(name))

    def test_void_wrapper_bug_does_not_repeat_group_mutations(self):
        method = MagicMock(side_effect=TypeError("'<' not supported between instances of 'NoneType' and 'int'"))
        tools._void_group_call(method, '_RB_MEM')
        method.assert_called_once_with('_RB_MEM')
        with self.assertRaisesRegex(TypeError, 'malformed input'):
            tools._void_group_call(MagicMock(side_effect=TypeError('malformed input')), '_RB_MEM')

    def test_apply_replaces_owned_names_and_preserves_user_groups(self):
        model, staad = frame(), MagicMock()
        staad.GetSTAADFile.return_value = model.path
        definitions = {'_RB_MEM': (2, (10,)), '_RB_MEM_LVL99': (2, (20,)),
                       '_RB_USER': (2, (30,)), '_MY_GROUP': (1, (1, 5))}
        staad.Geometry.GetGroupCount.side_effect = lambda kind: sum(value[0] == kind for value in definitions.values())
        staad.Geometry.GetGroupNames.side_effect = lambda kind: [name for name, value in definitions.items() if value[0] == kind]
        staad.Geometry.GetGroupEntities.side_effect = lambda name: definitions[name][1]
        staad.Geometry.DeleteGroup.side_effect = lambda name: definitions.pop(name)
        staad.Geometry.CreateGroupEx.side_effect = lambda kind, name, ids: definitions.__setitem__(name, (kind, tuple(ids)))
        with patch.object(tools.live, 'connect', return_value=staad), \
             patch.object(tools.live, 'require_snapshot') as boundary, \
             patch.object(tools.live, 'capture', return_value=model) as capture, \
             patch.object(tools.live, '_backup_model', return_value=Path('backup.std')):
            result = tools.apply_predefined_groups(model, lambda *args: None)
        self.assertGreater(result.successful, 0)
        self.assertEqual(definitions['_RB_USER'], (2, (30,)))
        self.assertEqual(definitions['_MY_GROUP'], (1, (1, 5)))
        self.assertNotIn('_RB_MEM_LVL99', definitions)
        self.assertEqual(definitions['_RB_MEM'][1], tuple(sorted(model.members)))
        boundary.assert_called_once()
        capture.assert_called_once()


class PhysicalReleaseTests(unittest.TestCase):
    def test_complete_primary_chain_never_releases_internal_splits(self):
        plan = tools.selected_release_plan(frame(), [10, 11, 12])
        self.assertEqual(set(plan.assignments), {(10, 0), (12, 0)})
        self.assertEqual(len(plan.chains), 1)
        self.assertEqual(plan.skipped, {})
        self.assertNotIn(11, plan.member_ids)
        self.assertIn('10 12 START MY MZ', tools.release_plan_commands(plan))

    def test_secondary_chain_with_tertiary_connection_is_complete(self):
        plan = tools.selected_release_plan(frame(), [30, 31])
        self.assertEqual(set(plan.assignments), {(30, 0), (31, 0)})
        self.assertEqual(plan.skipped, {})

    def test_invalid_and_incomplete_members_have_explicit_reasons(self):
        plan = tools.selected_release_plan(frame(), [1, 10, 30, 40])
        self.assertFalse(plan.assignments)
        self.assertIn('Columns', plan.skipped[1])
        self.assertIn('Incomplete', plan.skipped[10])
        self.assertIn('Incomplete', plan.skipped[30])
        self.assertIn('Tertiary', plan.skipped[40])

    def test_start_and_end_filters_respect_reversed_analytical_incidence(self):
        model = frame()
        start = tools.selected_release_plan(model, [20, 21], end='START', dofs=('MZ',))
        end = tools.selected_release_plan(model, [20, 21], end='END', dofs=('MZ',))
        self.assertEqual(set(start.assignments), {(20, 0), (21, 0)})
        self.assertEqual(end.assignments, {})
        model.members[21] = tuple(reversed(model.members[21]))
        end = tools.selected_release_plan(model, [20, 21], end='END', dofs=('MZ',))
        self.assertEqual(set(end.assignments), {(21, 1)})

    def test_straight_chain_splits_at_column_not_at_secondary_attachment(self):
        model = frame()
        model.nodes[14] = (4, 0, 0)
        model.members[2] = (14, 3)
        model.supports.append(14)
        plan = tools.selected_release_plan(model, [10])
        self.assertEqual(set(plan.assignments), {(10, 0), (10, 1)})

    def test_apply_uses_current_selection_and_batches_identical_specs(self):
        model, staad = frame(), MagicMock()
        staad.GetSTAADFile.return_value = model.path
        staad.Geometry.GetNoOfSelectedBeams.return_value = 5
        staad.Geometry.GetSelectedBeams.return_value = [10, 11, 12, 20, 21]
        staad.Property.CreateMemberReleaseSpec.return_value = 0
        staad.Property.GetMemberReleaseSpec.return_value = ([0, 0, 0, 0, 1, 1], [0.] * 6)
        with patch.object(tools.live, 'connect', return_value=staad), \
             patch.object(tools.live, 'require_snapshot') as boundary, \
             patch.object(tools.live, 'capture', return_value=model) as capture, \
             patch.object(tools.live, '_backup_model', return_value=Path('backup.std')):
            result = tools.apply_selected_releases(model, lambda *args: None)
        self.assertEqual(result.successful, 4)
        staad.Property.CreateMemberReleaseSpec.assert_called_once()
        staad.Property.AssignMemberSpecToBeam.assert_called_once_with([10, 12, 20, 21], 0)
        self.assertEqual(staad.Property.GetMemberReleaseSpec.call_count, 4)
        boundary.assert_called_once()
        capture.assert_called_once()

    def test_invalid_selection_requires_explicit_proceed_before_backup(self):
        model, staad = frame(), MagicMock()
        staad.Geometry.GetNoOfSelectedBeams.return_value = 4
        staad.Geometry.GetSelectedBeams.return_value = [1, 10, 11, 12]
        with patch.object(tools.live, 'connect', return_value=staad), \
             patch.object(tools.live, 'require_snapshot'), \
             patch.object(tools.live, '_backup_model') as backup:
            with self.assertRaisesRegex(ValueError, 'Proceed'):
                tools.apply_selected_releases(model, lambda *args: None)
            backup.assert_not_called()

    def test_selection_change_after_review_blocks_before_writes(self):
        model, staad = frame(), MagicMock()
        reviewed = tools.selected_release_plan(model, [10, 11, 12])
        staad.Geometry.GetNoOfSelectedBeams.return_value = 2
        staad.Geometry.GetSelectedBeams.return_value = [20, 21]
        with patch.object(tools.live, 'connect', return_value=staad), \
             patch.object(tools.live, 'require_snapshot'), \
             patch.object(tools.live, '_backup_model') as backup:
            with self.assertRaisesRegex(ValueError, 'selection or release options changed'):
                tools.apply_selected_releases(model, lambda *args: None, plan=reviewed)
            backup.assert_not_called()
            staad.Property.CreateMemberReleaseSpec.assert_not_called()

    def test_option_change_after_review_blocks_before_writes(self):
        model, staad = frame(), MagicMock()
        reviewed = tools.selected_release_plan(model, [10, 11, 12])
        staad.Geometry.GetNoOfSelectedBeams.return_value = 3
        staad.Geometry.GetSelectedBeams.return_value = [10, 11, 12]
        with patch.object(tools.live, 'connect', return_value=staad), \
             patch.object(tools.live, 'require_snapshot'), \
             patch.object(tools.live, '_backup_model') as backup:
            with self.assertRaisesRegex(ValueError, 'selection or release options changed'):
                tools.apply_selected_releases(model, lambda *args: None, dofs=('MZ',), plan=reviewed)
            backup.assert_not_called()


if __name__ == '__main__':
    unittest.main()
