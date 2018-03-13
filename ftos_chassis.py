#!/usr/bin/env python
#
# @descr    Checks chassis status of FTOS switches
#
# @author   Johan Hedberg <jh@citynetwork.se>
#

import sys
import argparse
from lib.cnh_nm import STATE_OK, STATE_CRIT, STATE_WARN
from lib.cnh.nm import trigger_not_ok, check_if_ok, my_snmp_get, my_snmp_walk, my_snmp_get_int
from lib.cnh.nm import dell_parse_snmp_uptime, snmpresult_to_dict

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
psu_usage_warn_percent = 75
psu_usage_crit_percent = 90
cpu_usage_warn_percent = 85
cpu_usage_crit_percent = 95
mem_usage_warn_percent = 75
mem_usage_crit_percent = 90

oid_device_type = 'DELL-NETWORKING-CHASSIS-MIB::dellNetDeviceType.0'
oid_stack_num_units = 'DELL-NETWORKING-CHASSIS-MIB::dellNetNumStackUnits.0'
oids_stack_status = [
        'DELL-NETWORKING-CHASSIS-MIB::dellNetStackUnitNumber',
        'DELL-NETWORKING-CHASSIS-MIB::dellNetStackUnitNumber',
        'DELL-NETWORKING-CHASSIS-MIB::dellNetStackUnitMgmtStatus',
        'DELL-NETWORKING-CHASSIS-MIB::dellNetStackUnitStatus',
        'DELL-NETWORKING-CHASSIS-MIB::dellNetStackUnitUpTime'
]

oid_num_psus = 'DELL-NETWORKING-CHASSIS-MIB::dellNetStackUnitNumPowerSupplies.{}'
oid_num_fans = 'DELL-NETWORKING-CHASSIS-MIB::dellNetStackUnitNumFanTrays.{}'

# Does not work with symbolic oids in easysnmp (but it does work with commandline snmpget)
oid_psu_oper = '.1.3.6.1.4.1.6027.3.26.1.4.6.1.4.2.{}.{}'  # dellNetPowerSupplyOperStatus
oid_psu_usage = '.1.3.6.1.4.1.6027.3.26.1.4.6.1.10.2.{}.{}'  # dellNetPowerSupplyUsage
oid_fans_oper = '.1.3.6.1.4.1.6027.3.26.1.4.7.1.4.2.{}.{}'  # dellNetFanTrayOperStatus
oid_mem_usage = '.1.3.6.1.4.1.6027.3.26.1.4.4.1.6.2.{}.1'  # dellNetCpuUtilMemUsage
oid_cpu_usage = '.1.3.6.1.4.1.6027.3.26.1.4.4.1.4.2.{}.1'  # dellNetCpuUtilMemUsage
oids_system = [
        'DELL-NETWORKING-CHASSIS-MIB::dellNetCpuUtil1Min.stack',
        'DELL-NETWORKING-CHASSIS-MIB::dellNetCpuUtilMemUsage.stack'
]


# Checking system status
device_type = my_snmp_get(args, oid_device_type)
if int(str(device_type.value)) == 2:
    num_stackunits = my_snmp_get(args, oid_stack_num_units)
    raw_stackunit_status = my_snmp_walk(args, oids_stack_status)

    status = STATE_OK
    statusstr = ""
    stackunit_status = snmpresult_to_dict(raw_stackunit_status)
    num_mgmt_units = 0
    for index, su in stackunit_status.iteritems():
        if su['dellNetStackUnitMgmtStatus'].value == u'1':
            num_mgmt_units += 1

        unit_status = int(str(su['dellNetStackUnitStatus'].value))
        if unit_status == 2:
            trigger_not_ok(
                    status,
                    statusstr,
                    STATE_CRIT,
                    'Stack-unit {} is unsupported'.format(index))
        elif unit_status == 3:
            trigger_not_ok(
                    status,
                    statusstr,
                    STATE_CRIT,
                    STATE_WARN,
                    'Stack-unit {} has software image version mismatch'.format(index))
        elif unit_status == 4:
            trigger_not_ok(
                    status,
                    statusstr,
                    STATE_WARN,
                    'Stack-unit {} has configuration mismatch'.format(index))
        elif unit_status == 5:
            trigger_not_ok(
                    status,
                    statusstr,
                    STATE_CRIT,
                    'Stack-unit {} is DOWN'.format(index))
        elif unit_status == 6:
            trigger_not_ok(
                    status,
                    statusstr,
                    STATE_CRIT,
                    'Stack-unit {} is NOT PRESENT'.format(index))

        # Uptime of each unit
        uptime = dell_parse_snmp_uptime(su['dellNetStackUnitUpTime'].value)
        if uptime < uptime_warn:
            if uptime < uptime_crit:
                trigger_not_ok(
                        status,
                        statusstr,
                        STATE_CRIT,
                        'Stack-unit {} uptime less than {} seconds!'.format(index, uptime_crit))
            else:
                trigger_not_ok(
                        status,
                        statusstr,
                        STATE_WARN,
                        'Stack-unit {} uptime less than {} seconds!'.format(index, uptime_warn))

        # Power supplys
        num_psus = my_snmp_get_int(args, oid_num_psus.format(index))
        for psu_id in xrange(1, num_psus+1):
            psu_oper_status = my_snmp_get_int(args, oid_psu_oper.format(index, psu_id))
            if psu_oper_status == 2:  # down
                trigger_not_ok(
                        status,
                        statusstr,
                        STATE_CRIT,
                        'Stack-unit {} PSU {} down!'.format(index, psu_id))
            elif psu_oper_status == 3:  # absent
                trigger_not_ok(
                        status,
                        statusstr,
                        STATE_WARN,
                        'Stack-unit {} PSU {} absent'.format(index, psu_id))
            psu_usage = my_snmp_get_int(args, oid_psu_usage.format(index, psu_id))
            if psu_usage > psu_usage_warn_percent:
                if psu_usage > psu_usage_crit_percent:
                    trigger_not_ok(
                            status,
                            statusstr,
                            STATE_CRIT,
                            'Stack-unit {} PSU {} high PSU usage ({}%)'.format(index, psu_id, psu_usage))
                else:
                    trigger_not_ok(
                            status,
                            statusstr,
                            STATE_WARN,
                            'Stack-unit {} PSU {} high PSU usage ({}%)'.format(index, psu_id, psu_usage))

        # Fans
        num_fans = my_snmp_get_int(args, oid_num_fans.format(index))
        for fan_id in xrange(1, num_fans+1):
            fan_oper_status = my_snmp_get_int(args, oid_fans_oper.format(index, fan_id))
            if fan_oper_status == 2:  # down
                trigger_not_ok(
                        status,
                        statusstr,
                        STATE_CRIT,
                        'Stack-unit {} Fan {} down!'.format(index, fan_id))
            elif fan_oper_status == 3:  # absent
                trigger_not_ok(
                        status,
                        statusstr,
                        STATE_WARN,
                        'Stack-unit {} Fan {} absent'.format(index, fan_id))

        # CPU Usage
        cpu_usage = my_snmp_get_int(args, oid_cpu_usage.format(index))
        if cpu_usage > cpu_usage_crit_percent:
            trigger_not_ok(
                    status,
                    statusstr,
                    STATE_CRIT,
                    'Stack-unit {} high CPU usage ({}%)'.format(index, cpu_usage))
        elif cpu_usage > cpu_usage_warn_percent:
            trigger_not_ok(
                    status,
                    statusstr,
                    STATE_WARN,
                    'Stack-unit {} high CPU usage ({}%)'.format(index, cpu_usage))

        # MEM Usage
        mem_usage = my_snmp_get_int(args, oid_mem_usage.format(index))
        if mem_usage > mem_usage_crit_percent:
            trigger_not_ok(
                    status,
                    statusstr,
                    STATE_CRIT,
                    'Stack-unit {} high memory usage ({}%)'.format(index, mem_usage))
        elif mem_usage > mem_usage_warn_percent:
            trigger_not_ok(
                    status,
                    statusstr,
                    STATE_WARN,
                    'Stack-unit {} high memory usage ({}%)'.format(index, mem_usage))

    if num_mgmt_units < 1:
        trigger_not_ok(
                status,
                statusstr,
                STATE_CRIT,
                'No active management unit!')
    elif num_mgmt_units > 1:
        trigger_not_ok(
                status,
                statusstr,
                STATE_CRIT,
                'More than one active management unit!')

    check_if_ok(status, statusstr)

print "OK: Switch is healthy"
sys.exit(STATE_OK)