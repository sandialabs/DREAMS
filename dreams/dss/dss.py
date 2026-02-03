"""
Functions related to dss
"""

import os
import time
import opendssdirect as dssdirect
import pandas as pd
import numpy as np

import dreams


def get_short_bus_name(long_bus_name):
    """Split bus name at periods and return 0th item """
    short_bus_name = long_bus_name.split('.')
    return short_bus_name[0]


def get_short_pde_name(long_pde_name):
    """
    Used for Loads, lines, Transformer
    Assumes only 1 period between pde type description and short name
    """
    short_pde_name = long_pde_name.split('.')
    return short_pde_name[-1]


def redirect(file_path):
    """
    simple redirect command for dss
    """
    return dssdirect.run_command(f'redirect "{file_path}"')


def cmd(command):
    """
    simple dss command surrounded by tripped quotes
    """
    return dssdirect.run_command(f"""{command}""")


def solve_system(
        feeder_path,
        load_multiplier=1.0,
        control_mode='STATIC',
        redirect_flag=True,
        compile_flag=False
        ):
    """
    Compile and Solve system at passed in filePath
    Allows for optional loadMult and controlMode variables.
    Defaults are: loadMult=1.0, controlMode='STATIC'
    NOTE: seems overly complicated...
    """
    if redirect_flag:
        # NOTE: does not change directory
        dssdirect.run_command(f"""redirect "{feeder_path}" """)

    if compile_flag:
        # NOTE: changes directory
        # useful as many scripts assume running from 'home' directory
        dssdirect.run_command(f"""compile "{feeder_path}" """)

    dssdirect.run_command(f"Set loadmult = {load_multiplier}")
    dssdirect.run_command(f"Set controlmode = {control_mode}")
    dssdirect.run_command('Set mode = snap')
    dssdirect.run_command('solve')

    convergence = True
    # check convergence
    if not dssdirect.Solution.Converged():
        convergence = False

    return convergence


def get_losses_per_phase_df():
    """
    Of current feeder solution, return dataframe of per phase power
    """
    export_path = dreams.dss.cmd('export p_byphase')
    df = pd.read_csv(export_path)

    expected_cols = [
        'Element', ' NumTerminals', ' NumConductors', ' NumPhases',
        ' kW1',  ' kvar1', ' kW2', ' kvar2', ' kW3', ' kvar3', 
        ' kW1_out',  ' kvar1_out', ' kW2_out', ' kvar2_out',
        ' kW3_out', ' kvar3_out',]

    expected_cols = [x.lower().strip() for x in expected_cols]
    df = pd.read_csv(export_path, header=None, skiprows=1, names=expected_cols)

    df[['kind', 'name']] = df['element'].str.split('.', expand=True)

    ordered_cols = [
        'element', 'kind', 'name',
        'numphases', 'kw1', 'kvar1', 'kw2', 'kvar2', 'kw3', 'kvar3',
        ]

    df = df[ordered_cols].fillna(0)

    line_mask = df['kind'] == 'Line'
    df = df[line_mask]

    df['total_kw_loss'] = 0.0
    df['total_kvar_loss'] = 0.0

    zero_cols = ['kw1', 'kvar1', 'kw2', 'kvar2', 'kw3', 'kvar3']
    for col in zero_cols:
        # set to zero as original values contain errors
        df[col] = 0.0

    for index, row in df.iterrows():
        element = row['element']
        n_phases = row['numphases']
        res = dreams.dss.cmd(f'select {element}')

        per_phase_loses = dreams.dss.cmd('phaselosses')
        per_phase_loses = [x.strip() for x in per_phase_loses.split(',')]
        for ndx_n in range(n_phases):
            phase_n = ndx_n + 1
            kw_ndx = ndx_n * 2
            kvar_ndx = kw_ndx + 1

            df.at[index, f'kw{phase_n}'] = float(per_phase_loses[kw_ndx])
            df.at[index, f'kvar{phase_n}'] = float(per_phase_loses[kvar_ndx])

        total_loss_str = dreams.dss.cmd('losses')
        total_kw_loss, total_kvar_loss = [
            float(x.strip()) for x in total_loss_str.split(',')]

        df.at[index, 'total_kw_loss'] = total_kw_loss
        df.at[index, 'total_kvar_loss'] = total_kvar_loss

    try:
        os.remove(export_path)
    except PermissionError:
        print(f"Cound't remove {export_path} due to a permission error...")

    return df


def gen_min_max_ave_voltages_and_capacity(secondary_kv_limit=0.5):
    """
    collect min max voltage, average and max capacity for line and xfmr.
    For both primary and secondary system
    (if elements below the input secondary_kv_limit (500 V) are found)

    assumes feeder is loaded and solved
    """
    voltages = pd.DataFrame()  # for collecting raw values from feeder

    results = {}  # for collecting returnable values in dictionary form

    secondary_v_limit = secondary_kv_limit*1000  # voltage limit in volts

    voltages['Vmag'] = dssdirect.Circuit.AllBusVMag()  # to filter secondary
    voltages['VPU'] = dssdirect.Circuit.AllBusMagPu()

    # masks for easier data collection
    primary_mask = voltages['Vmag'] >= secondary_v_limit
    secondary_mask = voltages['Vmag'] < secondary_v_limit

    has_secondary = sum(secondary_mask) > 0

    # primary voltage collection
    results['primary_voltage_max'] = voltages.loc[primary_mask]['VPU'].max()
    results['primary_voltage_min'] = voltages.loc[primary_mask]['VPU'].min()
    results['primary_voltage_ave'] = voltages.loc[primary_mask]['VPU'].mean()

    # secondary voltage collection
    if has_secondary:
        results['secondary_voltage_max'] = voltages.loc[
            secondary_mask]['VPU'].max()
        results['secondary_voltage_min'] = voltages.loc[
            secondary_mask]['VPU'].min()
        results['secondary_voltage_ave'] = voltages.loc[
            secondary_mask]['VPU'].mean()

    # TODO: use feeder here...? maybe?
    # Line and Transformer capacity are gathered from an OpenDSS csv export...
    time_str = str(time.time()).replace('.', '_')
    capacity_csv_path = dssdirect.run_command(f'export capacity capacity_{time_str}.csv')
    capacity_df = pd.read_csv(capacity_csv_path)
    # remove extra spaces from columns
    capacity_df.columns = capacity_df.columns.str.strip()

    # handle inf and nan ->set to zero...
    cols_to_clean = ['Imax', '%normal', '%emergency', 'kW', 'kvar']
    nan_values = ['+Inf', '-Inf', 'Nan']

    for col in cols_to_clean:
        # only attempt to strip objects
        if capacity_df[col].dtype == 'O':
            capacity_df[col] = capacity_df[col].str.strip()

    capacity_df = capacity_df.replace(dict.fromkeys(nan_values, '0'))

    # NOTE: this process appears to require the csv export/delete
    try:
        os.remove(capacity_csv_path)
    except PermissionError:
        print(f"Cound't remove {capacity_csv_path} due to a permission error...")

    line_mask = capacity_df['Name'].str.contains('Line')
    xfmr_mask = capacity_df['Name'].str.contains('Transformer')

    # NOTE: the space before kV in key name is due to OpenDSSdirect.
    primary_mask = capacity_df['kVBase'] >= (secondary_v_limit/1000.00)
    secondary_mask = capacity_df['kVBase'] < (secondary_v_limit/1000.00)

    primary_line_mask = line_mask & primary_mask

    primary_capacity = capacity_df[primary_line_mask]

    results['primary_line_max_capacity'] = primary_capacity['%normal'].max()
    results['primary_line_ave_capacity'] = primary_capacity['%normal'].mean()

    if has_secondary:
        secondary_line_mask = line_mask & secondary_mask
        secondary_capacity = capacity_df[secondary_line_mask]
        results['secondary_line_max_capacity'] = secondary_capacity[
            '%normal'].max()
        results['secondary_line_ave_capacity'] = secondary_capacity[
            '%normal'].mean()

    if sum(xfmr_mask) > 0:
        results['transformer_max_capacity'] = capacity_df[xfmr_mask][
            '%normal'].max()
        results['transformer_ave_capacity'] = capacity_df[xfmr_mask][
            '%normal'].mean()

    return results


def get_feeder_counts(secondary_kv_limit=0.5):
    """
    Collect useful information about the circuit
    ASSERTS: circuit is loaded in openDSS
    NOTE: load values do not include any load mult
    """
    # bus count and distance information
    bus_names = dssdirect.Circuit.AllBusNames()
    all_distances = []
    for bus_name in bus_names:
        # set active bus
        dssdirect.Circuit.SetActiveBus(bus_name)
        all_distances.append(dssdirect.Bus.Distance())

    # line count
    # old approach
    while_condition = dssdirect.Lines.First()
    n_lines = 0
    while while_condition:
        n_lines += 1
        while_condition = dssdirect.Lines.Next()

    # new approach
    # takes much longer... than above...
    # TODO: handle length units in a better way
    line_df = dreams.dss.get_line_df()
    primary_mask = line_df.primary_1.astype(bool)
    secondary_mask = ~primary_mask

    n_primary_lines = sum(primary_mask)
    n_secondary_lines = sum(secondary_mask)

    length_primary = np.nan
    length_secondary = np.nan
    if len(line_df.units.unique()) == 1:
        lenght_unit = line_df.units.iloc[0]
        # all length units are the same
        length_primary = line_df[primary_mask]['length'].sum()
        length_secondary = line_df[secondary_mask]['length'].sum()
        # convert to km
        if lenght_unit == 'ft':
            # feet to km
            length_primary /= 3280.84
            length_secondary /= 3280.84
        elif lenght_unit == 'm':
            # m to km
            length_primary /= 1000.00
            length_secondary /= 1000.00
        elif lenght_unit == 'km':
            # already km...
            length_primary = length_primary
            length_secondary = length_secondary
        else:
            # non handled unit...
            length_primary = np.nan
            length_secondary = np.nan

    # capacitor count
    while_condition = dssdirect.Capacitors.First()
    n_caps = 0
    while while_condition:
        n_caps += 1
        while_condition = dssdirect.Capacitors.Next()

    # fuse count
    while_condition = dssdirect.Fuses.First()
    n_fuses = 0
    while while_condition:
        n_fuses += 1
        while_condition = dssdirect.Fuses.Next()

    # generator count
    while_condition = dssdirect.Generators.First()
    n_generators = 0
    while while_condition:
        n_generators += 1
        while_condition = dssdirect.Generators.Next()

    # load data
    loads = dssdirect.utils.loads_to_dataframe()

    # transformer count
    while_condition = dssdirect.Transformers.First()
    n_xfmrs = 0
    while while_condition:
        n_xfmrs += 1
        while_condition = dssdirect.Transformers.Next()

    # pv count
    while_condition = dssdirect.PVsystems.First()
    n_pv = 0
    while while_condition:
        n_pv += 1
        while_condition = dssdirect.PVsystems.Next()

    # reactor count
    while_condition = dssdirect.Reactors.First()
    n_reactors = 0
    while while_condition:
        n_reactors += 1
        while_condition = dssdirect.Reactors.Next()

    # storage count
    while_condition = dssdirect.Storages.First()
    n_storages = 0
    while while_condition:
        n_storages += 1
        while_condition = dssdirect.Storages.Next()

    # switch count
    line_2_df = dssdirect.utils.lines_to_dataframe()
    n_switches = sum(line_2_df.IsSwitch)

    # voltage regulator count
    while_condition = dssdirect.RegControls.First()
    n_regulators = 0
    while while_condition:
        n_regulators += 1
        while_condition = dssdirect.RegControls.Next()

    # voltage source info
    v_source_df = dssdirect.utils.vsources_to_dataframe()

    # combine into dictionary
    result_dict = {}
    result_dict['source_pu'] = v_source_df['PU'].iloc[0]
    result_dict['source_kv'] = v_source_df['BasekV'].iloc[0]
    if len(loads) > 0:
        result_dict['kv_levels'] = loads['kV'].unique()

        result_dict['init_kw'] = loads['kW'].sum()
        result_dict['init_kvar'] = loads['kvar'].sum()

    result_dict['feeder_max_length_km'] = max(all_distances)

    result_dict['n_bus'] = len(bus_names)
    result_dict['n_lines'] = n_lines
    result_dict['n_primary_lines'] = n_primary_lines
    result_dict['length_primary_lines_km'] = length_primary
    result_dict['n_secondary_lines'] = n_secondary_lines
    result_dict['length_secondary_lines_km'] = length_secondary

    if len(loads) > 0:
        result_dict['n_cust'] = loads['NumCust'].sum()
        result_dict['n_loads'] = len(loads)

        result_dict['n_primary_loads'] = sum(loads['kV'] > secondary_kv_limit)
        result_dict['n_secondary_loads'] = sum(loads['kV'] <= secondary_kv_limit)

    result_dict['n_capacitors'] = n_caps
    result_dict['n_fuses'] = n_fuses
    result_dict['n_generators'] = n_generators
    result_dict['n_pv'] = n_pv
    result_dict['n_transformers'] = n_xfmrs
    result_dict['n_reactors'] = n_reactors
    result_dict['n_regulators'] = n_regulators
    result_dict['n_storages'] = n_storages
    result_dict['n_switches'] = n_switches

    # new solution informations
    result_dict['converged'] = dssdirect.Solution.Converged()
    result_dict['control_iterations'] = dssdirect.Solution.ControlIterations()
    result_dict['most_iterations'] = dssdirect.Solution.MostIterationsDone()
    result_dict['total_iterations'] = dssdirect.Solution.TotalIterations()

    return result_dict


def reset_relays():
    """
    reset relays by setting state to closed for any relays.
    """
    relays = dssdirect.utils.relays_to_dataframe()
    if len(relays) == 0:
        return
    for relay in relays.index:
        dreams.dss.cmd(f'edit relay.{relay} state=closed')
    return
