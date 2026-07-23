"""
Functions for calculating interpolated hosting capacity.
"""
import numpy as np
np.seterr(divide='ignore', invalid='ignore')  # ignore divide by zero (common with interpolation)

import xarray as xr

from scipy.interpolate import interp1d

from . import dataset as interp_dataset


def get_vchc(
        combined_dataset,
        voltage_threshold=None,
        auto_adjust_threshold=False,
        threshold_kind='higher',
        debug=False,
        ):
    """
    handle vchc... modify to accept multiple buses...
    """
    vchc_res = {}
    if voltage_threshold is None:
        if threshold_kind == 'higher':
            voltage_threshold = 1.05
        else:
            voltage_threshold = 0.95

    voltage_limit_found = False
    voltage_result_min = None
    n_tested_voltage_elements = len(combined_dataset.bus_name.values)
    voltage_element = ''
    voltage_ndx = 0
    
    n_tested_voltage_elements = len(combined_dataset.bus_name.values)
    current_element = 0

    # test each voltage element:
    for valid_element in combined_dataset.bus_name.values:
        if debug:
            current_element += 1
            print(f"* processing element {current_element}/{n_tested_voltage_elements}...", end='\r')
        sel_dataset = combined_dataset.sel({'bus_name': [valid_element]})

        # identify and update voltage threshold if required
        if auto_adjust_threshold:
            if threshold_kind == 'higher':
                # generation, higher threshold
                auto_threshold_v = interp_dataset.get_initial_max_v(sel_dataset)
                if auto_threshold_v > voltage_threshold:
                    select_v_threshold = auto_threshold_v
                else:
                    select_v_threshold = voltage_threshold
            else:
                # demand, lower voltages
                auto_threshold_v = interp_dataset.get_initial_min_v(sel_dataset)
                if auto_threshold_v < voltage_threshold:
                    select_v_threshold = auto_threshold_v
                else:
                    select_v_threshold = voltage_threshold
        else:
            select_v_threshold = voltage_threshold

        voltage_result = _interpolate_voltage_dataset(sel_dataset, select_v_threshold)

        # select minimum asset size to meet threshold
        # TODO?: account for shape... no - when shape is zero, interpolation result is inf

        res_df = voltage_result.to_dataframe()
        # to ensure only positive assets 20260713
        select_min = res_df[res_df['interpolated_asset_size'] > 0].min().item()
        select_voltage_ndx = res_df[res_df['interpolated_asset_size'] > 0].idxmin().item()

        # of tested elements, ensure most conservative result
        if select_min > 0:
            # check if valid (larger than zero)
            if voltage_result_min is None:
                voltage_result_min = select_min
                voltage_element = valid_element
                voltage_ndx = select_voltage_ndx
                voltage_limit_found = True

            elif select_min < voltage_result_min:
                voltage_result_min = select_min
                voltage_element = valid_element
                voltage_ndx = select_voltage_ndx

    if not voltage_limit_found:
        #print('no valid voltage values found')
        voltage_result_min = 0

    vchc_res['vchc'] = voltage_result_min
    vchc_res['vchc_ndx'] = voltage_ndx
    vchc_res['vchc_threshold'] = select_v_threshold
    vchc_res['vchc_element'] = voltage_element
    vchc_res['vchc_n_tested_elements'] = n_tested_voltage_elements
    if debug:
        # annoying space to ensure overrwriten previous 
        print(f"* tested {current_element}/{n_tested_voltage_elements} elements                           ")

    return vchc_res

def _interpolate_voltage_dataset(voltage_dataset, voltage_threshold):
    """
    return asset size for which the voltage dataset would reach the voltage threshold
    this is a vector
    """

    # Extract the voltage data as a 3D array
    voltages = voltage_dataset['voltages'].values  # Shape: (asset_size, bus_name, time)

    # Get the asset sizes and time coordinates
    asset_sizes = voltage_dataset['voltages'].coords['asset_size'].values
    time = voltage_dataset['voltages'].coords['time'].values

    # Create an empty array to hold the interpolated asset sizes
    interpolated_asset_sizes = np.empty(len(time))

    # Use scipy's interp1d for interpolation
    for t in range(len(time)):
        # Extract voltage values for the current time step
        voltage_values = voltages[:, :, t].flatten()  # Flatten to 1D
        asset_sizes_flat = np.tile(asset_sizes, voltages.shape[1])  # Repeat asset sizes for each bus

        # Create the interpolation function
        interp_func = interp1d(voltage_values, asset_sizes_flat, bounds_error=False, fill_value="extrapolate")

        # Perform interpolation
        interpolated_asset_sizes[t] = interp_func(voltage_threshold)

    # Create a DataArray for the interpolated asset sizes
    interpolated_asset_sizes_da = xr.DataArray(
        interpolated_asset_sizes,
        coords=[voltage_dataset['voltages'].coords['time']],
        dims=["time"],
        name="interpolated_asset_size"
    )
    return interpolated_asset_sizes_da

def get_tchc(
        combined_dataset,
        thermal_threshold=None,
        auto_adjust_threshold=False,
        debug=False,
        ):
    """
    Accetpts combined dataset of multiple thermal elements.
    If thermal is none, assumes 1.0 PU
    if auto adjust, assumes max is the larger of existing maximum, or 1
    """

    tchc_res = {}

    if thermal_threshold is None:
        thermal_threshold = 1.0

    thermal_limit_found = False
    thermal_result_min = None
    thermal_element = ''
    thermal_ndx = 0

    n_tested_thermal_elements = len(combined_dataset.line_name.values)
    current_element = 0
    # each thermal element is tested
    for valid_element in combined_dataset.line_name.values:
        if debug:
            current_element += 1
            print(f"* processing element {current_element}/{n_tested_thermal_elements}...", end='\r')
        sel_dataset = combined_dataset.sel({'line_name': [valid_element]})

        # identify and update thermal threshold if required
        if auto_adjust_threshold:
            max_thermal_threshold = interp_dataset.get_initial_max_thermal_pu(sel_dataset)

            if thermal_threshold < max_thermal_threshold:
                select_thermal_treshold = max_thermal_threshold
            else:
                select_thermal_treshold = thermal_threshold

        else:
            select_thermal_treshold = thermal_threshold

        #print(f"thermal threshold = {thermal_threshold}")
        thermal_result = _interpolate_thermal_dataset(sel_dataset, select_thermal_treshold)

        # create absolute first, then find minimum.
        # TODO: account for shape... requirement of non_zero profile
        select_min = abs(thermal_result).min().item()  # works for load
        select_thermal_ndx = abs(thermal_result).idxmin().item()

        # of tested elements, ensure most conservative result
        if select_min > 0:
            # check if valid (larger than zero)
            #print(f"element {valid_element}: {select_min}")
            if thermal_result_min is None:
                thermal_result_min = select_min
                thermal_element = valid_element
                thermal_ndx = select_thermal_ndx
                thermal_limit_found = True

            elif select_min < thermal_result_min:
                # most recent element is smallest hosting capacity
                thermal_result_min = select_min
                thermal_element = valid_element
                thermal_ndx = select_thermal_ndx

    if not thermal_limit_found:
        #print('no valid thermal values found')
        thermal_result_min = 0

    # collect thermal data
    tchc_res['tchc'] = thermal_result_min
    tchc_res['tchc_threshold'] = select_thermal_treshold
    tchc_res['tchc_element'] = thermal_element
    tchc_res['tchc_ndx'] = thermal_ndx
    tchc_res['tchc_n_tested_elements'] = n_tested_thermal_elements
    if debug:
        # annoying space to ensure overrwriten previous 
        print(f"* tested {current_element}/{n_tested_thermal_elements} elements                           ")

    return tchc_res

def _interpolate_thermal_dataset(thermal_dataset, thermal_threshold):
    """
    Assumes thermal dataset is already 'downselected' to include one 
    thermal elements of interest
    """
    # Extract the voltage data as a 3D array
    thermal_pus = thermal_dataset['thermal_pu'].values  # Shape: (asset_size, element_name, time)

    # Get the asset sizes and time coordinates
    asset_sizes = thermal_dataset['thermal_pu'].coords['asset_size'].values
    time = thermal_dataset['thermal_pu'].coords['time'].values

    # Create an empty array to hold the interpolated asset sizes
    interpolated_asset_sizes = np.empty(len(time))

    # Use scipy's interp1d for interpolation
    for t in range(len(time)):
        # Extract voltage values for the current time step
        thermal_values = thermal_pus[:, :, t].flatten()  # Flatten to 1D
        asset_sizes_flat = np.tile(asset_sizes, thermal_pus.shape[1])  # Repeat asset sizes for each bus

        # Create the interpolation function
        interp_func = interp1d(thermal_values, asset_sizes_flat, bounds_error=False, fill_value="extrapolate")
        interpolated_asset_sizes[t] = interp_func(thermal_threshold)
        
        # code for other types of interpolation, though linear seems okay
        # try:
        #     interp_func = interp1d(thermal_values, asset_sizes_flat,
        #                         bounds_error=False, fill_value="extrapolate",
        #                         kind='quadratic')

        #     # Perform interpolation
        #     interpolated_asset_sizes[t] = interp_func(thermal_threshold)
        # except ValueError:
        #     # likely related to duplicate x
        #     interpolated_asset_sizes[t] = np.nan

    # Create a DataArray for the interpolated asset sizes
    select_interpolated_asset_sizes_da = xr.DataArray(
        interpolated_asset_sizes,
        coords=[thermal_dataset['thermal_pu'].coords['time']],
        dims=["time"],
        name="interpolated_asset_size"
    )

    return select_interpolated_asset_sizes_da

def get_schc(combined_dataset, backfeeding_threshold=None):
    """
    returns substation constrained hosting capacity based on provided
    combined dataset and backfeeding threshold.
    """
    schc_res = {}

    if backfeeding_threshold is None:
        backfeeding_threshold = 0

    substation_result = _interpolate_substation_dataset(combined_dataset, backfeeding_threshold)

    # when zero, goes to negative infinity... maybe just replace negative inf with nan?
    res_df = substation_result.to_dataframe()
    substation_result_min = res_df[res_df['interpolated_asset_size'] > 0].min().item()
    substation_result_ndx = res_df[res_df['interpolated_asset_size'] > 0].idxmin().item()

    # substation_result_min = substation_result.min().item()
    # substation_result_ndx = substation_result.idxmin().item()

    # handle existing backfeeding situation
    # NOTE: the above selection of only positive may negate this part/require additional checks
    if substation_result_min < 0:
        substation_result_min = 0

    # collect schc data
    schc_res['schc'] = substation_result_min
    schc_res['schc_threshold'] = backfeeding_threshold
    schc_res['schc_ndx'] = substation_result_ndx


    return schc_res

def _interpolate_substation_dataset(substation_dataset, backfeeding_threshold):
    """
    Interpolate substation data, return minimum asset size of schc
    """
    # Extract the voltage data as a 3D array
    substation_powers = substation_dataset['substation_p_delivered'].values  # Shape: (asset_size, element_name, time)

    # Get the asset sizes and time coordinates
    asset_sizes = substation_dataset['substation_p_delivered'].coords['asset_size'].values
    time = substation_dataset['substation_p_delivered'].coords['time'].values

    # Create an empty array to hold the interpolated asset sizes
    interpolated_asset_sizes = np.empty(len(time))

    # Use scipy's interp1d for interpolation
    for t in range(len(time)):
        # Extract voltage values for the current time step
        power_values = substation_powers[:, :, t].flatten()  # Flatten to 1D
        asset_sizes_flat = np.tile(asset_sizes, substation_powers.shape[1])  # Repeat asset sizes for each bus

        # Create the interpolation function
        interp_func = interp1d(power_values, asset_sizes_flat, bounds_error=False, fill_value="extrapolate")

        # Perform interpolation
        interpolated_asset_sizes[t] = interp_func(backfeeding_threshold)

    # Create a DataArray for the interpolated asset sizes
    interpolated_asset_sizes_da = xr.DataArray(
        interpolated_asset_sizes,
        coords=[substation_dataset['substation_p_delivered'].coords['time']],
        dims=["time"],
        name="interpolated_asset_size"
    )

    return interpolated_asset_sizes_da
