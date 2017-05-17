#!/usr/bin/env python
#============================================================================
# Copyright (C) Microsoft Corporation, All rights reserved.
#============================================================================

import os
import imp
import re
import codecs
from functools import reduce
protocol = imp.load_source('protocol', '../protocol.py')
nxDSCLog = imp.load_source('nxDSCLog', '../nxDSCLog.py')

LG = nxDSCLog.DSCLog

rsyslog_conf_path = '/etc/rsyslog.conf'
rsyslog_inc_conf_path = '/etc/rsyslog.d/95-omsagent.conf'
syslog_ng_conf_path = '/etc/syslog-ng/syslog-ng.conf'
sysklog_conf_path='/etc/syslog.conf'
oms_syslog_ng_conf_path = '/etc/opt/omi/conf/omsconfig/syslog-ng-oms.conf'
oms_rsyslog_conf_path = '/etc/opt/omi/conf/omsconfig/rsyslog-oms.conf'
conf_path = ''
default_port = '25224'


def init_vars(SyslogSource, WorkspaceID):
    """
    Initialize global variables for this resource
    """
    global conf_path

    for source in SyslogSource:
        if source['Severities'] is not None:
            if 'value' in dir(source['Severities']):
                source['Severities'] = source['Severities'].value
        if 'value' in dir(source['Facility']):
            source['Facility'] = source['Facility'].value
    if os.path.exists(rsyslog_conf_path):
        conf_path = oms_rsyslog_conf_path
    elif os.path.exists(syslog_ng_conf_path):
        conf_path = oms_syslog_ng_conf_path
    else:
        LG().Log('ERROR', 'Unable to find OMS config files.')
        raise Exception('Unable to find OMS config files.')
    LG().Log('INFO', 'Config file is ' + conf_path + '.')


def Set_Marshall(SyslogSource, WorkspaceID):
    """
    Set the syslog conf for specified workspace on the machine
    """
    if os.path.exists(sysklog_conf_path):
        LG().Log('ERROR', 'Sysklogd is unsupported.')
        return [0]

    init_vars(SyslogSource, WorkspaceID)
    retval = Set(SyslogSource, WorkspaceID)

    if retval is False:
        retval = [-1]
    else:
        retval = [0]
    return retval


def Test_Marshall(SyslogSource, WorkspaceID):
    """
    Test if the syslog conf for specified workspace matches the provided conf
    """
    if os.path.exists(sysklog_conf_path):
        LG().Log('ERROR', 'Sysklogd is unsupported.')
        return [0]

    init_vars(SyslogSource, WorkspaceID)
    return Test(SyslogSource, WorkspaceID)


def Get_Marshall(SyslogSource, WorkspaceID):
    """
    Get the syslog conf for specified workspace from the machine and update
    the parameters
    """
    if os.path.exists(sysklog_conf_path):
        LG().Log('ERROR', 'Sysklogd is unsupported.')
        return 0, {'SyslogSource':protocol.MI_InstanceA([])}

    arg_names = list(locals().keys())
    init_vars(SyslogSource, WorkspaceID)
    retval = 0
    NewSource = Get(SyslogSource, WorkspaceID)
    for source in NewSource:
        if source['Severities'] is not None:
            source['Severities'] = protocol.MI_StringA(source['Severities'])
        source['Facility'] = protocol.MI_String(source['Facility'])
    SyslogSource = protocol.MI_InstanceA(NewSource)
    WorkspaceID = protocol.MI_String(WorkspaceID)

    retd = {}
    ld = locals()
    for k in arg_names:
        retd[k] = ld[k]
    return retval, retd


def Set(SyslogSource, WorkspaceID):
    """
    Set the syslog conf for specified workspace on the machine
    """
    if Test(SyslogSource, WorkspaceID) == [0]:
        return [0]

    if conf_path == oms_syslog_ng_conf_path:
        ret = UpdateSyslogNGConf(SyslogSource, WorkspaceID)
    else:
        ret = UpdateSyslogConf(SyslogSource, WorkspaceID)

    if ret:
        ret = [0]
    else:
        ret = [-1]
    return ret


def Test(SyslogSource, WorkspaceID):
    """
    Test if the syslog conf for specified workspace matches the provided conf
    """
    if conf_path == oms_syslog_ng_conf_path:
        NewSource = ReadSyslogNGConf(SyslogSource, WorkspaceID)
    else:
        NewSource = ReadSyslogConf(SyslogSource, WorkspaceID)

    SyslogSource=sorted(SyslogSource, key=lambda k: k['Facility'])
    for d in SyslogSource:
        found = False
        if ('Severities' not in d.keys() or d['Severities'] is None 
                or len(d['Severities']) is 0):
            d['Severities'] = ['none']

        d['Severities'].sort()

    NewSource=sorted(NewSource, key=lambda k: k['Facility'])
    for n in NewSource:
        n['Severities'].sort()
    if SyslogSource != NewSource:
        return [-1]
    return [0]


def Get(SyslogSource, WorkspaceID):
    """
    Get the syslog conf for specified workspace from the machine
    """
    if conf_path == oms_syslog_ng_conf_path:
        NewSource = ReadSyslogNGConf(SyslogSource, WorkspaceID)
    else:
        NewSource = ReadSyslogConf(SyslogSource, WorkspaceID)

    for d in NewSource:
        if d['Severities'] == ['none']:
            d['Severities'] = []
    return NewSource


def ReadSyslogConf(SyslogSource, WorkspaceID):
    """
    Read syslog conf file in rsyslog format for specified workspace and
    return the relevant facilities and severities
    """
    out = []
    txt = ''
    if len(SyslogSource) is 0:
        return out
    if not os.path.exists('/etc/rsyslog.d'):
        try:
            txt = codecs.open(rsyslog_conf_path, 'r', 'utf8').read()
            LG().Log('INFO', 'Successfully read ' + rsyslog_conf_path + '.')
        except:
            LG().Log('ERROR', 'Unable to read ' + rsyslog_conf_path + '.')
    else:
        src_conf_path = conf_path
        if os.path.exists(rsyslog_inc_conf_path):
            src_conf_path = rsyslog_inc_conf_path
        try:
            txt = codecs.open(src_conf_path, 'r', 'utf8').read()
            LG().Log('INFO', 'Successfully read ' + src_conf_path + '.')
        except:
            LG().Log('ERROR', 'Unable to read ' + src_conf_path + '.')
            return out

    # Find all lines sending to this workspace's port
    port = ExtractPortFromFluentDConf(WorkspaceID)
    facility_search = r'^[^#](.*?)@.*?' + port + '$'
    facility_re = re.compile(facility_search, re.M)
    for line in facility_re.findall(txt):
        l = line.replace('=', '')
        l = l.replace('\t', '').split(';')
        sevs = []
        fac = l[0].split('.')[0]
        for sev in l:
            sevs.append(sev.split('.')[1])
        out.append({'Facility': fac, 'Severities': sevs})
    return out


def UpdateSyslogConf(SyslogSource, WorkspaceID):
    """
    Update syslog conf file in rsyslog format with specified facilities and
    severities for the specified workspace
    """
    arg = ''
    if 'rsyslog' in conf_path:
        if os.path.exists('/etc/rsyslog.d'):
            txt = ''
        elif os.path.exists(rsyslog_conf_path):
            arg = '1'
            try:
                txt = codecs.open(rsyslog_conf_path, 'r', 'utf8').read()
                LG().Log('INFO', 'Successfully read ' + rsyslog_conf_path + \
                                 '.')
            except:
                LG().Log('ERROR', 'Unable to read ' + rsyslog_conf_path + '.')

    # Remove all lines related to this workspace ID (correlated by port)
    port = ExtractPortFromFluentDConf(WorkspaceID)
    workspace_comment = GetSyslogConfMultiHomedHeaderString(WorkspaceID)
    workspace_comment_search = r'^' + workspace_comment + '.*$'
    workspace_comment_re = re.compile(workspace_comment_search, re.M)
    txt = workspace_comment_re.sub('', txt)

    workspace_port_search = r'(#facility.*?\n.*?' + port + '\n)|(^[^#].*?' \
                        + port + '\n)'
    workspace_port_re = re.compile(workspace_port_search, re.M)
    for group in workspace_port_re.findall(txt):
        for match in group:
            txt = txt.replace(match, '')

    # Append conf lines for this workspace
    txt += workspace_comment + '\n'
    for d in SyslogSource:
        facility_txt = ''
        for s in d['Severities']:
            facility_txt += d['Facility'] + '.=' + s + ';'
        facility_txt = facility_txt[0:-1] + '\t@127.0.0.1:' + port + '\n'
        txt += facility_txt

    # Write the new complete txt to the conf file
    try:
        codecs.open(conf_path, 'w', 'utf8').write(txt)
        LG().Log('INFO', 'Created omsagent rsyslog configuration at ' + \
                         conf_path + '.')
    except:
        LG().Log('ERROR', 'Unable to create omsagent rsyslog configuration ' \
                          'at ' + conf_path + '.')
        return False

    if os.system('sudo /opt/microsoft/omsconfig/Scripts/OMSRsyslog.post.sh ' \
                 + arg) is 0:
        LG().Log('INFO', 'Successfully executed OMSRsyslog.post.sh.')
    else:
        LG().Log('ERROR', 'Error executing OMSRsyslog.post.sh.')
        return False
    return True


def ReadSyslogNGConf(SyslogSource, WorkspaceID):
    """
    Read syslog conf file in syslog-ng format for specified workspace and
    return the relevant facilities and severities
    """
    out = []
    txt = ''
    try:
        txt = codecs.open(syslog_ng_conf_path, 'r', 'utf8').read()
        LG().Log('INFO', 'Successfully read ' + syslog_ng_conf_path + '.')
    except:
        LG().Log('ERROR', 'Unable to read ' + syslog_ng_conf_path + '.')
        return out

    # Check first if there are conf lines labelled with this workspace ID
    workspace_id_search = r'^filter f_.*' + WorkspaceID + '_oms'
    workspace_id_re = re.compile(workspace_id_search, re.M)
    workspace_found = workspace_id_re.search(txt)

    if workspace_found:
        facility_re = ParseSyslogNGConfMultiHomed(txt, WorkspaceID)
    else:
        facility_re = ParseSyslogNGConf(txt)

    for s in facility_re.findall(txt):
        sevs = []
        if len(s[1]):
            if ',' in s[1]:
                sevs = s[1].split(',')
            else:
                sevs.append(s[1])
        out.append({'Facility': s[0], 'Severities': sevs})
    return out


def UpdateSyslogNGConf(SyslogSource, WorkspaceID):
    """
    Update syslog conf file in syslog-ng format with specified facilities and
    severities for the specified workspace
    """
    txt = ''
    try:
        txt = codecs.open(syslog_ng_conf_path, 'r', 'utf8').read()
        LG().Log('INFO', 'Successfully read ' + syslog_ng_conf_path + '.')
    except:
        LG().Log('ERROR', 'Unable to read ' + syslog_ng_conf_path + '.')
        return False

    # Extract the correct source from the conf file
    source_search = r'^source (.*?src).*$'
    source_re = re.compile(source_search, re.M)
    source_result = source_re.search(txt)
    source_expr = 'src'
    if source_result:
        source_expr = source_result.group(1)

    port = ExtractPortFromFluentDConf(WorkspaceID)

    # Remove all lines related to this workspace ID/port
    workspace_comment = '#OMS Workspace ' + WorkspaceID
    workspace_comment_search = r'(\n+)?(' + workspace_comment + '.*$)'
    workspace_comment_re = re.compile(workspace_comment_search, re.M)
    txt = workspace_comment_re.sub('', txt)

    workspace_search = r'(\n+)?(destination.*' + WorkspaceID + '_oms.*\n)?' \
                        '(\n)*filter.*' + WorkspaceID + '_oms.*\n' \
                        '(destination.*' + WorkspaceID + '_oms.*\n)?log.*'
    workspace_re = re.compile(workspace_search)
    txt = workspace_re.sub('', txt)

    port_search = r'(^.*oms.*port\(' + port + '\).*$)'
    port_re = re.compile(port_search, re.M)
    txt = port_re.sub('', txt)

    # Remove all OMS-related lines not marked with a workspace ID
    non_mh_search = r'(\n+)?(#OMS_Destination\ndestination.*_oms.*\n)?(\n)*' \
                     '#OMS_facility.*\nfilter.*_oms.*\n(destination.*_oms.*' \
                     '\n)?log.*'
    non_mh_re = re.compile(non_mh_search)
    txt = non_mh_re.sub('', txt)

    destination_comment_search = r'(\n+)?#OMS_Destination$'
    destination_comment_re = re.compile(destination_comment_search, re.M)
    txt = destination_comment_re.sub('', txt)

    facility_comment_search = r'(\n+)?#OMS_facility = .*$'
    facility_comment_re = re.compile(facility_comment_search, re.M)
    txt = facility_comment_re.sub('', txt)

    # Append conf lines for this workspace
    destination_str = 'd_' + WorkspaceID + '_oms'
    txt += '\n\n' + workspace_comment + ' Destination\ndestination ' \
           + destination_str + ' { udp("127.0.0.1" port(' + port + ')); };\n'
    for d in SyslogSource:
        if ('Severities' in d.keys() and d['Severities'] is not None
                and len(d['Severities']) > 0):
            facility_txt = '\n' + workspace_comment + ' Facility = ' \
                           + d['Facility'] + '\n'
            sevs = reduce(lambda x, y: x + ',' + y, d['Severities'])
            filter_str = 'f_' + d['Facility'] + '_' + WorkspaceID + '_oms'
            facility_txt += 'filter ' + filter_str + ' { level(' + sevs \
                            + ') and facility(' + d['Facility'] + '); };\n'
            facility_txt += 'log { source(' + source_expr + '); filter(' \
                            + filter_str + '); destination(' \
                            + destination_str + '); };\n'
            txt += facility_txt

    # Write the new complete txt to the conf file
    try:
        codecs.open(conf_path, 'w', 'utf8').write(txt)
        LG().Log('INFO', 'Created omsagent syslog-ng configuration at ' + \
                         conf_path + '.')
    except:
        LG().Log('ERROR', 'Unable to create omsagent syslog-ng configuration ' \
                          'at ' + conf_path + '.')
        return False

    if os.system('sudo /opt/microsoft/omsconfig/Scripts/' \
                 'OMSSyslog-ng.post.sh') is 0:
        LG().Log('INFO', 'Successfully executed OMSSyslog-ng.post.sh.')
    else:
        LG().Log('ERROR', 'Error executing OMSSyslog-ng.post.sh.')
        return False

    return True


def GetSyslogConfMultiHomedHeaderString(WorkspaceID):
    """
    Return the header for the multi-homed section from an rsyslog conf file
    """
    return '# OMS Syslog collection for workspace ' + WorkspaceID


def ExtractPortFromFluentDConf(WorkspaceID)
    """
    Returns the port used for this workspace's syslog collection from the
    FluentD configuration file:
    If multi-homed:
    /etc/opt/microsoft/omsagent/<workspace-ID>/conf/omsagent.d/syslog.conf
    if not multi-homed:
    /etc/opt/microsoft/omsagent/conf/omsagent.conf
    """
    omsagent_dir = '/etc/opt/microsoft/omsagent/'
    fluentd_syslog_conf = 'conf/omsagent.d/syslog.conf'
    fluentd_omsagent_conf = 'conf/omsagent.conf'
    if os.path.exists(omsagent_dir + WorkspaceID + '/' + fluentd_syslog_conf):
        port_path = omsagent_dir + WorkspaceID + '/' + fluentd_syslog_conf
    elif os.path.exists(omsagent_dir + fluentd_omsagent_conf):
        port_path = omsagent_dir + fluentd_omsagent_conf
    else:
        LG().Log('ERROR', 'No FluentD syslog configuration found: using ' \
                          'default syslog port ' + default_port + '.')
        return default_port

    try:
        txt = codecs.open(port_path, 'r', 'utf8').read()
    except:
        LG().Log('ERROR', 'Unable to read ' + port_path + ': using default ' \
                          'syslog port ' + default_port + '.')
        return default_port

    port_search = r'^<source>.*type syslog[^#]*port ([0-9]*)\n.*</source>$'
    port_re = re.compile(port_search, re.M | re.S)
    port_result = port_re.search(txt)
    if port_result:
        port = str(port_result.group(1))
    else:
        LG().Log('ERROR', 'No port found in ' + port_path + ': using ' \
                          'default syslog port ' + default_port + '.')
        port = default_port
    return port


def ParseSyslogNGConfMultiHomed(txt, WorkspaceID):
    """
    Returns a search to extract facilities and severities for the specified
    workspace for syslog-ng format
    """
    facility_search = r'^filter f_(?P<facility>.*?)_' + WorkspaceID + '_oms.*?level\((?P<severities>.*?)\)'
    return re.compile(facility_search, re.M)


def ParseSyslogNGConf(txt):
    """
    Returns a search to extract facilities and severities for the default
    workspace for syslog-ng format
    """
    facility_search = r'^filter f_(?P<facility>.*?)_oms.*?level' \
                       '\((?P<severities>.*?)\)'
    return re.compile(facility_search, re.M)
