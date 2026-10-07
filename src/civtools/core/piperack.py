"""Execute a validated rack plan against a verified blank STAAD model."""
from .geometry import brace_bays, build_rack_plan
from .cad import connect_staad, require_empty_model, staad_model_name

class PipeRackGenerator:

    def __init__(self, report=None):
        self.report = report or (lambda *args: None)
        self.open_staad = None
        self.geometry = None
        self.property = None
        self.support = None
        self.load = None
        self.command = None
        self.nodes = []
        self.beams = []
        self.beam_counter = 1
        self._grid_lookup = {}

    def connect_to_staad(self):
        """Connect to OpenSTAAD application"""
        try:
            self.open_staad, self.model_name = connect_staad()
            self.report("target", self.model_name)
            self.geometry = self.open_staad.Geometry
            self.support = self.open_staad.Support
            self.command = self.open_staad.Command
            self.geometry._FlagAsMethod('AddNode')
            self.geometry._FlagAsMethod('AddBeam')
            self.support._FlagAsMethod('CreateSupportPinned')
            self.support._FlagAsMethod('CreateSupportFixed')
            self.support._FlagAsMethod('AssignSupportToNode')
            self.command._FlagAsMethod('ExecuteCommand')
            self.report("log", f"Connected to {self.model_name}")
            return True
        except Exception as e:
            raise RuntimeError(f'Failed to connect to STAAD: {e}') from e

    def create_comprehensive_pipe_rack(self, config):
        """Create a complete pipe rack with all structural elements"""
        plan = build_rack_plan(config)
        if not self.connect_to_staad():
            return False
        require_empty_model(self.geometry)
        if staad_model_name(self.open_staad) != self.model_name:
            raise RuntimeError("The active STAAD model changed. Run again with the intended model open.")
        self.report("stage", "Blank model verified; creating geometry")
        self.nodes, self.beams = [], []
        total = plan.com_calls
        completed = 0

        def progress(stage, index, count):
            nonlocal completed
            completed += 1
            if index % 25 == 0 or index == count:
                self.report("stage", f"{stage}: {index:,} / {count:,}")
                self.report("progress", round(completed * 100 / total))

        try:
            for index, coords in enumerate(plan.nodes, 1):
                node_id = self.geometry.AddNode(*coords)
                if not node_id or node_id < 0:
                    raise RuntimeError(f"STAAD rejected node {index}.")
                self.nodes.append({"staad_id": node_id, "coords": coords})
                progress("Creating nodes", index, len(plan.nodes))
            for index, (start, end, kind) in enumerate(plan.beams, 1):
                beam_id = self.geometry.AddBeam(self.nodes[start]["staad_id"], self.nodes[end]["staad_id"])
                if not beam_id or beam_id < 0:
                    raise RuntimeError(f"STAAD rejected beam {index}.")
                self.beams.append({"staad_id": beam_id, "type": kind, "nodes": (start, end)})
                progress("Creating beams", index, len(plan.beams))
            create_support = self.support.CreateSupportFixed if plan.support_type == "Fixed" else self.support.CreateSupportPinned
            support_id = create_support()
            if not support_id or support_id < 0:
                raise RuntimeError("STAAD could not create the support definition.")
            completed += 1
            for index, node in enumerate(plan.foundations, 1):
                self.support.AssignSupportToNode(self.nodes[node]["staad_id"], support_id)
                progress("Assigning supports", index, len(plan.foundations))
        except Exception as error:
            raise RuntimeError(f"Generation stopped after {len(self.nodes):,} nodes and {len(self.beams):,} beams. The model may contain partial changes. {error}") from error
        self.report("progress", 100)
        return True

    def _create_all_nodes(self, num_trans, num_long, trans_spacing, long_spacing, trans_beam_elevations, long_beam_elevations, base_elev, found_depth):
        """Create all nodes based on independent transverse and longitudinal elevations"""
        node_id = 1
        self._grid_lookup = {}
        tier_nodes_by_elevation = {}
        for j in range(num_long):
            for k in range(num_trans):
                x = trans_spacing[k]
                z = long_spacing[j]
                y = base_elev - found_depth
                node_num = self.geometry.AddNode(x, y, z)
                self.nodes.append({'id': node_id, 'staad_id': node_num, 'type': 'foundation', 'coords': [x, y, z], 'grid': [k, j, -1]})
                self._grid_lookup[k, j, -1] = self.nodes[-1]
                node_id += 1
        for j in range(num_long):
            for k in range(num_trans):
                x = trans_spacing[k]
                z = long_spacing[j]
                y = base_elev
                node_num = self.geometry.AddNode(x, y, z)
                self.nodes.append({'id': node_id, 'staad_id': node_num, 'type': 'base', 'coords': [x, y, z], 'grid': [k, j, 0]})
                self._grid_lookup[k, j, 0] = self.nodes[-1]
                node_id += 1
        for (level_type, elevations) in (('T', trans_beam_elevations), ('L', long_beam_elevations)):
            for (i, elev) in enumerate(elevations):
                tag = (level_type, i)
                for j in range(num_long):
                    for k in range(num_trans):
                        y = elev
                        elevation_key = (k, j, y)
                        node = tier_nodes_by_elevation.get(elevation_key)
                        if node is None:
                            x = trans_spacing[k]
                            z = long_spacing[j]
                            node_num = self.geometry.AddNode(x, y, z)
                            node = {'id': node_id, 'staad_id': node_num, 'type': 'trans_tier' if level_type == 'T' else 'long_tier', 'coords': [x, y, z], 'grid': [k, j, tag]}
                            self.nodes.append(node)
                            tier_nodes_by_elevation[elevation_key] = node
                            node_id += 1
                        self._grid_lookup[k, j, tag] = node

    def _create_columns(self, num_trans, num_long, trans_beam_elevations, long_beam_elevations):
        """Create columns connecting foundation -> base -> all tier levels sorted by elevation"""
        for j in range(num_long):
            for k in range(num_trans):
                found_node = self._get_node_by_grid(k, j, -1)
                base_node = self._get_node_by_grid(k, j, 0)
                if found_node and base_node:
                    beam_num = self.geometry.AddBeam(found_node['staad_id'], base_node['staad_id'])
                    self.beams.append({'id': self.beam_counter, 'staad_id': beam_num, 'type': 'foundation_column', 'nodes': [found_node['id'], base_node['id']]})
                    self.beam_counter += 1
        all_levels = []
        for (i, elev) in enumerate(trans_beam_elevations):
            all_levels.append((elev, ('T', i)))
        for (i, elev) in enumerate(long_beam_elevations):
            all_levels.append((elev, ('L', i)))
        all_levels.sort(key=lambda x: x[0])
        for j in range(num_long):
            for k in range(num_trans):
                prev_node = self._get_node_by_grid(k, j, 0)
                for (elev, tag) in all_levels:
                    curr_node = self._get_node_by_grid(k, j, tag)
                    if prev_node and curr_node and (prev_node['staad_id'] != curr_node['staad_id']):
                        beam_num = self.geometry.AddBeam(prev_node['staad_id'], curr_node['staad_id'])
                        self.beams.append({'id': self.beam_counter, 'staad_id': beam_num, 'type': 'column', 'nodes': [prev_node['id'], curr_node['id']]})
                        self.beam_counter += 1
                    prev_node = curr_node

    def _create_main_beams(self, num_trans, num_long, trans_beam_elevations, long_beam_elevations):
        """Create transverse beams at trans levels, longitudinal beams at long levels"""
        for i in range(len(trans_beam_elevations)):
            for j in range(num_long):
                for k in range(num_trans - 1):
                    node1 = self._get_node_by_grid(k, j, ('T', i))
                    node2 = self._get_node_by_grid(k + 1, j, ('T', i))
                    if node1 and node2:
                        beam_num = self.geometry.AddBeam(node1['staad_id'], node2['staad_id'])
                        self.beams.append({'id': self.beam_counter, 'staad_id': beam_num, 'type': 'transverse_beam', 'nodes': [node1['id'], node2['id']]})
                        self.beam_counter += 1
        for i in range(len(long_beam_elevations)):
            for j in range(num_long - 1):
                for k in range(num_trans):
                    node1 = self._get_node_by_grid(k, j, ('L', i))
                    node2 = self._get_node_by_grid(k, j + 1, ('L', i))
                    if node1 and node2:
                        beam_num = self.geometry.AddBeam(node1['staad_id'], node2['staad_id'])
                        self.beams.append({'id': self.beam_counter, 'staad_id': beam_num, 'type': 'longitudinal_beam', 'nodes': [node1['id'], node2['id']]})
                        self.beam_counter += 1

    def _create_longitudinal_bracing_system(self, num_trans, num_long, tier_elevations):
        """Create V-bracing system in longitudinal direction only, with alternating pattern"""
        node_id = len(self.nodes) + 1
        bays = brace_bays(num_long)
        levels = [(0, 0)] + [(('T', index), index + 1) for index in range(len(tier_elevations))]
        for ((bottom_tag, _), (top_tag, tier_number)) in zip(levels, levels[1:]):
            for j in bays:
                for k in [0, num_trans - 1]:
                    node1 = self._get_node_by_grid(k, j, bottom_tag)
                    node2 = self._get_node_by_grid(k, j + 1, bottom_tag)
                    node3 = self._get_node_by_grid(k, j, top_tag)
                    node4 = self._get_node_by_grid(k, j + 1, top_tag)
                    if all([node1, node2, node3, node4]):
                        x_mid = (node3['coords'][0] + node4['coords'][0]) / 2
                        y_mid = node3['coords'][1]
                        z_mid = (node3['coords'][2] + node4['coords'][2]) / 2
                        mid_node_num = self.geometry.AddNode(x_mid, y_mid, z_mid)
                        mid_node = {'id': node_id, 'staad_id': mid_node_num, 'type': 'brace_mid', 'coords': [x_mid, y_mid, z_mid], 'grid': [k, j + 0.5, tier_number]}
                        self.nodes.append(mid_node)
                        node_id += 1
                        beam_num1 = self.geometry.AddBeam(node1['staad_id'], mid_node_num)
                        self.beams.append({'id': self.beam_counter, 'staad_id': beam_num1, 'type': 'longitudinal_v_brace', 'nodes': [node1['id'], mid_node['id']]})
                        self.beam_counter += 1
                        beam_num2 = self.geometry.AddBeam(node2['staad_id'], mid_node_num)
                        self.beams.append({'id': self.beam_counter, 'staad_id': beam_num2, 'type': 'longitudinal_v_brace', 'nodes': [node2['id'], mid_node['id']]})
                        self.beam_counter += 1

    def _assign_supports_pinned(self, num_trans, num_long):
        """Assign pinned supports to foundation nodes"""
        return self._assign_supports_to_foundations(num_trans, num_long, self.support.CreateSupportPinned)

    def _assign_supports_fixed(self, num_trans, num_long):
        """Assign fixed supports to foundation nodes"""
        return self._assign_supports_to_foundations(num_trans, num_long, self.support.CreateSupportFixed)

    def _assign_supports_to_foundations(self, num_trans, num_long, create_support):
        foundation_nodes = [node['staad_id'] for j in range(num_long) for k in range(num_trans) if (node := self._get_node_by_grid(k, j, -1)) is not None]
        if not foundation_nodes:
            raise RuntimeError('No foundation nodes were created.')
        support_id = create_support()
        failures = []
        for node_id in foundation_nodes:
            try:
                self.support.AssignSupportToNode(node_id, support_id)
            except Exception as error:
                failures.append(f'{node_id}: {error}')
        if failures:
            raise RuntimeError('Failed to assign support to foundation node(s): ' + '; '.join(failures))
        return True

    def _assign_supports(self, num_trans, num_long, support_type):
        """Assign supports based on support type"""
        if support_type == 'Fixed':
            return self._assign_supports_fixed(num_trans, num_long)
        if support_type == 'Pinned':
            return self._assign_supports_pinned(num_trans, num_long)
        raise ValueError(f'Unknown support type: {support_type}')

    def _get_node_by_grid(self, k, j, i):
        """Get node by grid coordinates"""
        node = self._grid_lookup.get((k, j, i))
        if node is not None:
            return node
        for node in self.nodes:
            if 'grid' in node and node['grid'] == [k, j, i]:
                return node
        return None
