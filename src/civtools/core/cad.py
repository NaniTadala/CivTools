"""STAAD connection checks shared by the engineering services."""
import ctypes
from comtypes import BSTR, automation, client


def staad_model_name(staad):
    name = BSTR()
    argument = automation.VARIANT()
    argument._.c_void_p = ctypes.addressof(name)
    argument.vt = automation.VT_BSTR | automation.VT_BYREF
    staad._FlagAsMethod("GetSTAADFile")
    staad.GetSTAADFile(argument, True)
    if not name.value:
        raise RuntimeError("Open and save the intended STAAD model first.")
    return name.value


def connect_staad():
    try:
        staad = client.GetActiveObject("StaadPro.OpenSTAAD")
        return staad, staad_model_name(staad)
    except Exception as error:
        raise RuntimeError(f"Cannot connect to an open STAAD model: {error}") from error


def require_empty_model(geometry):
    for name in ("GetNodeCount", "GetMemberCount"):
        geometry._FlagAsMethod(name)
    try:
        nodes, members = int(geometry.GetNodeCount()), int(geometry.GetMemberCount())
    except Exception as error:
        raise RuntimeError("Could not verify that the STAAD model is empty. No geometry was added.") from error
    if nodes < 0 or members < 0:
        raise RuntimeError("STAAD returned invalid model counts. No geometry was added.")
    if nodes or members:
        raise RuntimeError(f"Use a blank STAAD model. The active model has {nodes:,} nodes and {members:,} members; no geometry was added.")
