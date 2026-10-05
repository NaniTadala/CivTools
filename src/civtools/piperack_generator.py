from pathlib import Path
import customtkinter as ctk
from comtypes import client
from comtypes import automation
import math
import json
import os
from tkinter import messagebox

ctk.set_appearance_mode("light")  # Modes: "System" (default), "Dark", "Light"
ctk.set_default_color_theme("dark-blue")  # Themes: "blue" (default), "green", "dark-blue"

def get_config_path():
    """Get the path to the config file in AppData."""
    app_data = os.environ.get("APPDATA")
    if not app_data:
        raise OSError("The Windows APPDATA directory is not available.")
    config_dir = Path(app_data) / "CivTools"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "pipe_rack_configs.json"

class PipeRackGenerator:
    def __init__(self):
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
            # Try to get active STAAD instance first
            try:
                self.open_staad = client.GetActiveObject("StaadPro.OpenSTAAD")
                print("Connected to existing STAAD instance")
            except:
                # If no active instance, create a new one
                self.open_staad = client.CreateObject("StaadPro.OpenSTAAD")
                print("Created new STAAD instance")
                
                # Create a new model file
                self.command = self.open_staad.Command
                self.command._FlagAsMethod("ExecuteCommand")
                self.command.ExecuteCommand("NEW")
                
            # Get required interfaces
            self.geometry = self.open_staad.Geometry
            self.support = self.open_staad.Support
            self.command = self.open_staad.Command
            
            # Flag required methods
            self.geometry._FlagAsMethod("AddNode")
            self.geometry._FlagAsMethod("AddBeam")
            self.support._FlagAsMethod("CreateSupportPinned") 
            self.support._FlagAsMethod("CreateSupportFixed")
            self.support._FlagAsMethod("AssignSupportToNode")
            self.command._FlagAsMethod("ExecuteCommand")
            
            print("Successfully connected to STAAD")
            return True
            
        except Exception as e:
            print(f"Failed to connect to STAAD: {e}")
            return False
    
    def create_comprehensive_pipe_rack(self, config):
        """Create a complete pipe rack with all structural elements"""
        if not self.connect_to_staad():
            return False
            
        # Clear existing nodes and beams
        self.nodes = []
        self.beams = []
        self.beam_counter = 1
        
        # Extract configuration parameters
        num_transverse = config.get('num_transverse_grids', 2)
        num_longitudinal = config.get('num_longitudinal_grids', 4)
        base_elevation = config.get('base_elevation', 0.0)
        
        # Generate grid spacing if not provided
        if 'transverse_spacing' not in config:
            config['transverse_spacing'] = [i * 6.0 for i in range(num_transverse)]
        if 'longitudinal_spacing' not in config:
            config['longitudinal_spacing'] = [i * 8.0 for i in range(num_longitudinal)]
        
        transverse_spacing = config['transverse_spacing']
        longitudinal_spacing = config['longitudinal_spacing']
        
        # Validate grid dimensions
        if len(transverse_spacing) != num_transverse:
            print(f"Warning: transverse_spacing length ({len(transverse_spacing)}) doesn't match num_transverse_grids ({num_transverse})")
            num_transverse = len(transverse_spacing)
        if len(longitudinal_spacing) != num_longitudinal:
            print(f"Warning: longitudinal_spacing length ({len(longitudinal_spacing)}) doesn't match num_longitudinal_grids ({num_longitudinal})")
            num_longitudinal = len(longitudinal_spacing)
        
        # Structural parameters
        foundation_depth = config.get('foundation_depth', 1.5)
        bracing_enabled = config.get('bracing_enabled', False)
        
        print("Creating comprehensive pipe rack structure...")
        
        # Step 1: Create all nodes including foundation nodes
        trans_beam_elevations = config.get('trans_beam_elevations', [])
        long_beam_elevations  = config.get('long_beam_elevations', [])

        self._create_all_nodes(num_transverse, num_longitudinal,
                               transverse_spacing, longitudinal_spacing,
                               trans_beam_elevations, long_beam_elevations,
                               base_elevation, foundation_depth)
        self._create_columns(num_transverse, num_longitudinal,
                             trans_beam_elevations, long_beam_elevations)
        self._create_main_beams(num_transverse, num_longitudinal,
                                trans_beam_elevations, long_beam_elevations)
        
        # Step 3: Create V-bracing systems (longitudinal only)
        # NEW - bracing uses trans levels as reference for tier count
        if bracing_enabled:
            self._create_longitudinal_bracing_system(
                num_transverse, num_longitudinal, trans_beam_elevations
            )
        
        # Step 4: Assign supports
        support_type = config.get('support_type', 'Fixed')
        if not self._assign_supports(num_transverse, num_longitudinal, support_type):
            return False
        
        print(f"Pipe rack created successfully with {len(self.nodes)} nodes and {len(self.beams)} beams")
        return True
    
    # NEW
    def _create_all_nodes(self, num_trans, num_long, trans_spacing, long_spacing,
                         trans_beam_elevations, long_beam_elevations,
                         base_elev, found_depth):
        """Create all nodes based on independent transverse and longitudinal elevations"""
        node_id = 1
        self._grid_lookup = {}
        tier_nodes_by_elevation = {}

        # Foundation nodes
        for j in range(num_long):
            for k in range(num_trans):
                x = trans_spacing[k]
                z = long_spacing[j]
                y = base_elev - found_depth
                node_num = self.geometry.AddNode(x, y, z)
                self.nodes.append({'id': node_id, 'staad_id': node_num, 'type': 'foundation',
                                   'coords': [x, y, z], 'grid': [k, j, -1]})
                self._grid_lookup[(k, j, -1)] = self.nodes[-1]
                node_id += 1

        # Base level nodes
        for j in range(num_long):
            for k in range(num_trans):
                x = trans_spacing[k]
                z = long_spacing[j]
                y = base_elev
                node_num = self.geometry.AddNode(x, y, z)
                self.nodes.append({'id': node_id, 'staad_id': node_num, 'type': 'base',
                                   'coords': [x, y, z], 'grid': [k, j, 0]})
                self._grid_lookup[(k, j, 0)] = self.nodes[-1]
                node_id += 1

        for level_type, elevations in (
            ("T", trans_beam_elevations),
            ("L", long_beam_elevations),
        ):
            for i, elev in enumerate(elevations):
                tag = (level_type, i)
                for j in range(num_long):
                    for k in range(num_trans):
                        y = base_elev + elev
                        elevation_key = (k, j, y)
                        node = tier_nodes_by_elevation.get(elevation_key)
                        if node is None:
                            x = trans_spacing[k]
                            z = long_spacing[j]
                            node_num = self.geometry.AddNode(x, y, z)
                            node = {
                                'id': node_id,
                                'staad_id': node_num,
                                'type': 'trans_tier' if level_type == "T" else 'long_tier',
                                'coords': [x, y, z],
                                'grid': [k, j, tag],
                            }
                            self.nodes.append(node)
                            tier_nodes_by_elevation[elevation_key] = node
                            node_id += 1
                        self._grid_lookup[(k, j, tag)] = node
    
    # NEW
    def _create_columns(self, num_trans, num_long, trans_beam_elevations, long_beam_elevations):
        """Create columns connecting foundation -> base -> all tier levels sorted by elevation"""

        # Foundation to base
        for j in range(num_long):
            for k in range(num_trans):
                found_node = self._get_node_by_grid(k, j, -1)
                base_node  = self._get_node_by_grid(k, j, 0)
                if found_node and base_node:
                    beam_num = self.geometry.AddBeam(found_node['staad_id'], base_node['staad_id'])
                    self.beams.append({'id': self.beam_counter, 'staad_id': beam_num,
                                       'type': 'foundation_column',
                                       'nodes': [found_node['id'], base_node['id']]})
                    self.beam_counter += 1

        # Build sorted list of all levels: (elevation, grid_tag)
        all_levels = []
        for i, elev in enumerate(trans_beam_elevations):
            all_levels.append((elev, ('T', i)))
        for i, elev in enumerate(long_beam_elevations):
            all_levels.append((elev, ('L', i)))
        all_levels.sort(key=lambda x: x[0])

        # Connect base -> first level, then level -> level in elevation order
        for j in range(num_long):
            for k in range(num_trans):
                prev_node = self._get_node_by_grid(k, j, 0)  # start from base
                for elev, tag in all_levels:
                    curr_node = self._get_node_by_grid(k, j, tag)
                    if (
                        prev_node
                        and curr_node
                        and prev_node['staad_id'] != curr_node['staad_id']
                    ):
                        beam_num = self.geometry.AddBeam(prev_node['staad_id'], curr_node['staad_id'])
                        self.beams.append({'id': self.beam_counter, 'staad_id': beam_num,
                                           'type': 'column',
                                           'nodes': [prev_node['id'], curr_node['id']]})
                        self.beam_counter += 1
                    prev_node = curr_node
    
    # NEW
    def _create_main_beams(self, num_trans, num_long, trans_beam_elevations, long_beam_elevations):
        """Create transverse beams at trans levels, longitudinal beams at long levels"""

        # Transverse beams at each transverse level
        for i in range(len(trans_beam_elevations)):
            for j in range(num_long):
                for k in range(num_trans - 1):
                    node1 = self._get_node_by_grid(k,   j, ('T', i))
                    node2 = self._get_node_by_grid(k+1, j, ('T', i))
                    if node1 and node2:
                        beam_num = self.geometry.AddBeam(node1['staad_id'], node2['staad_id'])
                        self.beams.append({'id': self.beam_counter, 'staad_id': beam_num,
                                           'type': 'transverse_beam',
                                           'nodes': [node1['id'], node2['id']]})
                        self.beam_counter += 1

        # Longitudinal beams at each longitudinal level
        for i in range(len(long_beam_elevations)):
            for j in range(num_long - 1):
                for k in range(num_trans):
                    node1 = self._get_node_by_grid(k, j,   ('L', i))
                    node2 = self._get_node_by_grid(k, j+1, ('L', i))
                    if node1 and node2:
                        beam_num = self.geometry.AddBeam(node1['staad_id'], node2['staad_id'])
                        self.beams.append({'id': self.beam_counter, 'staad_id': beam_num,
                                           'type': 'longitudinal_beam',
                                           'nodes': [node1['id'], node2['id']]})
                        self.beam_counter += 1
    
    def _create_longitudinal_bracing_system(self, num_trans, num_long, tier_elevations):
        """Create V-bracing system in longitudinal direction only, with alternating pattern"""
        node_id = len(self.nodes) + 1
        
        # Determine which bays to brace based on number of longitudinal bays
        if num_long <= 2:
            # No bracing if only 1 or 2 bays
            return
            
        # For 3 bays, brace the middle bay (bay 1)
        elif num_long == 3:
            brace_bays = [1]
            
        # For 4 bays, brace either bay 1 or 2 (we'll choose bay 1)
        elif num_long == 4:
            brace_bays = [1]
            
        # For more than 4 bays, alternate bracing in middle bays
        else:
            # Start with second bay, then alternate
            brace_bays = []
            start_bay = 1 if num_long % 2 == 0 else 2  # Start at bay 1 for even, bay 2 for odd
            for i in range(start_bay, num_long-1, 2):
                brace_bays.append(i)
        
        # Brace from the base to the first tier, then between adjacent tiers.
        levels = [(0, 0)] + [
            (("T", index), index + 1)
            for index in range(len(tier_elevations))
        ]
        for (bottom_tag, _), (top_tag, tier_number) in zip(levels, levels[1:]):
            for j in brace_bays:
                for k in [0, num_trans - 1]:  # Only at end frames
                    node1 = self._get_node_by_grid(k, j, bottom_tag)
                    node2 = self._get_node_by_grid(k, j + 1, bottom_tag)
                    node3 = self._get_node_by_grid(k, j, top_tag)
                    node4 = self._get_node_by_grid(k, j + 1, top_tag)
                    
                    if all([node1, node2, node3, node4]):
                        # Create mid-point node at the center of TOP beam (for V pattern)
                        x_mid = (node3['coords'][0] + node4['coords'][0]) / 2
                        y_mid = node3['coords'][1]  # Same as top nodes
                        z_mid = (node3['coords'][2] + node4['coords'][2]) / 2
                        
                        mid_node_num = self.geometry.AddNode(x_mid, y_mid, z_mid)
                        mid_node = {'id': node_id, 'staad_id': mid_node_num, 'type': 'brace_mid',
                                   'coords': [x_mid, y_mid, z_mid],
                                   'grid': [k, j + 0.5, tier_number]}
                        self.nodes.append(mid_node)
                        node_id += 1
                        
                        # Create V-bracing: from bottom corners to mid-point (V pattern)
                        beam_num1 = self.geometry.AddBeam(node1['staad_id'], mid_node_num)
                        self.beams.append({'id': self.beam_counter, 'staad_id': beam_num1, 
                                         'type': 'longitudinal_v_brace', 'nodes': [node1['id'], mid_node['id']]})
                        self.beam_counter += 1
                        
                        beam_num2 = self.geometry.AddBeam(node2['staad_id'], mid_node_num)
                        self.beams.append({'id': self.beam_counter, 'staad_id': beam_num2, 
                                         'type': 'longitudinal_v_brace', 'nodes': [node2['id'], mid_node['id']]})
                        self.beam_counter += 1

    def _assign_supports_pinned(self, num_trans, num_long):
        """Assign pinned supports to foundation nodes"""
        return self._assign_supports_to_foundations(
            num_trans, num_long, self.support.CreateSupportPinned
        )
    
    def _assign_supports_fixed(self, num_trans, num_long):
        """Assign fixed supports to foundation nodes"""
        return self._assign_supports_to_foundations(
            num_trans, num_long, self.support.CreateSupportFixed
        )

    def _assign_supports_to_foundations(self, num_trans, num_long, create_support):
        foundation_nodes = [
            node["staad_id"]
            for j in range(num_long)
            for k in range(num_trans)
            if (node := self._get_node_by_grid(k, j, -1)) is not None
        ]
        if not foundation_nodes:
            raise RuntimeError("No foundation nodes were created.")

        support_id = create_support()
        failures = []
        for node_id in foundation_nodes:
            try:
                self.support.AssignSupportToNode(node_id, support_id)
            except Exception as error:
                failures.append(f"{node_id}: {error}")
        if failures:
            raise RuntimeError(
                "Failed to assign support to foundation node(s): "
                + "; ".join(failures)
            )
        return True

    def _assign_supports(self, num_trans, num_long, support_type):
        """Assign supports based on support type"""
        if support_type == "Fixed":
            return self._assign_supports_fixed(num_trans, num_long)
        if support_type == "Pinned":
            return self._assign_supports_pinned(num_trans, num_long)
        raise ValueError(f"Unknown support type: {support_type}")
    
    def _get_node_by_grid(self, k, j, i):
        """Get node by grid coordinates"""
        node = self._grid_lookup.get((k, j, i))
        if node is not None:
            return node
        for node in self.nodes:
            if 'grid' in node and node['grid'] == [k, j, i]:
                return node
        return None

class PipeRackApp(ctk.CTkToplevel):
    def __init__(self, master=None):
        super().__init__(master)
        # 1. Hide the window initially
        self.withdraw()
        self.generator = PipeRackGenerator()
        self.config = {}
        self.saved_configs = []
        self.selected_config_index = ctk.IntVar(value=-1)  # Add this line for radio button selection
        
        self.title("STAAD Pipe Rack Modeler")
        self.geometry("1000x720")
        self.minsize(800, 720)
        
        # Configure grid layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        # Create main container
        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(2, weight=1)  # Changed from 1 to 2
        
        # Title label
        self.title_label = ctk.CTkLabel(
            self.main_frame, 
            text="STAAD Pipe Rack Modeler",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        self.title_label.grid(row=0, column=0, pady=(10, 20), sticky="n")
        
        # Usage instructions label
        usage_text = ("USAGE INSTRUCTION - Before running this program, please ensure that STAAD.Pro is launched\n"
                    "and a new blank project file is created with the appropriate file name")
        self.usage_label = ctk.CTkLabel(
            self.main_frame,
            text=usage_text,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="blue",
            wraplength=750
        )
        self.usage_label.grid(row=1, column=0, pady=(0, 20), sticky="n")
        
        # Create tabview (row changed from 1 to 2)
        self.tabview = ctk.CTkTabview(self.main_frame)
        self.tabview.grid(row=2, column=0, padx=10, pady=(0, 10), sticky="nsew")
        self.tabview.grid_columnconfigure(0, weight=1)
        
        # Add tabs
        self.tabview.add("Basic Configuration")
        self.tabview.add("Advanced Configuration")
        self.tabview.add("Saved Configurations")
        
        # Configure tabs to expand
        for tab in ["Basic Configuration", "Advanced Configuration", "Saved Configurations"]:
            self.tabview.tab(tab).grid_columnconfigure(0, weight=1)
        
        # Basic Configuration Tab
        self.setup_basic_config_tab()
        
        # Advanced Configuration Tab
        self.setup_advanced_config_tab()
        
        # Saved Configurations Tab
        self.setup_saved_configs_tab()
        
        # Generate button (row changed from 2 to 3)
        self.generate_button = ctk.CTkButton(
            self.main_frame,
            text="Generate Pipe Rack",
            command=self.generate_pipe_rack,
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"))
        self.generate_button.grid(row=3, column=0, pady=(0, 10), sticky="ew", padx=10)
        
        # Status label (row changed from 3 to 4)
        self.status_label = ctk.CTkLabel(
            self.main_frame,
            text="Ready",
            text_color="gray70"
        )
        self.status_label.grid(row=4, column=0, pady=(0, 10))
        
        # Load saved configs
        self.load_saved_configs()
        # 2. Show the window after everything is set up
        self.deiconify()
    
    def update_spacing_tables(self, event=None):
        """Update the spacing tables based on current grid counts"""
        try:
            # Clear all tables completely
            for table in [self.trans_spacing_table, self.long_spacing_table, self.tier_heights_table]:
                for widget in table.winfo_children():
                    widget.destroy()
            
            self.trans_spacing_entries = []
            self.long_spacing_entries = []
            self.tier_heights_entries = []
            
            # Get current counts
            num_trans = int(self.trans_grids_entry.get() or 2)
            num_long = int(self.long_grids_entry.get() or 4)
            num_tiers = int(self.tiers_entry.get() or 2)
            
            # Helper function to create entries
            def create_entries(table, count, entries_list, prefix, defaults):
                for i in range(count):
                    frame = ctk.CTkFrame(table)
                    frame.pack(fill="x", pady=2)
                    ctk.CTkLabel(frame, text=f"{prefix} {i+1}:").pack(side="left", padx=5)
                    entry = ctk.CTkEntry(frame, width=100)
                    entry.pack(side="right", padx=5)
                    if i < len(defaults):
                        entry.insert(0, str(defaults[i]))
                    entries_list.append(entry)
            
            # Create entries for each table
            create_entries(self.trans_spacing_table, num_trans, self.trans_spacing_entries, 
                        "Grid", [0.0, 6.0, 12.0, 18.0])
            create_entries(self.long_spacing_table, num_long, self.long_spacing_entries,
                        "Grid", [0.0, 8.0, 16.0, 24.0])
            create_entries(self.tier_heights_table, num_tiers, self.tier_heights_entries,
                        "Tier", [3.0, 6.0, 9.0, 12.0])
                
        except ValueError:
            pass  # Ignore invalid input during typing
    
    def setup_basic_config_tab(self):
        tab = self.tabview.tab("Basic Configuration")
        tab.grid_columnconfigure(0, weight=1)
        
        # Frame for basic parameters (only remaining ones)
        frame = ctk.CTkFrame(tab)
        frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        frame.grid_columnconfigure(1, weight=1)
        
        # Basic parameters
        ctk.CTkLabel(frame, text="Basic Parameters", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, columnspan=2, pady=(0, 10), sticky="w")
        
        # Base elevation
        ctk.CTkLabel(frame, text="Base Elevation (m):").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        self.base_elev_entry = ctk.CTkEntry(frame, placeholder_text="0.0")
        self.base_elev_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        
        # Foundation depth
        ctk.CTkLabel(frame, text="Foundation Depth (m):").grid(row=2, column=0, padx=5, pady=5, sticky="e")
        self.foundation_depth_entry = ctk.CTkEntry(frame, placeholder_text="1.5")
        self.foundation_depth_entry.grid(row=2, column=1, padx=5, pady=5, sticky="ew")
        
        # Spacing tables frame (now in one row)
        spacing_frame = ctk.CTkFrame(tab)
        spacing_frame.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        spacing_frame.grid_columnconfigure(0, weight=1)  # Transverse
        spacing_frame.grid_columnconfigure(1, weight=1)  # Longitudinal
        spacing_frame.grid_columnconfigure(2, weight=1)  # Tier heights
        spacing_frame.grid_rowconfigure(0, weight=1)
        
        # Transverse spacing table (left)
        trans_frame = ctk.CTkFrame(spacing_frame)
        trans_frame.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
        
        # Add transverse count input inside the transverse frame
        trans_count_frame = ctk.CTkFrame(trans_frame)
        trans_count_frame.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(trans_count_frame, text="Number of Transverse Grids:").pack(side="left", padx=5)
        self.trans_grids_entry = ctk.CTkEntry(trans_count_frame, placeholder_text="2", width=80)
        self.trans_grids_entry.pack(side="right", padx=5)
        self.trans_grids_entry.bind("<KeyRelease>", self.update_transverse_table)
        
        ctk.CTkLabel(trans_frame, text="Transverse Spacing (m):", font=ctk.CTkFont(weight="bold")).pack(pady=(0, 5))
        self.trans_spacing_table = ctk.CTkScrollableFrame(trans_frame, height=100)
        self.trans_spacing_table.pack(fill="both", expand=True)
        self.trans_spacing_entries = []
        
        # Longitudinal spacing table (middle)
        long_frame = ctk.CTkFrame(spacing_frame)
        long_frame.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")
        
        # Add longitudinal count input inside the longitudinal frame
        long_count_frame = ctk.CTkFrame(long_frame)
        long_count_frame.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(long_count_frame, text="Number of Longitudinal Grids:").pack(side="left", padx=5)
        self.long_grids_entry = ctk.CTkEntry(long_count_frame, placeholder_text="4", width=80)
        self.long_grids_entry.pack(side="right", padx=5)
        self.long_grids_entry.bind("<KeyRelease>", self.update_longitudinal_table)
        
        ctk.CTkLabel(long_frame, text="Longitudinal Spacing (m):", font=ctk.CTkFont(weight="bold")).pack(pady=(0, 5))
        self.long_spacing_table = ctk.CTkScrollableFrame(long_frame, height=100)
        self.long_spacing_table.pack(fill="both", expand=True)
        self.long_spacing_entries = []
        
        # Tier heights table (right)
        tier_frame = ctk.CTkFrame(spacing_frame)
        tier_frame.grid(row=0, column=2, padx=5, pady=5, sticky="nsew")

        tier_count_frame = ctk.CTkFrame(tier_frame)
        tier_count_frame.pack(fill="x", pady=(0, 10))
        tier_count_frame.grid_columnconfigure(0, weight=1)
        tier_count_frame.grid_columnconfigure(1, weight=1)

        # Transverse count (left)
        trans_count_inner = ctk.CTkFrame(tier_count_frame)
        trans_count_inner.grid(row=0, column=0, padx=(0, 3), sticky="ew")
        ctk.CTkLabel(trans_count_inner, text="No. of Transverse Levels:").pack(side="left", padx=5)
        self.trans_tiers_entry = ctk.CTkEntry(trans_count_inner, placeholder_text="2", width=50)
        self.trans_tiers_entry.pack(side="right", padx=5)
        self.trans_tiers_entry.bind("<KeyRelease>", self.update_trans_elev_table)
        

        # Longitudinal count (right)
        long_count_inner = ctk.CTkFrame(tier_count_frame)
        long_count_inner.grid(row=0, column=1, padx=(3, 0), sticky="ew")
        ctk.CTkLabel(long_count_inner, text="No. of Longitudinal Levels:").pack(side="left", padx=5)
        self.long_tiers_entry = ctk.CTkEntry(long_count_inner, placeholder_text="2", width=50)
        self.long_tiers_entry.pack(side="right", padx=5)
        self.long_tiers_entry.bind("<KeyRelease>", self.update_long_elev_table)

        # NEW
        elev_split_frame = ctk.CTkFrame(tier_frame)
        elev_split_frame.pack(fill="both", expand=True)
        elev_split_frame.grid_columnconfigure(0, weight=1)
        elev_split_frame.grid_columnconfigure(1, weight=1)

        # Left: Transverse
        trans_elev_frame = ctk.CTkFrame(elev_split_frame)
        trans_elev_frame.grid(row=0, column=0, padx=(0, 3), sticky="nsew")
        ctk.CTkLabel(trans_elev_frame, text="Transverse Elev. (m):", font=ctk.CTkFont(weight="bold")).pack(pady=(0, 5))
        self.trans_beam_elev_table = ctk.CTkScrollableFrame(trans_elev_frame, height=100)
        self.trans_beam_elev_table.pack(fill="both", expand=True)
        self.trans_beam_elev_entries = []

        # Right: Longitudinal
        long_elev_frame = ctk.CTkFrame(elev_split_frame)
        long_elev_frame.grid(row=0, column=1, padx=(3, 0), sticky="nsew")
        ctk.CTkLabel(long_elev_frame, text="Longitudinal Elev. (m):", font=ctk.CTkFont(weight="bold")).pack(pady=(0, 5))
        self.long_beam_elev_table = ctk.CTkScrollableFrame(long_elev_frame, height=100)
        self.long_beam_elev_table.pack(fill="both", expand=True)
        self.long_beam_elev_entries = []
        
        # Initialize tables with default values
        self.update_transverse_table()
        self.update_longitudinal_table()
        self.update_tier_table()

    def update_transverse_table(self, event=None):
        """Update only the transverse spacing table"""
        try:
            # Clear transverse table only
            for widget in self.trans_spacing_table.winfo_children():
                widget.destroy()
            
            self.trans_spacing_entries = []
            
            # Get current transverse count
            num_trans = int(self.trans_grids_entry.get() or 2)
            
            # Create entries for transverse spacing
            for i in range(num_trans):
                frame = ctk.CTkFrame(self.trans_spacing_table)
                frame.pack(fill="x", pady=2)
                ctk.CTkLabel(frame, text=f"Grid {i+1}:").pack(side="left", padx=5)
                entry = ctk.CTkEntry(frame, width=100)
                entry.pack(side="right", padx=5)
                # Default values for transverse spacing
                default_values = [0.0, 6.0, 12.0, 18.0]
                if i < len(default_values):
                    entry.insert(0, str(default_values[i]))
                self.trans_spacing_entries.append(entry)
                
        except ValueError:
            pass  # Ignore invalid input during typing

    def update_longitudinal_table(self, event=None):
        """Update only the longitudinal spacing table"""
        try:
            # Clear longitudinal table only
            for widget in self.long_spacing_table.winfo_children():
                widget.destroy()
            
            self.long_spacing_entries = []
            
            # Get current longitudinal count
            num_long = int(self.long_grids_entry.get() or 4)
            
            # Create entries for longitudinal spacing
            for i in range(num_long):
                frame = ctk.CTkFrame(self.long_spacing_table)
                frame.pack(fill="x", pady=2)
                ctk.CTkLabel(frame, text=f"Grid {i+1}:").pack(side="left", padx=5)
                entry = ctk.CTkEntry(frame, width=100)
                entry.pack(side="right", padx=5)
                # Default values for longitudinal spacing
                default_values = [0.0, 8.0, 16.0, 24.0]
                if i < len(default_values):
                    entry.insert(0, str(default_values[i]))
                self.long_spacing_entries.append(entry)
                
        except ValueError:
            pass  # Ignore invalid input during typing

    # NEW - replace with these three methods
    def update_tier_table(self, event=None):
        """Called on load - refreshes both tables"""
        self.update_trans_elev_table()
        self.update_long_elev_table()

    def update_trans_elev_table(self, event=None):
        try:
            for widget in self.trans_beam_elev_table.winfo_children():
                widget.destroy()
            self.trans_beam_elev_entries = []

            num_trans_tiers = int(self.trans_tiers_entry.get() or 2)
            trans_defaults = [3.0, 6.0, 9.0, 12.0]

            for i in range(num_trans_tiers):
                t_frame = ctk.CTkFrame(self.trans_beam_elev_table)
                t_frame.pack(fill="x", pady=2)
                ctk.CTkLabel(t_frame, text=f"Level {i+1}:").pack(side="left", padx=5)
                t_entry = ctk.CTkEntry(t_frame, width=60)
                t_entry.pack(side="right", padx=5)
                if i < len(trans_defaults):
                    t_entry.insert(0, str(trans_defaults[i]))
                self.trans_beam_elev_entries.append(t_entry)
        except ValueError:
            pass

    def update_long_elev_table(self, event=None):
        try:
            for widget in self.long_beam_elev_table.winfo_children():
                widget.destroy()
            self.long_beam_elev_entries = []

            num_long_tiers = int(self.long_tiers_entry.get() or 2)
            long_defaults = [2.7, 5.7, 8.7, 11.7]

            for i in range(num_long_tiers):
                l_frame = ctk.CTkFrame(self.long_beam_elev_table)
                l_frame.pack(fill="x", pady=2)
                ctk.CTkLabel(l_frame, text=f"Level {i+1}:").pack(side="left", padx=5)
                l_entry = ctk.CTkEntry(l_frame, width=60)
                l_entry.pack(side="right", padx=5)
                if i < len(long_defaults):
                    l_entry.insert(0, str(long_defaults[i]))
                self.long_beam_elev_entries.append(l_entry)
        except ValueError:
            pass

    def setup_advanced_config_tab(self):
        tab = self.tabview.tab("Advanced Configuration")
        tab.grid_columnconfigure(0, weight=1)
        
        # Frame for advanced parameters
        frame = ctk.CTkFrame(tab)
        frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        frame.grid_columnconfigure(1, weight=1)
        
        # Advanced parameters
        ctk.CTkLabel(frame, text="Advanced Parameters", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, columnspan=2, pady=(0, 10), sticky="w")
        
        # Bracing enabled
        self.bracing_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(frame, text="Enable Bracing System", variable=self.bracing_var).grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky="w")
        
        # Support type selection
        ctk.CTkLabel(frame, text="Support Type:").grid(row=2, column=0, padx=5, pady=5, sticky="e")
        self.support_type_var = ctk.StringVar(value="Fixed")
        self.support_type_dropdown = ctk.CTkComboBox(
            frame, 
            values=["Fixed", "Pinned"], 
            variable=self.support_type_var
        )
        self.support_type_dropdown.grid(row=2, column=1, padx=5, pady=5, sticky="ew")
    
    def setup_saved_configs_tab(self):
        tab = self.tabview.tab("Saved Configurations")
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)
        
        # Top frame for controls
        top_frame = ctk.CTkFrame(tab)
        top_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        top_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(top_frame, text="Configuration Name:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.config_name_entry = ctk.CTkEntry(top_frame)
        self.config_name_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        
        save_button = ctk.CTkButton(top_frame, text="Save Current Config", command=self.save_current_config)
        save_button.grid(row=0, column=2, padx=5, pady=5)
        
        # Listbox for saved configs
        self.config_listbox = ctk.CTkScrollableFrame(tab)
        self.config_listbox.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")
        self.config_listbox.grid_columnconfigure(0, weight=1)
        
        # Bottom frame for actions
        bottom_frame = ctk.CTkFrame(tab)
        bottom_frame.grid(row=2, column=0, padx=10, pady=(0, 10), sticky="ew")
        
        load_button = ctk.CTkButton(bottom_frame, text="Load Selected Config", command=self.load_selected_config)
        load_button.pack(side="left", padx=5, pady=5)
        
        delete_button = ctk.CTkButton(bottom_frame, text="Delete Selected Config", command=self.delete_selected_config)
        delete_button.pack(side="left", padx=5, pady=5)
    
    def load_saved_configs(self):
        """Load saved configurations from file"""
        try:
            config_path = get_config_path()
            if config_path.exists():
                with open(config_path, "r") as f:
                    self.saved_configs = json.load(f)
                self.update_config_list()
            else:
                self.saved_configs = []  # Initialize empty list if no config file exists
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load saved configurations: {e}")
            self.saved_configs = []  # Fallback to empty list
    
    def save_configs_to_file(self):
        """Save configurations to file"""
        try:
            config_path = get_config_path()
            with open(config_path, "w") as f:
                json.dump(self.saved_configs, f, indent=2)
            return True
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save configurations: {e}")
            return False
    
    def update_config_list(self):
        """Update the list of saved configurations"""
        # Clear current list
        for widget in self.config_listbox.winfo_children():
            widget.destroy()
        
        # Add each config to the list
        for i, config in enumerate(self.saved_configs):
            frame = ctk.CTkFrame(self.config_listbox)
            frame.pack(fill="x", pady=2)
            frame.grid_columnconfigure(0, weight=1)
            
            label = ctk.CTkLabel(frame, text=config["name"])
            label.grid(row=0, column=0, sticky="w", padx=5, pady=2)
            
            radio = ctk.CTkRadioButton(frame, text="", value=i, variable=self.selected_config_index)
            radio.grid(row=0, column=1, sticky="e", padx=5, pady=2)
    
    def save_current_config(self):
        """Save the current configuration"""
        name = self.config_name_entry.get().strip()
        if not name:
            messagebox.showerror("Error", "Please enter a configuration name")
            return
        
        # Get current config from UI
        config = self.get_current_config()
        if config is None:
            return
        
        config["name"] = name
        
        # Initialize saved_configs if it doesn't exist
        if not hasattr(self, 'saved_configs'):
            self.saved_configs = []
        
        # Check if name already exists
        for i, saved_config in enumerate(self.saved_configs):
            if saved_config["name"] == name:
                self.saved_configs[i] = config
                break
        else:
            self.saved_configs.append(config)
        
        # Save to file and update list
        if not self.save_configs_to_file():
            return
        self.update_config_list()
        messagebox.showinfo("Success", f"Configuration '{name}' saved successfully")
    
    def get_current_config(self):
        """Get current configuration from UI fields with strict validation"""
        try:
            # Get grid counts with minimum validation
            num_transverse = int(self.trans_grids_entry.get() or 2)
            num_longitudinal = int(self.long_grids_entry.get() or 4)
            # NEW
            num_trans_tiers = int(self.trans_tiers_entry.get() or 2)
            num_long_tiers  = int(self.long_tiers_entry.get() or 2)
            
            # Minimum grid count validation
            errors = []
            if num_transverse < 2:
                errors.append("Must have at least 2 transverse grids")
            if num_longitudinal < 2:
                errors.append("Must have at least 2 longitudinal grids")
            # NEW
            if num_trans_tiers < 1:
                errors.append("Must have at least 1 transverse beam level")
            if num_long_tiers < 1:
                errors.append("Must have at least 1 longitudinal beam level")
                
            if errors:
                messagebox.showerror(
                    "Invalid Grid Count",
                    "Cannot generate model:\n\n• " + "\n• ".join(errors))
                return None
            
            # Collect spacing values
            transverse_spacing = []
            for entry in self.trans_spacing_entries:
                val = entry.get().strip()
                if not val:
                    messagebox.showwarning("Empty Value", 
                        "All spacing values must be filled")
                    return None
                transverse_spacing.append(float(val))
            
            longitudinal_spacing = []
            for entry in self.long_spacing_entries:
                val = entry.get().strip()
                if not val:
                    messagebox.showwarning("Empty Value",
                        "All spacing values must be filled")
                    return None
                longitudinal_spacing.append(float(val))
                
            trans_beam_elevations = []
            for entry in self.trans_beam_elev_entries:
                val = entry.get().strip()
                if not val:
                    messagebox.showwarning("Empty Value", "All transverse beam elevations must be filled")
                    return None
                trans_beam_elevations.append(float(val))

            long_beam_elevations = []
            for entry in self.long_beam_elev_entries:
                val = entry.get().strip()
                if not val:
                    messagebox.showwarning("Empty Value", "All longitudinal beam elevations must be filled")
                    return None
                long_beam_elevations.append(float(val))

            numeric_groups = {
                "Transverse grid positions": transverse_spacing,
                "Longitudinal grid positions": longitudinal_spacing,
                "Transverse elevations": trans_beam_elevations,
                "Longitudinal elevations": long_beam_elevations,
            }
            for label, values in numeric_groups.items():
                if any(not math.isfinite(value) for value in values):
                    errors.append(f"{label} must contain finite numbers")
                if any(left >= right for left, right in zip(values, values[1:])):
                    errors.append(f"{label} must be strictly increasing")
            
            # Strict count matching validation
            if len(transverse_spacing) != num_transverse:
                errors.append(f"Need exactly {num_transverse} transverse spacing values (got {len(transverse_spacing)})")
            
            if len(longitudinal_spacing) != num_longitudinal:
                errors.append(f"Need exactly {num_longitudinal} longitudinal spacing values (got {len(longitudinal_spacing)})")
                
            # NEW
            if len(trans_beam_elevations) != num_trans_tiers:
                errors.append(f"Need exactly {num_trans_tiers} transverse beam elevation values (got {len(trans_beam_elevations)})")
            if len(long_beam_elevations) != num_long_tiers:
                errors.append(f"Need exactly {num_long_tiers} longitudinal beam elevation values (got {len(long_beam_elevations)})")
            
            if errors:
                messagebox.showerror(
                    "Validation Failed",
                    "Cannot generate model:\n\n• " + "\n• ".join(errors) +
                    "\n\nPlease correct the input values.")
                return None
                
            # Return config only if all validations pass
            base_elevation = float(self.base_elev_entry.get() or 0.0)
            foundation_depth = float(self.foundation_depth_entry.get() or 1.5)
            if not math.isfinite(base_elevation):
                errors.append("Base elevation must be finite")
            if not math.isfinite(foundation_depth) or foundation_depth <= 0:
                errors.append("Foundation depth must be a finite positive number")
            if errors:
                messagebox.showerror(
                    "Validation Failed",
                    "Cannot generate model:\n\n• " + "\n• ".join(errors),
                )
                return None

            return {
                'num_transverse_grids': num_transverse,
                'num_longitudinal_grids': num_longitudinal,
                'base_elevation': base_elevation,
                'foundation_depth': foundation_depth,
                'transverse_spacing': transverse_spacing,
                'longitudinal_spacing': longitudinal_spacing,
                'num_trans_tiers': num_trans_tiers,
                'num_long_tiers': num_long_tiers,
                'trans_beam_elevations': trans_beam_elevations,
                'long_beam_elevations': long_beam_elevations,
                'bracing_enabled': self.bracing_var.get(),
                'support_type': self.support_type_var.get()
            }
            
        except ValueError as e:
            messagebox.showerror("Invalid Input", f"Please enter valid numbers: {e}")
            return None
    
    def load_selected_config(self):
        """Load a selected configuration"""
        if not hasattr(self, 'saved_configs') or not self.saved_configs:
            messagebox.showerror("Error", "No configurations available to load")
            return
            
        selected_index = self.selected_config_index.get()
        
        if selected_index == -1 or selected_index >= len(self.saved_configs):
            messagebox.showerror("Error", "Please select a configuration to load")
            return
        
        config = self.saved_configs[selected_index]
        
        # Update UI fields
        self.trans_grids_entry.delete(0, "end")
        self.trans_grids_entry.insert(0, str(config['num_transverse_grids']))
        
        self.long_grids_entry.delete(0, "end")
        self.long_grids_entry.insert(0, str(config['num_longitudinal_grids']))
        
        # NEW
        self.trans_tiers_entry.delete(0, "end")
        self.trans_tiers_entry.insert(0, str(config.get('num_trans_tiers', 2)))

        self.long_tiers_entry.delete(0, "end")
        self.long_tiers_entry.insert(0, str(config.get('num_long_tiers', 2)))
        
        self.base_elev_entry.delete(0, "end")
        self.base_elev_entry.insert(0, str(config['base_elevation']))
        
        self.foundation_depth_entry.delete(0, "end")
        self.foundation_depth_entry.insert(0, str(config['foundation_depth']))
        
        # Update the individual tables
        self.update_transverse_table()
        self.update_longitudinal_table()
        self.update_tier_table()
        
        # Fill in the spacing values
        for i, entry in enumerate(self.trans_spacing_entries):
            if i < len(config['transverse_spacing']):
                entry.delete(0, "end")
                entry.insert(0, str(config['transverse_spacing'][i]))
        
        for i, entry in enumerate(self.long_spacing_entries):
            if i < len(config['longitudinal_spacing']):
                entry.delete(0, "end")
                entry.insert(0, str(config['longitudinal_spacing'][i]))
        
        for i, entry in enumerate(self.trans_beam_elev_entries):
            if i < len(config['trans_beam_elevations']):
                entry.delete(0, "end")
                entry.insert(0, str(config['trans_beam_elevations'][i]))

        for i, entry in enumerate(self.long_beam_elev_entries):
            if i < len(config['long_beam_elevations']):
                entry.delete(0, "end")
                entry.insert(0, str(config['long_beam_elevations'][i]))
        
        self.bracing_var.set(config['bracing_enabled'])
        
        # Add support type loading with default fallback
        support_type = config.get('support_type', 'Fixed')
        self.support_type_var.set(support_type)
        
        messagebox.showinfo("Success", f"Configuration '{config['name']}' loaded successfully")
    
    def delete_selected_config(self):
        """Delete the selected configuration"""
        if not hasattr(self, 'saved_configs') or not self.saved_configs:
            messagebox.showerror("Error", "No configurations available to delete")
            return
            
        selected_index = self.selected_config_index.get()
        
        if selected_index == -1 or selected_index >= len(self.saved_configs):
            messagebox.showerror("Error", "Please select a configuration to delete")
            return
        
        config = self.saved_configs[selected_index]
        
        # Confirm deletion
        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete configuration '{config['name']}'?"):
            self.saved_configs.pop(selected_index)
            self.selected_config_index.set(-1)  # Reset selection
            if not self.save_configs_to_file():
                return
            self.update_config_list()
            messagebox.showinfo("Success", f"Configuration '{config['name']}' deleted successfully")
    
    def generate_pipe_rack(self):
        """Generate the pipe rack based on current configuration"""
        config = self.get_current_config()
        if config is None:
            return
        
        # Update status
        self.status_label.configure(text="Generating pipe rack...", text_color="white")
        self.update()
        
        try:
            # Create the pipe rack
            success = self.generator.create_comprehensive_pipe_rack(config)
            
            if success:
                # Verify model was actually created by checking nodes
                if len(self.generator.nodes) > 0:
                    self.status_label.configure(text="Pipe rack generated successfully in new STAAD model!", 
                                              text_color="green")
                    messagebox.showinfo("Success", "Pipe rack generated successfully in STAAD.Pro!")
                else:
                    self.status_label.configure(text="Failed to generate pipe rack", text_color="red")
                    messagebox.showerror("Error", "No model elements were created")
            else:
                self.status_label.configure(text="Failed to generate pipe rack", text_color="red")
                messagebox.showerror("Error", "Failed to generate pipe rack")
                
        except Exception as e:
            self.status_label.configure(text=f"Error: {str(e)}", text_color="red")
            messagebox.showerror("Error", f"An error occurred: {str(e)}")

if __name__ == "__main__":
    root_for_testing = ctk.CTk()
    root_for_testing.withdraw()
    app = PipeRackApp(root_for_testing)
    root_for_testing.mainloop()