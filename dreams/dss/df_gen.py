"""
Custom functions to generate data frames of useful data...
"""

import os
import opendssdirect as dssdirect
import pandas as pd
import numpy as np
import dreams
import time


def create_df_from_dss(
        odd_name: str,
        dss_name: str,
        element_col_types: dict,
        ):
    """
    General function to collect and cast dss information into a pandas
    dataframe.

    return data frame.

    example of use:
    odd_name = 'Transformers'  # for collecting opendssdirect names
    dss_name = 'transformer'  # for querying dss via cmd
    element_col_types = {'phases': int,
                'windings':int,
                'kv': float,
                'kva': float,
                'conns': ['conn'],
                'buses': ['bus'], # interpret list data, and rename column
                'normhkva': float,
                'sub': str,
                'xfmrcode':str}  # data to collect, and resulting type
    create_df_from_dss(odd_name, dss_name, element_col_types)

    """
    odd_call = getattr(dssdirect, odd_name)
    while_condition = odd_call.First()
    element_dict = {}

    while while_condition:
        element_name = odd_call.Name()

        element_dict[element_name] = {}
        for col, col_type in element_col_types.items():
            # TODO: can this cmd be used to get power flow?
            res = dreams.dss.cmd(f"? {dss_name}.{element_name}.{col}")
            if isinstance(col_type, list) and len(col_type) == 1:
                # iterate list type date - must convert to string..
                res_list = list(
                    filter(None, res.strip('][ ').split(','))
                    )
                res_list = [x.strip() for x in res_list]

                col = col_type[0]
                for res_index in list(range(0, len(res_list))):
                    col_n = f"{col}{res_index+1}"
                    element_dict[element_name][col_n] = res_list[res_index]
            elif isinstance(col_type, list) and odd_name == 'Capacitors':
                # NOTE: issue with capacitors having multiple kvar per step,
                # returns a list, but really just needs a summation..
                res = res[1:-1].strip().split(' ')
                res = sum(map(float, res))
                element_dict[element_name][col_type[0]] = col_type[1](res)
            elif isinstance(col_type, list):
                # column type is list of 2, for single lists not bus related.
                # strip res out
                res = res.replace('[', '').replace(']', '')
                res = res.replace(',', '').strip()
                # cast res as type with correct col name
                element_dict[element_name][col_type[0]] = col_type[1](res)
            else:
                element_dict[element_name][col] = res
        try:
            while_condition = odd_call.Next()
        except dssdirect.DSSException:
            print(f'parsing error: {dss_name}.{element_name}')
            # issue with names incorrecly specifying phases with . and/or _

    result_df = pd.DataFrame.from_dict(element_dict, orient='index')
    result_df.index.rename('name', inplace=True)

    for key, value in element_col_types.items():
        if isinstance(value, type):
            result_df[key] = result_df[key].astype(value)

    return result_df


def get_element_bus_nodes(row,
                          bus_num='1'):
    """
    Return nodes of specified bus connected to transformer.
    Meant to be used as:
    df['bus_x_nodes'] = xfmr_df.apply(get_transformer_primary_nodes, axis=1)
    """
    if isinstance(row, str):
        bus = row
    else:
        bus = row[f'bus{bus_num}'].split('.')

    if '0' in bus:
        bus.remove('0')
    nodes = "".join(bus[1:])
    return nodes


def get_bus_info_df(secondary_kv_limit=0.5):
    """
    Return dataframe of bus name, location, phases, and kv base
    """
    bus_names = dssdirect.Circuit.AllBusNames()
    bus_dict = {}

    for bus_name in bus_names:
        dssdirect.Circuit.SetActiveBus(bus_name)
        bus_dict[bus_name] = {}
        bus_dict[bus_name]['longitude'] = dssdirect.Bus.X()
        bus_dict[bus_name]['latitude'] = dssdirect.Bus.Y()
        # handle nodes/phases
        nodes = dssdirect.Bus.Nodes()
        node_str = [str(x) for x in nodes]
        node_str = "".join(node_str)
        bus_dict[bus_name]['n_phases'] = len(nodes)
        bus_dict[bus_name]['phases'] = node_str
        bus_dict[bus_name]['kv_base'] = dssdirect.Bus.kVBase()
        primary_bool = dssdirect.Bus.kVBase() > secondary_kv_limit
        bus_dict[bus_name]['primary'] = primary_bool
        bus_dict[bus_name]['distance'] = dssdirect.Bus.Distance()

    bus_df = pd.DataFrame.from_dict(bus_dict, orient='index')
    bus_df.index.rename('name', inplace=True)

    return bus_df


def get_bus_voltage_df(over_voltage_pu_limit=1.05,
                       under_voltage_pu_limit=0.95):
    """
    Returns data frame of bus names with PU voltage, angle, and rating.
    Also identifies nodes that are under or over voltage

    second attempt at getting bus voltages - faster than original

    """
    cwd = os.getcwd()  # to prevent directory change...
    bus_names = dssdirect.Circuit.AllBusNames()
    bus_dict = {name: {} for name in bus_names}

    data_of_interest = [
        'v1', 'ang1', 'v2', 'ang2', 'v3', 'ang3']

    for bus_name in bus_names:
        # set active bus
        dssdirect.Circuit.SetActiveBus(bus_name)

        voltage_mag_ang_pu = dssdirect.Bus.puVmagAngle()

        # init bus data
        for name in data_of_interest:
            bus_dict[bus_name][name] = np.nan

        bus_dict[bus_name]['n_nodes'] = dssdirect.Bus.NumNodes()
        bus_dict[bus_name]['nodes_list'] = dssdirect.Bus.Nodes()

        node_str = [str(x) for x in bus_dict[bus_name]['nodes_list']]
        bus_dict[bus_name]['nodes'] = "".join(node_str)

        bus_dict[bus_name]['over_voltage'] = False
        bus_dict[bus_name]['under_voltage'] = False
        bus_dict[bus_name]['zero_voltage'] = False
        bus_dict[bus_name]['distance'] = dssdirect.Bus.Distance()

        bus_dict[bus_name]['kv_base'] = dssdirect.Bus.kVBase()

        index_offset = 0
        for node in bus_dict[bus_name]['nodes_list']:
            voltage_name = f'v{node}'
            angle_name = f'ang{node}'

            bus_dict[bus_name][voltage_name] = voltage_mag_ang_pu[index_offset]
            bus_dict[bus_name][angle_name] = voltage_mag_ang_pu[index_offset+1]

            # seems like this could be done better with the df...
            # although since it checks each node indifidually..
            if bus_dict[bus_name][voltage_name] > over_voltage_pu_limit:
                bus_dict[bus_name]['over_voltage'] = True

            if bus_dict[bus_name][voltage_name] < under_voltage_pu_limit:
                bus_dict[bus_name]['under_voltage'] = True

            if bus_dict[bus_name][voltage_name] == 0.0:
                bus_dict[bus_name]['zero_voltage'] = True

            index_offset += 2

    bus_df = pd.DataFrame.from_dict(bus_dict, orient='index')
    bus_df.index.rename('name', inplace=True)
    bus_df.drop(columns=['nodes_list'], inplace=True)

    os.chdir(cwd)

    return bus_df


def get_capacitor_df():
    """
    Returns capacitor dataframe
    """
    odd_name = 'Capacitors'  # for collecting opendssdirect names
    dss_name = 'capacitor'  # for querying dss via cmd
    element_col_types = {'phases': int,
                         'kv': float,
                         'kvar': ['kvar', float],
                         'conn': str,
                         'bus1': str,
                         'bus2': str,
                         'normamps': float,
                         'states': ['state', int]}

    if dssdirect.Capacitors.First():
        short_name_function = dreams.dss.get_short_bus_name
        cap_df = create_df_from_dss(odd_name, dss_name, element_col_types)
        cap_df['short_bus1'] = cap_df['bus1'].apply(short_name_function)
        cap_df['short_bus2'] = cap_df['bus2'].apply(short_name_function)

        cap_df['inline'] = cap_df['short_bus1'] != cap_df['short_bus2']

        return cap_df

    return pd.DataFrame()


def get_capacity_df():
    """
    Returns capacity dataframe.
    Requires exporting a csv, reading via pandas,
    then deleting csv on disk.
    Also includes identification of element type
    """
    cwd = os.getcwd()
    time_str = str(time.time()).replace('.', '_')
    capacity_csv_path = dssdirect.run_command(f'export capacity capacity_{time_str}.csv')
    capacity_df = pd.read_csv(capacity_csv_path)
    # create type and short name columns
    capacity_df['lower_name'] = capacity_df['Name'].str.lower()
    capacity_df['LongName'] = capacity_df['Name']
    capacity_df['splits'] = capacity_df['lower_name'].str.split('.')

    new_cols = ['Type', 'Name']
    # issue with names having multiple periods...
    capacity_df[new_cols] = pd.DataFrame(capacity_df['splits'].tolist(),
                                         index=capacity_df.index)
    capacity_df.drop(columns=['lower_name', 'splits'], inplace=True)

    """ to handle names with multiple periods
    # think work around is not ideal, names shouldn't have double periods
    capacity_df['Type'] = [splits[0] for splits in capacity_df['splits']]
    capacity_df['Name'] = ['.'.join(splits[1:]) for splits in capacity_df['splits']]
    """

    # fix extra space in capacity column names
    capacity_df.columns = [x.strip() for x in capacity_df.columns]

    column_order = [
        'Type',
        'Name',
        'Imax',
        '%normal',
        '%emergency',
        'kW',
        'kvar',
        'kVBase',
        'NumPhases',
        'TotalCustomers',
        'NumCustomers',
        'LongName']
    capacity_df = capacity_df[column_order]

    # ensure all lower
    capacity_df.columns = [x.lower() for x in capacity_df.columns]
    #  capacity_df.index.rename('name', inplace=True)

    os.remove(capacity_csv_path)
    # opendssdirect functions may change working directory
    os.chdir(cwd)

    return capacity_df


def get_powers_df():
    """
    Returns power dataframe.
    Requires exporting a csv, reading via pandas,
    then deleting csv on disk.
    Also includes identification of element type
    """
    cwd = os.getcwd()
    power_csv_path = dssdirect.run_command('export powers')
    powers_df = pd.read_csv(power_csv_path)
    # clean names
    powers_df.columns = [x.replace(' ', '') for x in powers_df.columns]
    # select only first terminal data
    powers_df = powers_df[powers_df.Terminal == 1]
    # data of interest
    powers_df = powers_df[['Element', 'P(kW)', 'Q(kvar)']]
    # split out short name
    powers_df['short_name'] = powers_df['Element'].str.split('.').str[1]
    powers_df['short_name'] = powers_df['short_name'].str.lower().str.strip()

    # split out type
    powers_df['type'] = powers_df['Element'].str.split('.').str[0].str.lower()
    # rename to match convention
    old_to_new = {
        'Element': 'longname',
        'P(kW)': 'p_kw',
        'Q(kvar)': 'q_kvar',
    }
    powers_df.rename(columns=old_to_new, inplace=True)

    # ensure numeric
    numeric_columns = ['p_kw', 'q_kvar']
    for col in numeric_columns:
        if powers_df[col].dtype == 'O':
            # strip
            powers_df[col] = powers_df[col].str.strip() 
            # set str nan to zero
            nan_mask = powers_df[col] == 'Nan'
            powers_df.loc[nan_mask, col] = 0.0
            # convert to numeric
            powers_df[col] = pd.to_numeric(powers_df[col])

    # calculate s_kva
    powers_df['s_kva'] = powers_df['p_kw']**2 + powers_df['q_kvar']**2
    powers_df['s_kva'] = powers_df['s_kva']**(1/2)
    # order data similar to capacity df
    data_order = [
        'type',
        'short_name',
        'p_kw',
        'q_kvar',
        's_kva',
        'longname'
    ]
    os.remove(power_csv_path)
    # opendssdirect functions may change working directory
    os.chdir(cwd)

    return powers_df[data_order]


def get_fuse_df():
    """
    Return modified fuse dataframe.
    """
    cwd = os.getcwd()
    # Initialize fuse dataframe
    if dssdirect.Fuses.First():

        fuse_df = dssdirect.utils.fuses_to_dataframe()
        fuse_df.columns = [x.lower().strip() for x in fuse_df.columns]
        fuse_df.set_index('name', inplace=True)
        fuse_df['single_obj'] = (fuse_df['monitoredobj'] ==
                                 fuse_df['switchedobj'])
        fuse_df['monitoredobj_short'] = fuse_df['monitoredobj'].apply(
            dreams.dss.get_short_pde_name)
        fuse_df['fuse_name'] = fuse_df.index

        # line required for bus
        line_df = dssdirect.utils.lines_to_dataframe()
        line_df.index.rename('name', inplace=True)

        fuse_df = pd.merge(fuse_df,
                           line_df[['Name', 'Bus1']],
                           left_on='monitoredobj_short',
                           right_on='Name', how='left')
        short_name_function = dreams.dss.get_short_bus_name
        fuse_df['short_bus1'] = fuse_df['Bus1'].apply(short_name_function)

        col_2_rename = {'Name': 'line_name', 'Bus1': 'bus1'}

        fuse_df.rename(columns=col_2_rename, inplace=True)
        fuse_df.set_index('fuse_name', inplace=True)

        fuse_df['bus1_nodes'] = fuse_df.apply(
            get_element_bus_nodes, bus_num='1', axis=1)
        fuse_df['bus1_phase'] = dreams.gis.phase_number_to_letter(
            fuse_df['bus1_nodes'])
        fuse_df.index.rename('name', inplace=True)

    else:
        fuse_df = pd.DataFrame()

    os.chdir(cwd)
    return fuse_df


def get_generator_df():
    """
    Returns generator information
    """
    odd_name = 'Generators'  # for collecting opendssdirect names
    dss_name = 'generator'  # for querying dss via cmd
    element_col_types = {'phases': int,
                         'kv': float,
                         'kva': float,
                         'kw': float,
                         'kvar': float,
                         'pf': float,
                         'conn': str,
                         'bus1': str,
                         'h': float,
                         'forceon': str}  # data to collect, and resulting type

    if dssdirect.Generators.First():
        short_name_function = dreams.dss.get_short_bus_name
        gen_df = create_df_from_dss(odd_name, dss_name, element_col_types)
        gen_df['short_bus1'] = gen_df['bus1'].apply(short_name_function)

        gen_df['bus1_nodes'] = gen_df.apply(
            get_element_bus_nodes, bus_num='1', axis=1)
        gen_df['bus1_phase'] = dreams.gis.phase_number_to_letter(
            gen_df['bus1_nodes'])

        return gen_df
    return pd.DataFrame()


def get_line_df(
        switches=False,
        secondary_kv_limit=0.5,
        ):
    """
    Return modified Line dataframe.  Optionally return switches.
    """
    odd_name = 'Lines'
    dss_name = 'line'
    element_col_types = {
        'phases': int,
        'normamps': float,
        'emergamps': float,
        'length': float,
        'units': str,
        'wires': str,
        'spacing': str,
        'linecode': str,
        'geometry': str,
        'bus1': str,
        'bus2': str,
        'linetype': str}  # not used by dss
    line_df = create_df_from_dss(odd_name, dss_name, element_col_types)

    cwd = os.getcwd()
    # get line data from odd
    line_df2 = dssdirect.utils.lines_to_dataframe()[['TotalCust', 'IsSwitch']]
    line_df = line_df.merge(line_df2, left_index=True, right_index=True)

    short_name_function = dreams.dss.get_short_bus_name
    line_df['short_bus1'] = line_df['bus1'].apply(short_name_function)
    line_df['short_bus2'] = line_df['bus2'].apply(short_name_function)

    line_df.columns = [x.lower().strip() for x in line_df.columns]
    line_df.index.rename('name', inplace=True)

    # collect primary flag for lines based on bus
    buses = dreams.dss.get_bus_info_df()

    line_df = pd.merge(line_df, buses[['kv_base', 'primary']],
                       left_on='short_bus1', right_index=True,)

    line_df = pd.merge(line_df, buses[['kv_base', 'primary']],
                       left_on='short_bus2', right_index=True,
                       suffixes=("_1", "_2"))
    inconsistent_check = sum(line_df['kv_base_1'] != line_df['kv_base_2'])
    if inconsistent_check:
        print('Line connects two buses with different ratings!')

    # astype requred for proper negating using the ~
    switch_mask = line_df['isswitch'].astype(bool)

    if switches:
        line_df = line_df[switch_mask]
    else:
        line_df = line_df[~switch_mask]

    line_df.drop(columns=['isswitch'], inplace=True)

    os.chdir(cwd)

    if len(line_df) == 0:
        # for case where no switches exist
        return pd.DataFrame()

    return line_df


def get_load_df(secondary_kv_limit=0.5):
    """
    Return modified load dataframe
    TODO: get upstream xfmr...
    """
    odd_name = 'Loads'  # for collecting opendssdirect names
    dss_name = 'load'  # for querying dss via cmd
    element_col_types = {'phases': int,
                         'kv': float,
                         'kw': float,
                         'kvar': float,
                         'pf': float,
                         'conn': str,
                         'bus1': str,
                         'model': int,
                         'status': str}  # data to collect, and resulting type

    if dssdirect.Loads.First():
        short_name_function = dreams.dss.get_short_bus_name
        load_df = create_df_from_dss(odd_name, dss_name, element_col_types)

        load_df['short_bus1'] = load_df['bus1'].apply(short_name_function)
        load_df['bus1_nodes'] = load_df.apply(
            get_element_bus_nodes, bus_num='1', axis=1)
        load_df['bus1_phase'] = dreams.gis.phase_number_to_letter(
            load_df['bus1_nodes'])

        load_df['primary'] = load_df['kv'] >= secondary_kv_limit

        # if short_bus = bus, use nodes from bus

        return load_df
    return pd.DataFrame()


def get_pv_df():
    """
    Return modified pv dataframe
    TODO: associate phase/upstream xfmr
    """
    odd_name = 'PVsystems'  # for collecting opendssdirect names
    dss_name = 'pvsystem'  # for querying dss via cmd
    element_col_types = {'phases': int,
                         'kv': float,
                         'kva': float,
                         'kvarmax': float,
                         'pf': float,
                         'conn': str,
                         'bus1': str,
                         '%pmpp': float,
                         '%cutin': float,
                         '%cutout': float,
                         'varfollowinverter': str,
                         'wattpriority': str,
                         'pfpriority': str,
                         'irradiance': float
                         }  # data to collect, and resulting type

    if dssdirect.PVsystems.First():
        short_name_function = dreams.dss.get_short_bus_name
        pv_df = create_df_from_dss(odd_name, dss_name, element_col_types)
        pv_df['short_bus1'] = pv_df['bus1'].apply(short_name_function)

        pv_df['bus1_nodes'] = pv_df.apply(
            get_element_bus_nodes, bus_num='1', axis=1)
        pv_df['bus1_phase'] = dreams.gis.phase_number_to_letter(
            pv_df['bus1_nodes'])
        return pv_df
    return pd.DataFrame()


def get_reactor_df(secondary_kv_limit=0.5):
    """
    returns dataframe of current reactors in system
    """
    cwd = os.getcwd()
    if dssdirect.Reactors.First() == 0:
        os.chdir(cwd)
        return pd.DataFrame()

    reactor_dict = {}

    while_cond = dssdirect.Reactors.First()
    while while_cond:
        name = dssdirect.Reactors.Name()
        reactor_dict[name] = {}
        bus1 = dssdirect.Reactors.Bus1()
        bus2 = dssdirect.Reactors.Bus2()
        reactor_dict[name]['bus1'] = bus1
        reactor_dict[name]['bus2'] = bus2
        reactor_dict[name]['n_phases'] = dssdirect.Reactors.Phases()
        reactor_dict[name]['kv'] = dssdirect.Reactors.kV()
        reactor_dict[name]['primary_1'] = reactor_dict[name]['kv'] > \
            secondary_kv_limit
        reactor_dict[name]['r'] = dssdirect.Reactors.R()
        reactor_dict[name]['x'] = dssdirect.Reactors.X()
        reactor_dict[name]['short_bus1'] = dreams.dss.get_short_bus_name(bus1)
        reactor_dict[name]['short_bus2'] = dreams.dss.get_short_bus_name(bus2)

        while_cond = dssdirect.Reactors.Next()
    os.chdir(cwd)

    reactor_df = pd.DataFrame.from_dict(reactor_dict, orient='index')

    reactor_df.index.rename('name', inplace=True)
    # get norm amps for each.
    for name in reactor_df.index:
        res = dreams.dss.cmd(f"? reactor.{name}.normamps")
        reactor_df.at[name, 'normamps'] = float(res)

    return reactor_df


def get_storage_df():
    """
    returns dataframe of current reactors in system
    """
    cwd = os.getcwd()
    if dssdirect.Storages.First() == 0:
        os.chdir(cwd)
        return pd.DataFrame()
    storage_attributes = {
        'bus1': 'bus1',
        'phases': 'n_phases',
        'kv': 'kv',
        'kva': 'kva',
        'kwhrated': 'kwh_rated',
        '%reserve': 'percent_kwh_reserve',
        '%stored': 'percent_kwh_stored',
        'state': 'state',
        'model': 'model',
        }

    storage_dict = {}

    while_cond = dssdirect.Storages.First()
    # while valid storage name
    while while_cond:
        name = dssdirect.Storages.Name()
        storage_dict[name] = {}

        # collect data via dss query
        for key, value in storage_attributes.items():
            open_dss_value = dreams.dss.cmd(f"? storage.{name}.{key}")
            storage_dict[name][value] = open_dss_value

        storage_dict[name]['pu_soc'] = dssdirect.Storages.puSOC()
        storage_dict[name]['short_bus1'] = dreams.dss.get_short_bus_name(
            storage_dict[name]['bus1'])

        while_cond = dssdirect.Storages.Next()
    os.chdir(cwd)

    storage_df = pd.DataFrame.from_dict(storage_dict, orient='index')

    storage_df.index.rename('name', inplace=True)

    # ensure correct dtypes of numeric columns
    numeric_cols = [
        'n_phases',
        'kv',
        'kva',
        'kwh_rated',
        'percent_kwh_reserve',
        'percent_kwh_stored',
        'model',
    ]
    for col in numeric_cols:
        storage_df[col] = pd.to_numeric(storage_df[col])

    return storage_df


def get_transformer_df():
    """
    Return transformer dataframe.
    Assumes only 2 buses involved.
    TODO: handle arbitrary number of unique buses
    """
    if dssdirect.Transformers.First():
        odd_name = 'Transformers'  # for collecting opendssdirect names
        dss_name = 'transformer'  # for querying dss via cmd
        element_col_types = {
            'phases': int,  # data to collect, and resulting type
            'windings': int,
            'kv': float,
            'kva': float,
            'conns': ['conn'],
            'buses': ['bus'],
            'normhkva': float,
            'sub': str,
            'xfmrcode': str}

        xfmr_df = create_df_from_dss(odd_name, dss_name, element_col_types)
        bus_df = dreams.dss.get_bus_info_df()
        short_name_function = dreams.dss.get_short_bus_name

        n_buses = sum(xfmr_df.columns.str.contains('conn'))
        n_buses = 2
        # NOTE the fast string iteration works, but the
        # issue is not all xfmrs having the same snumber of buses
        # this leads to nan - when collecting data on all buses.
        # a solution may be to create masks for nan data
        valid_bus_kv = []
        for bus in range(1, n_buses+1):
            # skip for nan
            if xfmr_df[f'bus{bus}'] is np.nan:
                xfmr_df[f'short_bus{bus}'] = np.nan
                xfmr_df[f'bus{bus}_nodes'] = np.nan
                xfmr_df[f'bus{bus}_phase'] = np.nan
                xfmr_df[f'bus{bus}_kv_base'] = np.nan
                continue

            # collect short bus
            xfmr_df[f'short_bus{bus}'] = xfmr_df[f'bus{bus}'].apply(
                short_name_function)

            # collect nodes and phases
            xfmr_df[f'bus{bus}_nodes'] = xfmr_df.apply(get_element_bus_nodes,
                                                       bus_num=f'{bus}',
                                                       axis=1)
            xfmr_df[f'bus{bus}_phase'] = dreams.gis.phase_number_to_letter(
                xfmr_df[f'bus{bus}_nodes'])

            # collect kv base
            xfmr_df = pd.merge(xfmr_df, bus_df[['kv_base']],
                               left_on=f'short_bus{bus}',
                               right_index=True)

            xfmr_df.rename(columns={'kv_base': f'bus{bus}_kv_base'},
                           inplace=True)
            valid_bus_kv.append(f'bus{bus}_kv_base')

        # identify high side bus
        high_kv_bus = xfmr_df[valid_bus_kv].idxmax(axis=1)
        xfmr_df[['high_side_bus', 'delme']] = high_kv_bus.str.split(
            '_',
            expand=True,
            n=1)
        xfmr_df.drop(columns='delme', inplace=True)
        # collect short name of high side bus
        xfmr_df['high_side_short_bus'] = xfmr_df.apply(
            lambda x: x[f"short_{x['high_side_bus']}"], axis=1)

        return xfmr_df

    return pd.DataFrame()


def get_voltage_regulator_df():
    """
    Return modified voltage regulator df
    TODO: think of using custom collection?
    """
    cwd = os.getcwd()
    if dssdirect.RegControls.First() != 0:
        reg_df = dssdirect.utils.regcontrols_to_dataframe()
        reg_df.index.rename('Name', inplace=True)
        cols_to_keep = ['CTPrimary', 'Delay', 'MonitoredBus', 'Name',
                        'TapDelay', 'TapWinding',
                        'Transformer', 'VoltageLimit', 'Winding', ]
        reg_df = reg_df[cols_to_keep]
        reg_df['reg_name'] = reg_df.index
        reg_df.columns = [x.lower().strip() for x in reg_df.columns]

        # associate transformer bus information
        xfmr_df = dreams.dss.get_transformer_df()
        xfmr_df['xfmr_name'] = xfmr_df.index
        reg_df = pd.merge(reg_df,
                          xfmr_df[['xfmr_name', 'short_bus1',
                                   'bus1_nodes', 'bus1_phase']],
                          left_on='transformer',
                          right_on='xfmr_name')
        cols_to_rename = {'short_bus1': 'transformer_short_bus1',
                          'bus1_phase': 'transfomer_bus1_phase',
                          'bus1_nodes': 'transformer_bus1_nodes'}

        reg_df.rename(columns=cols_to_rename, inplace=True)
        reg_df.drop(columns=['xfmr_name', 'name'], inplace=True)
        reg_df.set_index('reg_name', inplace=True)
        reg_df.index.rename('name', inplace=True)

        short_name_function = dreams.dss.get_short_bus_name
        reg_df['short_monitoredbus'] = reg_df['monitoredbus'].apply(
            short_name_function)
        # lower bus name
        reg_df['short_monitoredbus'] = reg_df['short_monitoredbus'].str.lower()

        # handle case where monitored bus is blank...
        # use transformer bus for all busies
        empy_mask = reg_df['monitoredbus'] == ''
        filler_bus = reg_df[empy_mask]['transformer_short_bus1']
        reg_df.loc[empy_mask, 'monitoredbus'] = filler_bus
        reg_df.loc[empy_mask, 'short_monitoredbus'] = filler_bus

    else:
        reg_df = pd.DataFrame()

    os.chdir(cwd)
    return reg_df


def get_voltage_source_df():
    """
    Return modified voltage regulator df
    """
    odd_name = 'Vsources'  # for collecting opendssdirect names
    dss_name = 'vsource'  # for querying dss via cmd
    element_col_types = {
        'bus1': str,
        'bus2': str,
        'phases': int,
        'pu': float,
        'basekv': float,
        'basemva': float,
        'basefreq': float,
        'sequence': str,
        }  # data to collect, and resulting type
    if dssdirect.Vsources.First():
        src_df = create_df_from_dss(odd_name, dss_name, element_col_types)
        short_name_function = dreams.dss.get_short_bus_name
        src_df['short_bus1'] = src_df['bus1'].apply(short_name_function)
        return src_df
    return pd.DataFrame()
