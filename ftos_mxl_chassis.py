#!/usr/bin/env python
#
# @descr    Checks chassis status of FTOS switches
#
# @author   Johan Hedberg <jh@citynetwork.se>
#

import sys
import argparse
from lib.cnh_nm import STATE_OK, STATE_CRIT, STATE_WARN
from lib.cnh_nm import trigger_not_ok, check_if_ok, my_snmp_get, my_snmp_walk, my_snmp_get_int
from lib.cnh_nm import dell_parse_snmp_uptime, snmpresult_to_dict

# Argument parsing
parser = argparse.ArgumentParser(description='Check FTOS environmental status')
parser.add_argument('-C', metavar='<community>', required=True,
                    help='SNMP Community')
parser.add_argument('-H', metavar='<host>', required=True,
                    help='Host to check')
args = parser.parse_args()


# Vars
uptime_crit = 600
uptime_warn = 1800
cpu_usage_warn_percent = 85
cpu_usage_crit_percent = 95
mem_usage_warn_percent = 75
mem_usage_crit_percent = 90

oid_device_type = 'DELL-NETWORKING-CHASSIS-MIB::dellNetDeviceType.0'
oid_stack_num_units = 'DELL-NETWORKING-CHASSIS-MIB::dellNetNumStackUnits.0'
oids_stack_status = [
    'DELL-NETWORKING-CHASSIS-MIB::dellNetStackUnitNumber',
    'DELL-NETWORKING-CHASSIS-MIB::dellNetStackUnitStatus',
    'DELL-NETWORKING-CHASSIS-MIB::dellNetStackUnitUpTime'
]
oid_mgmt_status = 'DELL-NETWORKING-CHASSIS-MIB::dellNetStackUnitMgmtStatus.{}'
oid_num_psus = 'DELL-NETWORKING-CHASSIS-MIB::dellNetStackUnitNumPowerSupplies.{}'
oid_num_fans = 'DELL-NETWORKING-CHASSIS-MIB::dellNetStackUnitNumFanTrays.{}'

# Does not work with symbolic oids in easysnmp (but it does work with commandline snmpget)
oid_psu_oper = '.1.3.6.1.4.1.6027.3.26.1.4.6.1.4.2.{}.{}'  # dellNetPowerSupplyOperStatus
oid_fans_oper = '.1.3.6.1.4.1.6027.3.26.1.4.7.1.4.2.{}.{}'  # dellNetFanTrayOperStatus
oid_mem_usage = '.1.3.6.1.4.1.6027.3.26.1.4.4.1.6.2.{}.1'  # dellNetCpuUtilMemUsage
oid_cpu_usage = '.1.3.6.1.4.1.6027.3.26.1.4.4.1.4.2.{}.1'  # dellNetCpuUtil1Min

# Oids for devices with older firmware
f10_oid_stack_num_units = 'F10-M-SERIES-CHASSIS-MIB::chNumStackUnits.0'
f10_oids_stack_status = [
    'F10-M-SERIES-CHASSIS-MIB::chStackUnitNumber',
    'F10-M-SERIES-CHASSIS-MIB::chStackUnitStatus',
    'F10-M-SERIES-CHASSIS-MIB::chStackUnitUpTime'
]
f10_oid_mgmt_status = 'F10-M-SERIES-CHASSIS-MIB::chStackUnitMgmtStatus.{}'
f10_oid_num_psus = 'F10-M-SERIES-CHASSIS-MIB::chStackUnitNumPowerSupplies.{}'
f10_oid_num_fans = 'F10-M-SERIES-CHASSIS-MIB::chStackUnitNumFanTrays.{}'
f10_oid_psu_oper = 'F10-M-SERIES-CHASSIS-MIB::chSysPowerSupplyOperStatus.{}.{}'
f10_oid_fans_oper = 'F10-M-SERIES-CHASSIS-MIB::chSysFanTrayOperStatus.{}.{}'


# Checking system firmware type
device_type = my_snmp_get(args, oid_device_type)
if device_type.value == u'NOSUCHOBJECT' or device_type.value == u'NOSUCHINSTANCE':
    f10 = True
    oid_stack_num_units = f10_oid_stack_num_units
    oids_stack_status = f10_oids_stack_status
    oid_num_psus = f10_oid_num_psus
    oid_num_fans = f10_oid_num_fans
    oid_psu_oper = f10_oid_psu_oper
    oid_fans_oper = f10_oid_fans_oper
    oid_mgmt_status = f10_oid_mgmt_status
else:
    f10 = False


num_stackunits = my_snmp_get(args, oid_stack_num_units)
raw_stackunit_status = my_snmp_walk(args, oids_stack_status)

status = STATE_OK
statusstr = ""
stackunit_status = snmpresult_to_dict(raw_stackunit_status)
num_mgmt_units = 0
for index, su in stackunit_status.iteritems():

    mgmt_status = my_snmp_get(args, oid_mgmt_status.format(index))
    if mgmt_status.value == u'1':
        num_mgmt_units += 1

    if f10:
        unit_status_label = 'chStackUnitStatus'
    else:
        unit_status_label = 'dellNetStackUnitStatus'
    unit_status = int(str(su[unit_status_label].value))
    if unit_status == 2:
        status, statusstr = trigger_not_ok(
            status,
            statusstr,
            STATE_CRIT,
            'Stack-unit {} is unsupported'.format(index))
    elif unit_status == 3:
        status, statusstr = trigger_not_ok(
            status,
            statusstr,
            STATE_CRIT,
            STATE_WARN,
            'Stack-unit {} has software image version mismatch'.format(index))
    elif unit_status == 4:
        status, statusstr = trigger_not_ok(
            status,
            statusstr,
            STATE_WARN,
            'Stack-unit {} has configuration mismatch'.format(index))
    elif unit_status == 5:
        status, statusstr = trigger_not_ok(
            status,
            statusstr,
            STATE_CRIT,
            'Stack-unit {} is DOWN'.format(index))
    elif unit_status == 6:
        status, statusstr = trigger_not_ok(
            status,
            statusstr,
            STATE_CRIT,
            'Stack-unit {} is NOT PRESENT'.format(index))

    # Uptime of each unit
    if f10:
        uptime_label = 'chStackUnitUpTime'
    else:
        uptime_label = 'dellNetStackUnitUpTime'
    uptime = dell_parse_snmp_uptime(su[uptime_label].value)
    if uptime < uptime_warn:
        if uptime < uptime_crit:
            status, statusstr = trigger_not_ok(
                status,
                statusstr,
                STATE_CRIT,
                'Stack-unit {} uptime less than {} seconds!'.format(index, uptime_crit))
        else:
            status, statusstr = trigger_not_ok(
                status,
                statusstr,
                STATE_WARN,
                'Stack-unit {} uptime less than {} seconds!'.format(index, uptime_warn))

    # Power supplys
    num_psus = my_snmp_get_int(args, oid_num_psus.format(index))
    for psu_id in xrange(1, num_psus + 1):
        psu_oper_status = my_snmp_get_int(args, oid_psu_oper.format(index, psu_id))
        if psu_oper_status == 2:  # down
            status, statusstr = trigger_not_ok(
                status,
                statusstr,
                STATE_CRIT,
                'Stack-unit {} PSU {} down!'.format(index, psu_id))
        elif psu_oper_status == 3:  # absent
            status, statusstr = trigger_not_ok(
                status,
                statusstr,
                STATE_WARN,
                'Stack-unit {} PSU {} absent'.format(index, psu_id))

    # Fans
    num_fans = my_snmp_get_int(args, oid_num_fans.format(index))
    for fan_id in xrange(1, num_fans + 1):
        fan_oper_status = my_snmp_get_int(args, oid_fans_oper.format(index, fan_id))
        if fan_oper_status == 2:  # down
            status, statusstr = trigger_not_ok(
                status,
                statusstr,
                STATE_CRIT,
                'Stack-unit {} Fan {} down!'.format(index, fan_id))
        elif fan_oper_status == 3:  # absent
            status, statusstr = trigger_not_ok(
                status,
                statusstr,
                STATE_WARN,
                'Stack-unit {} Fan {} absent'.format(index, fan_id))

    # CPU Usage
    if not f10:
        cpu_usage = my_snmp_get_int(args, oid_cpu_usage.format(index))
        if cpu_usage > cpu_usage_crit_percent:
            status, statusstr = trigger_not_ok(
                status,
                statusstr,
                STATE_CRIT,
                'Stack-unit {} high CPU usage ({}%)'.format(index, cpu_usage))
        elif cpu_usage > cpu_usage_warn_percent:
            status, statusstr = trigger_not_ok(
                status,
                statusstr,
                STATE_WARN,
                'Stack-unit {} high CPU usage ({}%)'.format(index, cpu_usage))

    # MEM Usage
    if not f10:
        mem_usage = my_snmp_get_int(args, oid_mem_usage.format(index))
        if mem_usage > mem_usage_crit_percent:
            status, statusstr = trigger_not_ok(
                status,
                statusstr,
                STATE_CRIT,
                'Stack-unit {} high memory usage ({}%)'.format(index, mem_usage))
        elif mem_usage > mem_usage_warn_percent:
            status, statusstr = trigger_not_ok(
                status,
                statusstr,
                STATE_WARN,
                'Stack-unit {} high memory usage ({}%)'.format(index, mem_usage))

if num_mgmt_units < 1:
    status, statusstr = trigger_not_ok(
        status,
        statusstr,
        STATE_CRIT,
        'No active management unit!')
elif num_mgmt_units > 1:
    status, statusstr = trigger_not_ok(
        status,
        statusstr,
        STATE_CRIT,
        'More than one active management unit!')

check_if_ok(status, statusstr)

print "OK: Switch is healthy"
sys.exit(STATE_OK)
