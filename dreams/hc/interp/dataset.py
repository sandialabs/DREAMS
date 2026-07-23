"""
functions to create data set from qsts monitors
"""
import xarray as xr
import pandas as pd
import numpy as np


def get_combined_ds(qsts_mons):
    """
    based on asset monitor results, create and combined datasets of interst
    """
    voltage_dataset = get_voltage_dataset(qsts_mons)
    thermal_dataset = get_thermal_dataset(qsts_mons)
    substation_dataset = get_substation_dataset(qsts_mons)
    asset_powers_dataset = get_asset_powers_dataset(qsts_mons)

    ds_list = [
        voltage_dataset.assign_coords(dataset_id=['voltage_ds']),
        thermal_dataset.assign_coords(dataset_id=['thermal_ds']),
        substation_dataset.assign_coords(dataset_id=['substation_ds']),
        asset_powers_dataset.assign_coords(dataset_id=['asset_ds'])
    ]
    ds_combined = xr.merge(ds_list)

    return ds_combined


# NOTE: these individual dataset creation functions could be refactored into one
# with a dictionary of things that are different for each type...
# think it's only the 'volt' etc key, coords and dims that change
# actually, the data collection call is different for each one aswell...

def get_voltage_dataset(qsts_mons):
    """
    accepts monitor results from specific bus
    returns dataset of voltages
    """

    # Create a list of asset sizes and bus names
    asset_sizes = list(qsts_mons.keys())
    bus_names = list(qsts_mons[asset_sizes[0]]['volt'].keys())

    # Create a time array based on the length of the voltage vectors
    time_length = len(qsts_mons[asset_sizes[0]]['volt'][bus_names[0]].df.values)
    time = pd.Index(range(time_length)) + 1

    # Initialize an empty 3D numpy array to hold the voltage data
    data = np.empty((len(asset_sizes), len(bus_names), time_length), dtype=np.float32)

    # Populate the data array with voltage values
    for i, asset_size in enumerate(asset_sizes):
        for j, bus_name in enumerate(bus_names):
            # getting average voltage
            data[i, j, :] = qsts_mons[asset_size]['volt'][bus_name].get_vector_ave_v()

    # Create the DataArray
    data_array = xr.DataArray(
        data,
        coords=[
            asset_sizes,  # x-axis: asset sizes
            bus_names,    # y-axis: bus names
            time          # z-axis: time
        ],
        dims=["asset_size", "bus_name", "time"]
    )

    dataset = xr.Dataset({"voltages": data_array})

    return dataset

def get_thermal_dataset(qsts_mons):
    """
    accepts monitor results from specific bus,
    returns dataset of pu thermal values
    """

    # Create a list of asset sizes and bus names
    asset_sizes = list(qsts_mons.keys())
    line_names = list(qsts_mons[asset_sizes[0]]['therm'].keys())

    # Create a time array based on the length of the thermal_pu vectors (amps for lines, s for xfrms)
    time_length = len(qsts_mons[asset_sizes[0]]['therm'][line_names[0]].df.values)
    time = pd.Index(range(time_length)) + 1

    # Initialize an empty 3D numpy array to hold the thermal_pu data
    data = np.empty((len(asset_sizes), len(line_names), time_length), dtype=np.float32)

    # Populate the data array with pu current values
    for i, asset_size in enumerate(asset_sizes):
        for j, line_name in enumerate(line_names):
            # getting average current
            data[i, j, :] = qsts_mons[asset_size]['therm'][line_name].get_thermal_pu_vector()

    # Create the DataArray
    data_array = xr.DataArray(
        data,
        coords=[
            asset_sizes,  # x-axis: asset sizes
            line_names,   # y-axis: line names
            time          # z-axis: time
        ],
        dims=["asset_size", "line_name", "time"]
    )

    dataset = xr.Dataset({"thermal_pu": data_array})
    return dataset

def get_substation_dataset(qsts_mons):
    """
    return dataset for substation bacfeeding interpolation 
    """

    asset_sizes = list(qsts_mons.keys())

    source_names = list(qsts_mons[asset_sizes[0]]['vsource'].keys())

    time_length = len(qsts_mons[asset_sizes[0]]['vsource'][source_names[0]].df.values)
    time = pd.Index(range(time_length)) + 1

    data = np.empty((len(asset_sizes), len(source_names), time_length), dtype=np.float32)

    for i, asset_size in enumerate(asset_sizes):
        for j, bus_name in enumerate(source_names):
            # getting source p
            data[i, j, :] = qsts_mons[asset_size]['vsource'][bus_name].get_total_p_vector()

    # Create the DataArray
    data_array = xr.DataArray(
        data,
        coords=[
            asset_sizes,  # x-axis: asset sizes
            source_names, # y-axis: names
            time          # z-axis: time
        ],
        dims=["asset_size", "source_name", "time"]
    )

    dataset = xr.Dataset({"substation_p_delivered": data_array})

    return dataset

def get_asset_powers_dataset(qsts_mons):
    """
    accepts monitor results from specific bus,
    returns dataset of P and Q values from asset sizes.
    """

    # Create a list of asset sizes and bus names
    asset_sizes = list(qsts_mons.keys())

    # identify if gen or load.
    if 'load_hca_s' in qsts_mons[asset_sizes[0]]:
        # is load
        asset_kind = 'load_hca_s'
        mon_name = 'load_hca'
    else:
        asset_kind = 'gen_hca_s'
        mon_name = 'gen_hca'

    # Create a time array based on the length of source voltage dataframe
    time_length = len(qsts_mons[asset_sizes[0]]['vsource']['source'].df.values)
    time = pd.Index(range(time_length)) + 1

    # Initialize an empty 3D numpy array to hold p data
    data = np.empty((len(asset_sizes), 2, time_length), dtype=np.float32)

    # Populate the data array with appropriate powers
    for i, asset_size in enumerate(asset_sizes):
        data[i, 0, :] = qsts_mons[asset_size][asset_kind][mon_name].get_p_vector()
        data[i, 1, :] = qsts_mons[asset_size][asset_kind][mon_name].get_q_vector()

    # Create the DataArray
    data_array = xr.DataArray(
        data,
        coords=[
            asset_sizes,  # x-axis: asset sizes
            ['kw', 'kvar'],   # y-axis: power kind
            time          # z-axis: time
        ],
        dims=["asset_size", "asset_power_kind", "time"]
    )

    dataset = xr.Dataset({"asset_power": data_array})
    return dataset

# dataset analysis function
def get_initial_max_v(voltage_dataset):
    """
    based on first asset size, return maximum voltage
    """
    first_asset_size = voltage_dataset.asset_size.min().item()
    max_v = voltage_dataset.sel(
        {'asset_size': first_asset_size})['voltages'].max().item()
    return max_v

def get_initial_min_v(voltage_dataset):
    """
    based on first asset size, return minimum voltage
    """
    first_asset_size = voltage_dataset.asset_size.min().item()
    min_v = voltage_dataset.sel(
        {'asset_size': first_asset_size})['voltages'].min().item()
    return min_v


def get_initial_max_thermal_pu(thermal_dataset):
    """
    based on first asset size, return maximum thermal pu
    """
    first_asset_size = thermal_dataset.asset_size.min().item()
    max_pu = thermal_dataset.sel(
        {'asset_size': first_asset_size})['thermal_pu'].max().item()
    return max_pu
