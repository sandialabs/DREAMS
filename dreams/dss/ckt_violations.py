"""
Checks for Violations, identify violations,

eventually, suggest changes for said violations

"""

import os
import opendssdirect as dssdirect
import pandas as pd
import dreams
import time


def check_violations(
        capacity_limit=100,
        over_voltage_limit=1.05,
        under_voltage_limit=0.95):
    """
    Checks current solved circuit for voltage and capacity violations.
    Returns dictionary of violations.
    """

    circuit = dreams.dss.gen_min_max_ave_voltages_and_capacity(
        secondary_kv_limit=0)

    violation_types = {}

    # check for voltage violations
    violation_types['over_voltage'] = circuit['primary_voltage_max'] >= over_voltage_limit
    violation_types['under_voltage'] = circuit['primary_voltage_min'] <= under_voltage_limit

    # check line overloading
    violation_types['line_overload'] = circuit['primary_line_max_capacity'] >= capacity_limit

    # check transformer overloading
    if 'transformer_max_capacity' in circuit:
        violation_types['xfmr_overload'] = circuit['transformer_max_capacity'] >= capacity_limit

    violation_types['n_violation_types'] = sum(violation_types.values())

    return violation_types


def id_violations(
        capacity_limit=100,
        over_voltage_limit=1.05,
        under_voltage_limit=0.95):
    """
    Identify violations in present solved circuit related to capacity
    and voltage.

    returns dictionary of components in violation and statistics
    NOTE: circuit must be solved
    """
    og_dir = os.getcwd()

    violation_dict = {}

    # collect capactiy from exported file
    time_str = str(time.time()).replace('.', '_')
    csv_file_path = dssdirect.run_command(f'export capacity capacity_{time_str}.csv')
    capacity_df = pd.read_csv(csv_file_path)
    # remove temporary csv
    try:
        os.remove(csv_file_path)
    except PermissionError:
        print(f"Cound't remove {csv_file_path} due to a permission error...")

    # count number of elements
    capacity_df[['kind', 'short_name']] = capacity_df['Name'].str.split('.', expand=True)
    capacity_df['primary'] = capacity_df[' kVBase'] > 1.0  # ASSERT primary

    # NOTE: assumes transformers and lines exist in model... may not?
    n_lines = capacity_df['kind'].value_counts()['Line']
    n_primary_lines = capacity_df[capacity_df['primary']]['kind'].value_counts()['Line']
    n_secondary_lines = n_lines - n_primary_lines

    if 'Transformer' in capacity_df['kind'].values:
        n_transformers = capacity_df['kind'].value_counts()['Transformer']
    else:
        n_transformers = 0

    # filter out over capacity elements
    # this will work for reactors, lines, transformers...
    # NOTE: relies on standard output format of openDSS capacity csv
    # The changing of this is an external source.
    over_capacity_mask = capacity_df[' %normal'] >= capacity_limit
    if sum(over_capacity_mask) > 0:
        over_capacity_elements = capacity_df[over_capacity_mask].copy()

        # clean up data frame
        over_capacity_elements.reset_index(inplace=True)
        over_capacity_elements.drop(columns='index', inplace=True)

        # handle lines
        line_mask = over_capacity_elements['kind'] == 'Line'
        over_capacity_lines = over_capacity_elements[line_mask]
        n_lines_overcap = line_mask.sum()
        n_primary_lines_overcap = over_capacity_lines['primary'].sum()
        n_secondary_lines_overcap = n_lines_overcap - n_primary_lines_overcap

        # handle transformers
        if n_transformers > 0:
            xfmr_mask = over_capacity_elements['kind'] == 'Transformer'
            n_transformers_overcap = xfmr_mask.sum()
            over_capacity_xfmr = over_capacity_elements[xfmr_mask]
        else:
            n_transformers_overcap = 0
            over_capacity_xfmr = pd.DataFrame()

    else:
        over_capacity_elements = pd.DataFrame()
        over_capacity_lines = pd.DataFrame()
        over_capacity_xfmr = pd.DataFrame()

        n_lines_overcap = 0
        n_primary_lines_overcap = 0
        n_secondary_lines_overcap = 0
        n_transformers_overcap = 0

    # get voltage violations
    bus_voltages = dreams.dss.get_bus_voltage_df(
        over_voltage_pu_limit=over_voltage_limit,
        under_voltage_pu_limit=under_voltage_limit)

    bus_voltages['primary'] = bus_voltages['kv_base'] > 1.0

    # count bus types
    n_bus = len(bus_voltages)
    n_primary_bus = bus_voltages['primary'].sum()
    n_secondary_bus = n_bus - n_primary_bus

    over_voltage_mask = bus_voltages['over_voltage']
    zero_voltage_mask = bus_voltages['zero_voltage']
    under_voltage_mask = bus_voltages['under_voltage']

    # exclude under voltage elements that have a zero voltage
    under_voltage_mask = under_voltage_mask & ~zero_voltage_mask

    over_voltage_elements = bus_voltages[over_voltage_mask]
    under_voltage_elements = bus_voltages[under_voltage_mask]
    zero_voltage_elements = bus_voltages[zero_voltage_mask]

    voltage_violation_mask = under_voltage_mask | over_voltage_mask
    n_bus_violations = sum(voltage_violation_mask)
    n_primary_voltage_violations = bus_voltages[voltage_violation_mask]['primary'].sum()
    n_secondary_voltage_violations = n_bus_violations - n_primary_voltage_violations

    # combine results into dictionary
    violation_dict['over_capacity'] = over_capacity_elements
    violation_dict['n_over_capacity'] = len(violation_dict['over_capacity'])
    violation_dict['over_capacity_lines'] = over_capacity_lines
    violation_dict['n_over_capacity_lines'] = len(over_capacity_lines)
    violation_dict['over_capacity_transformers'] = over_capacity_xfmr
    violation_dict['n_over_capacity_transformers'] = len(over_capacity_xfmr)

    violation_dict['over_voltage'] = over_voltage_elements.reset_index(
        names='Bus_Name')
    violation_dict['n_over_voltage'] = len(violation_dict['over_voltage'])

    violation_dict['under_voltage'] = under_voltage_elements.reset_index(
        names='Bus_Name')
    violation_dict['n_under_voltage'] = len(violation_dict['under_voltage'])

    violation_dict['zero_voltage'] = zero_voltage_elements.reset_index(
        names='Bus_Name')
    violation_dict['n_zero_voltage'] = len(violation_dict['zero_voltage'])

    # handle percents - with optional secondary...
    violation_dict['percent_violation_voltage'] = (n_bus_violations / n_bus) * 100
    violation_dict['percent_violation_primary_voltage'] = (n_primary_voltage_violations / n_primary_bus) * 100

    violation_dict['percent_violation_secondary_voltage'] = 0
    if n_secondary_bus > 0:
        violation_dict['percent_violation_secondary_voltage'] = (n_secondary_voltage_violations / n_secondary_bus) * 100

    violation_dict['percent_violation_xfmr_capacity'] = 0
    if n_transformers > 0:
        violation_dict['percent_violation_xfmr_capacity'] = (n_transformers_overcap / n_transformers) * 100

    violation_dict['percent_violation_line_capacity'] = (n_lines_overcap / n_lines) * 100
    violation_dict['percent_violation_primary_line_capacity'] = (n_primary_lines_overcap / n_primary_lines) * 100

    violation_dict['percent_violation_secondary_line_capacity'] = 0
    if n_secondary_lines > 0:
        violation_dict['percent_violation_secondary_line_capacity'] = (n_secondary_lines_overcap / n_secondary_lines) * 100

    os.chdir(og_dir)

    return violation_dict


def fix_violations(violation_dict):
    """
    NOT CREATED / PLACEHOLDER ONLY
    
    Accepts dictionary of violations and attempts to fix.
    Line Capacity - search for larger rated line with similar qualities...
    Transformer Capacity - increases rating
    Voltage violations...
        if low- increase Voltage source?
        if high - decrease voltage source?
    """

    return violation_dict
