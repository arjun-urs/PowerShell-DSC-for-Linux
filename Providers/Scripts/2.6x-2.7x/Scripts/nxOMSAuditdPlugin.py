#!/usr/bin/env python
#============================================================================
# Copyright (C) Microsoft Corporation, All rights reserved.
#============================================================================

import os
import sys
import imp
import codecs
import subprocess
import uuid
import platform

protocol = imp.load_source('protocol', '../protocol.py')
nxDSCLog = imp.load_source('nxDSCLog', '../nxDSCLog.py')

LG = nxDSCLog.DSCLog

LOG_ERROR = 'ERROR'
LOG_INFO = 'INFO'

WORKSPACE_ID_TMPL_STR = "@@WORKSPACE_ID@@"
AGENT_ETC_ROOT = '/etc/opt/microsoft/omsagent'
AGENT_VAR_ROOT = '/var/opt/microsoft/omsagent'
AUOMS_OUTCONF_DIR = '/etc/opt/microsoft/auoms/outconf.d'
AUOMS_PLUGIN_CONF = '/etc/audisp/plugins.d/auoms.conf'
MODULE_RESOURCE_DIR = '/opt/microsoft/omsconfig/modules/nxOMSAuditdPlugin/DSCResources/MSFT_nxOMSAuditdPluginResource'
RESOURCE_OMSAGENT_CONF = MODULE_RESOURCE_DIR + '/conf/auditd_plugin.conf'
RESOURCE_AUOMS_CONF = MODULE_RESOURCE_DIR + '/conf/auoms.conf'
RESOURCE_AUDIT_RULES_V1 = MODULE_RESOURCE_DIR + '/rules/oms-security-audit-v1.rules'
RESOURCE_AUDIT_RULES_V2 = MODULE_RESOURCE_DIR + '/rules/oms-security-audit-v2.rules'

def Set_Marshall(WorkspaceId, Ensure):
    if 'value' in dir(WorkspaceId):
        WorkspaceId = WorkspaceId.value
    WorkspaceId = WorkspaceId.encode('ascii', 'ignore').lower()
    if 'value' in dir(Ensure):
        Ensure = Ensure.value
    Ensure = Ensure.encode('ascii', 'ignore')
    return Set(WorkspaceId, Ensure)

def Test_Marshall(WorkspaceId, Ensure):
    if 'value' in dir(WorkspaceId):
        WorkspaceId = WorkspaceId.value
    WorkspaceId = WorkspaceId.encode('ascii', 'ignore').lower()
    if 'value' in dir(Ensure):
        Ensure = Ensure.value
    Ensure = Ensure.encode('ascii', 'ignore')
    return Test(WorkspaceId, Ensure)

def Get_Marshall(WorkspaceId, Ensure):
    arg_names = list(locals().keys())

    if 'value' in dir(WorkspaceId):
        WorkspaceId = WorkspaceId.value
    WorkspaceId = WorkspaceId.encode('ascii', 'ignore').lower()

    retval = 0
    (retval, Ensure) = Get(WorkspaceId)

    WorkspaceId = protocol.MI_String(WorkspaceId)
    Ensure = protocol.MI_String(Ensure)

    retd = {}
    ld = locals()
    for k in arg_names:
        retd[k] = ld[k]
    return retval, retd

def IsUUID(uuidStr):
    try:
        uuidOut = uuid.UUID(uuidStr)
    except:
        return False
    return str(uuidOut).encode('utf-8') == str(uuidStr).encode('utf-8')

def IsValidWorkspaceId(WorkspaceId):
    if not IsUUID(WorkspaceId):
        return False
    return os.path.isdir(os.path.join(AGENT_VAR_ROOT, WorkspaceId))

def GetTmpDir(WorkspaceId):
    return os.path.join(AGENT_VAR_ROOT, WorkspaceId, "tmp")

def GetAgentConfDir(WorkspaceId):
    return os.path.join(AGENT_ETC_ROOT, WorkspaceId, "conf/omsagent.d")

def GetOMSAgentConfPath(WorkspaceId):
    return os.path.join(GetAgentConfDir(WorkspaceId), "auditd_plugin.conf")

def GetTmpAuomsOutputConfPath(WorkspaceId):
    return os.path.join(GetTmpDir(WorkspaceId), "auoms.conf")

def GetAuomOutputConfPath(WorkspaceId):
    return os.path.join(AUOMS_OUTCONF_DIR, WorkspaceId + ".conf")

def GetTmpAuditRulesPath(WorkspaceId):
    return os.path.join(GetTmpDir(WorkspaceId), "auditd_plugin.rules")

def Set(WorkspaceId, Ensure):
    if not IsValidWorkspaceId(WorkspaceId):
        return [1]

    (audit_version, plugin_state,
     actual_audit_rules, actual_outconf, actual_plugin_conf) = GetState(WorkspaceId)
    if audit_version is None:
        return [1]

    (desired_plugin_state, desired_rules, desired_outconf,
     desired_plugin_conf) = GetDesiredState(WorkspaceId, Ensure, audit_version, plugin_state)
    if desired_plugin_state is None:
        return [1]

    if actual_plugin_conf != desired_plugin_conf:
        if desired_plugin_conf is None:
            RemoveFile(GetOMSAgentConfPath(WorkspaceId))
        else:
            WriteFile(GetOMSAgentConfPath(WorkspaceId), desired_plugin_conf)

    rules_file_path = ""
    if actual_audit_rules != desired_rules:
        if desired_rules is None:
            rules_file_path = "remove"
        else:
            rules_file_path = GetTmpAuditRulesPath(WorkspaceId)
            WriteFile(rules_file_path, desired_rules)

    outconf_name = ""
    outconf_path = ""
    if actual_outconf != desired_outconf:
        if not desired_outconf is None:
            outconf_name = WorkspaceId + ".conf"
            outconf_path = GetTmpAuomsOutputConfPath(WorkspaceId)
            WriteFile(outconf_path, desired_outconf)

    # Run script that will restart omsagent and enable+start/disable+stop auoms
    args = []
    args.append("/usr/bin/sudo")
    args.append("/opt/microsoft/omsconfig/Scripts/OMSAuditdPlugin.sh")
    args.append("set")
    if actual_plugin_conf != desired_plugin_conf:
        args.append("retart")
    else:
        args.append("")
    if plugin_state != desired_plugin_state:
        args.append(desired_plugin_state)
    else:
        args.append("")
    args.append(rules_file_path)
    args.append(outconf_name)
    args.append(outconf_path)
    proc = subprocess.Popen(args, -1, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    exit_code = proc.wait()
    if exit_code != 0:
        out_txt = proc.stdout.read().decode('utf8', 'replace').encode('utf8', 'replace')
        err_txt = proc.stderr.read().decode('utf8', 'replace').encode('utf8', 'replace')
        LG().Log(LOG_INFO, "stdout: " + out_txt)
        LG().Log(LOG_INFO, "stderr: " + err_txt)

    RemoveFile(GetTmpAuomsOutputConfPath(WorkspaceId))
    RemoveFile(GetTmpAuditRulesPath(WorkspaceId))

    return [exit_code]

def Test(WorkspaceId, Ensure):
    if not IsValidWorkspaceId(WorkspaceId):
        # Failed to determine state, return fake success
        return [0]

    state = GetEnsure(WorkspaceId)
    if state is None:
        # Failed to determine state, return fake success
        return [0]
    else:
        if state == Ensure:
            return [0]
        else:
            return [-1]

def Get(WorkspaceId):
    if not IsValidWorkspaceId(WorkspaceId):
        return (-1, "Absent")

    state = GetEnsure(WorkspaceId)
    if state is None:
        return (-1, "Absent")
    else:
        return (0, state)

def GetOtherOutconfCounts(WorkspaceId):
    tcount = 0
    wcount = 0
    for name in os.listdir(AUOMS_OUTCONF_DIR):
        if name.endswith(".conf"):
            if name != WorkspaceId + ".conf":
                tcount += 1
                if IsValidWorkspaceId(name[:-5]):
                    wcount += 1
    return (tcount, wcount)

def GetDesiredAuditRules(AuditVersion):
    if AuditVersion == 1:
        desired_rules = ReadFile(RESOURCE_AUDIT_RULES_V1)
    else:
        desired_rules = ReadFile(RESOURCE_AUDIT_RULES_V2)

    if platform.machine() != "x86_64" and desired_rules != None:
        lines = desired_rules.split("\n")
        new_lines = []
        for line in lines:
            if not 'b64' in line:
                new_lines.append(line)
        desired_rules = "\n".join(lines)
    return desired_rules

def GetDesiredState(WorkspaceId, Ensure, AuditVersion, CurrentPluginState):
    desired_plugin_state = "no"
    desired_rules = None
    desired_outconf = None
    desired_plugin_conf = None

    (other_conf_count, other_ws_conf_count) = GetOtherOutconfCounts(WorkspaceId)

    if Ensure == "Present":
        desired_plugin_state = "yes"
        desired_rules = GetDesiredAuditRules(AuditVersion)
        desired_outconf = ReadFile(RESOURCE_AUOMS_CONF)
        desired_plugin_conf = ReadFile(RESOURCE_OMSAGENT_CONF)

        if desired_rules is None or desired_outconf is None or desired_plugin_conf is None:
            # Failed to determine state
            return (None, None, None, None)

        desired_outconf = desired_outconf.replace(WORKSPACE_ID_TMPL_STR, WorkspaceId)
        desired_plugin_conf = desired_plugin_conf.replace(WORKSPACE_ID_TMPL_STR, WorkspaceId)
    else:
        if other_conf_count > 0:
            if other_ws_conf_count > 0:
                # There are other workspace outconfs present, so the desired state is "yes"
                desired_plugin_state = "yes"
            else:
                # If the only other outconfs are non-OMS, then we don't
                # want to change the auoms plugin state
                desired_plugin_state = CurrentPluginState
        # If there are any other workspaces with auoms outconf files, then
        # we don't want to remove the audit rules
        if other_ws_conf_count > 0:
            desired_rules = GetDesiredAuditRules(AuditVersion)

    return (desired_plugin_state, desired_rules, desired_outconf, desired_plugin_conf)

def GetEnsure(WorkspaceId):
    (audit_version, plugin_state,
     actual_audit_rules, actual_outconf, actual_plugin_conf) = GetState(WorkspaceId)
    if audit_version is None:
        return None

    Ensure = "Absent"
    if (not actual_audit_rules is None or
            not actual_outconf is None or
            not actual_plugin_conf is None):
        Ensure = "Present"

    (desired_plugin_state, desired_rules, desired_outconf,
     desired_plugin_conf) = GetDesiredState(WorkspaceId, Ensure, audit_version, plugin_state)
    if desired_plugin_state is None:
        return None

    if (desired_plugin_state != plugin_state or
            desired_rules != actual_audit_rules or
            desired_outconf != actual_outconf or
            desired_plugin_conf != actual_plugin_conf):
        return "Absent"
    else:
        return "Present"

def GetState(WorkspaceId):
    args = []
    args.append("/usr/bin/sudo")
    args.append("/opt/microsoft/omsconfig/Scripts/OMSAuditdPlugin.sh")
    args.append("get")
    args.append(GetTmpDir(WorkspaceId))
    proc = subprocess.Popen(args, -1, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    exit_code = proc.wait()
    out_txt = proc.stdout.read().decode('utf8', 'replace').encode('utf8', 'replace')
    if exit_code != 0:
        err_txt = proc.stderr.read().decode('utf8', 'replace').encode('utf8', 'replace')
        LG().Log(LOG_INFO, "stdout: " + out_txt)
        LG().Log(LOG_INFO, "stderr: " + err_txt)
        return (None, None, None, None, None)

    audit_version = 2
    parts = out_txt.strip().split(".")
    if len(parts) >= 2:
        if parts[0] == "1" and int(parts[1]) < 8:
            audit_version = 1
    else:
        LG().Log(LOG_INFO, "Invalid version string returned from 'OMSAuditdPlugin.sh version'")
        return (None, None, None, None, None)

    state_file = os.path.join(GetTmpDir(WorkspaceId), "auditd_plugin.state")
    rules_file = os.path.join(GetTmpDir(WorkspaceId), "auditd_plugin.rules")
    plugin_state = ReadFile(state_file)
    audit_rules = ReadFile(rules_file)
    RemoveFile(state_file)
    RemoveFile(rules_file)
    if audit_rules != None and audit_rules.strip() == "":
        audit_rules = None

    actual_outconf = ReadFile(GetAuomOutputConfPath(WorkspaceId))
    actual_plugin_conf = ReadFile(GetOMSAgentConfPath(WorkspaceId))

    return (audit_version, plugin_state, audit_rules, actual_outconf, actual_plugin_conf)

def ReadFile(Path):
    if not os.path.isfile(Path):
        return None
    return codecs.open(Path, 'r', 'utf8').read().encode('ascii', 'ignore')

def WriteFile(Path, Text):
    codecs.open(Path, 'w', 'utf8').write(Text)

def RemoveFile(Path):
    if os.path.isfile(Path):
        os.remove(Path)
