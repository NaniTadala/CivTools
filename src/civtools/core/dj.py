import comtypes
import comtypes.client
from comtypes import automation
import ctypes
from .callbacks import ServiceCallbacks
from .cad import connect_staad

def make_safe_array_double(size):
    return automation._midlSAFEARRAY(ctypes.c_double).create([0] * size)

def make_safe_array_int(size):
    return automation._midlSAFEARRAY(ctypes.c_int).create([0] * size)

def make_safe_array_long(size):
    return automation._midlSAFEARRAY(ctypes.c_long).create([0] * size)

def make_variant_vt_ref(obj, var_type):
    var = automation.VARIANT()
    var._.c_void_p = ctypes.addressof(obj)
    var.vt = var_type | automation.VT_BYREF
    return var

DESIGN_CODES = {'AISC 360-05': 1045, 'AISC 360-10': 1061, 'AISC 360-16': 1067, 'AISC': 1002, 'IS800 LSD': 1032, 'IS800 WSD': 1052, 'IS800 1984': 1009}

class DJService(ServiceCallbacks):

    def connect_to_staad(self):
        """Connect to STAAD Pro using comtypes with proper error handling"""
        self.log_message('Connecting to STAAD Pro...')
        try:
            staad, model_name = connect_staad()
            self.report("target", model_name)
            self.log_message(f'Connected to STAAD model: {model_name}')
            return staad
        except Exception as e:
            error_msg = f'Failed to connect to STAAD Pro: {str(e)}\n\nEnsure STAAD.Pro CONNECT Edition is running and model is open\n'
            self.log_error(error_msg)
            return None

    def assign_dj_parameters(self, config):
        """Main function to assign DJ parameters using COM automation"""
        try:
            self.log_message('Starting DJ parameter assignment...')
            self.update_progress(0.1)
            staad = self.connect_to_staad()
            if not staad:
                return
            try:
                code = DESIGN_CODES.get(config['design_code'], 1032)
                self.update_progress(0.3)
                geometry = staad.Geometry
                prop = staad.Property
                design = staad.Design
                geometry._FlagAsMethod('GetPhysicalMemberCount')
                geometry._FlagAsMethod('GetPhysicalMemberList')
                geometry._FlagAsMethod('GetAnalyticalMemberCountForPhysicalMember')
                geometry._FlagAsMethod('GetAnalyticalMembersForPhysicalMember')
                geometry._FlagAsMethod('GetMemberIncidence')
                prop._FlagAsMethod('GetBeamMaterialName')
                design._FlagAsMethod('CreateDesignBrief')
                design._FlagAsMethod('GetDesignBriefCode')
                design._FlagAsMethod('AssignDesignParameter')
                pcnt = geometry.GetPhysicalMemberCount()
                if pcnt == 0:
                    self.log_error('No physical members found in the model')
                    return
                self.log_message(f'Found {pcnt} physical members')
                self.update_progress(0.4)
                safe_array_pmem = make_safe_array_long(pcnt)
                pmem = make_variant_vt_ref(safe_array_pmem, automation.VT_ARRAY | automation.VT_I4)
                geometry.GetPhysicalMemberList(pmem)
                processed_count = 0
                brf = 0
                self.log_message('Starting member processing...')
                self.update_progress(0.5)
                if config['brief_option'] == 'Existing':
                    try:
                        brf = config['existing_brief_number']
                        codx = design.GetDesignBriefCode(brf)
                        if codx == 0:
                            self.log_error(f'Design Parameter {brf} not available in model')
                            return
                        existing_code_name = 'Unknown'
                        for (name, code_num) in DESIGN_CODES.items():
                            if code_num == codx:
                                existing_code_name = name
                                break
                        self.log_message(f'Using existing design brief: {brf} (Code: {existing_code_name} - {codx})')
                    except Exception as e:
                        self.log_error(f'Error checking existing brief: {str(e)}')
                        return
                else:
                    self.log_message(f"Using design code: {config['design_code']} (Code: {code})")
                for j in range(pcnt):
                    current_pmem = pmem[0][j]
                    anln = geometry.GetAnalyticalMemberCountForPhysicalMember(current_pmem)
                    if anln == 0:
                        continue
                    safe_array_selb = make_safe_array_long(anln)
                    selb = make_variant_vt_ref(safe_array_selb, automation.VT_ARRAY | automation.VT_I4)
                    anl = ctypes.c_long(0)
                    anl_vt = make_variant_vt_ref(anl, automation.VT_I4)
                    geometry.GetAnalyticalMembersForPhysicalMember(current_pmem, anl_vt, selb)
                    if config['member_selection'] == 'All Member with Material':
                        if anln > 0:
                            try:
                                mat1 = prop.GetBeamMaterialName(selb[0][0])
                                if mat1 != config['material_filter']:
                                    continue
                            except:
                                continue
                    processed_count += 1
                    node_a = ctypes.c_long(0)
                    node_b = ctypes.c_long(0)
                    node_a_vt = make_variant_vt_ref(node_a, automation.VT_I4)
                    node_b_vt = make_variant_vt_ref(node_b, automation.VT_I4)
                    geometry.GetMemberIncidence(selb[0][0], node_a_vt, node_b_vt)
                    dj1_value = float(node_a.value)
                    geometry.GetMemberIncidence(selb[0][anln - 1], node_a_vt, node_b_vt)
                    dj2_value = float(node_b.value)
                    if config['brief_option'] == 'New':
                        if brf == 0:
                            brf = design.CreateDesignBrief(code)
                            self.log_message(f'Created new design brief: {brf}')
                    design.AssignDesignParameter(brf, 'DJ1', dj1_value, selb)
                    design.AssignDesignParameter(brf, 'DJ2', dj2_value, selb)
                    progress = 0.5 + 0.5 * (j + 1) / pcnt
                    self.update_progress(progress)
                    if (j + 1) % 10 == 0 or j + 1 == pcnt:
                        self.report("stage", f'Assigning members: {j + 1} / {pcnt}')
                self.processed_count = processed_count
                if config['member_selection'] == 'All Member with Material':
                    if processed_count == 0:
                        self.log_error(f"No members with material '{config['material_filter']}'")
                    else:
                        self.log_success(f"Assigned to {processed_count} members with material '{config['material_filter']}'")
                else:
                    self.log_success(f'Assigned to {processed_count} members')
                self.update_progress(1.0)
            except Exception as e:
                self.log_error(f'COM Error: {str(e)}')
                import traceback
                self.log_message(traceback.format_exc())
            finally:
                if 'staad' in locals():
                    staad = None
        except Exception as e:
            self.log_error(f'Process Error: {str(e)}')
