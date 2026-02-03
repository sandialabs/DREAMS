"""
Create, and optionally export GIS type files containing feeder data.
Feeder object required.

TODO: look into creating a multi layer geopackage...
TODO: look into creating KML aswell (will first make geopackage)
        steal this from gis_collect when complete

TODO: export transformers as points (optionally)
"""

import os
import warnings
import pathlib
import geopandas as gpd
import pandas as pd

from shapely.errors import ShapelyDeprecationWarning
from shapely.geometry import Point
from shapely.geometry import MultiPoint
from shapely.geometry import LineString

warnings.filterwarnings("ignore", category=ShapelyDeprecationWarning)


def export_feeder_gpkg(
        feeder,
        input_crs=4326,
        output_crs=4326,
        output_path=None,
        ):
    """
    export all feeder elements as geopackage
    """
    # ensure output path exists, if not, make it
    if output_path is not None:
        # use pathlib... 20230710 - maybe not?
        output_path = pathlib.Path(output_path)
        if not os.path.isdir(output_path):
            os.makedirs(output_path, exist_ok=True)

    export_functions = [
        export_bus_gis,
        export_capacitor_gis,
        export_fuse_gis,
        export_generator_gis,
        export_line_gis,
        export_load_gis,
        export_pv_gis,
        export_reactor_gis,
        export_storage_gis,
        export_switch_gis,
        export_transformer_gis,
        export_voltage_source_gis,
        export_voltage_regulator_gis,
                        ]

    resulting_outputs = []
    for export_function in export_functions:
        result_path = export_function(
            feeder,
            output_path=output_path,
            input_crs=input_crs,
            output_crs=output_crs,
            )
        if result_path is not None:
            resulting_outputs.append(result_path)

    return resulting_outputs


def collect_point_type_gdf(
        feeder,
        feeder_attribute,
        input_crs=4326,
        ):
    """
    return geodataframe of point type elements from feeder or empty gdf if
    no elements exist
    """
    element_df = getattr(feeder, feeder_attribute).copy()

    if len(element_df) == 0:
        return gpd.GeoDataFrame()

    # merge coordinates from feeder.buses
    df = element_df.copy()
    df['name'] = df.index
    df = df.merge(feeder.buses, left_on='short_bus1', right_on='name')
    # create geometry from joined coordinates
    gdf = gpd.GeoDataFrame(
        df,
        crs=input_crs,
        geometry=gpd.points_from_xy(df.longitude, df.latitude))

    return gdf


def collect_line_type_gdf(
        feeder,
        feeder_attribute,
        input_crs=4326,
        ):
    """
    return geodataframe of line type elements from feeder or empty gdf if
    no elements exist
    """
    element_df = getattr(feeder, feeder_attribute).copy()

    if len(element_df) == 0:
        return gpd.GeoDataFrame()

    element_df['element_name'] = element_df.index

    # merge coordinates from feeder.buses
    bus1_df = element_df.merge(feeder.buses,
                               left_on='short_bus1', right_on='name')
    bus2_df = element_df.merge(feeder.buses,
                               left_on='short_bus2', right_on='name')

    # create points for each bus (1 and 2)
    bus1_df['point_geo_1'] = [Point(x, y) for x, y in
                              zip(bus1_df.longitude, bus1_df.latitude)]
    bus2_df['point_geo_2'] = [Point(x, y) for x, y in
                              zip(bus2_df.longitude, bus2_df.latitude)]

    # merge bus dfs
    buses_df = bus1_df.merge(bus2_df, on='element_name')

    # list comprehend line geo
    buses_df['line_geo'] = [LineString([x, y]) for x, y in
                            zip(buses_df.point_geo_1, buses_df.point_geo_2)]

    # clean up line dataframe
    geo_df = buses_df[['short_bus1_x', 'element_name', 'line_geo']].copy()

    # merge bus information
    geo_bus_df = feeder.buses.merge(geo_df,
                                    left_on='name', right_on='short_bus1_x')

    # merge capacity from feeder.capacity
    cap_df = element_df.merge(feeder.capacity, on='name')
    cap_df['element_name'] = cap_df.index

    # merge geo to capacity df
    res_df = cap_df.merge(geo_bus_df, left_on='name', right_on='element_name')

    # res_df.set_index('element_name_x', inplace=True)
    # res_df.index.rename('name', inplace=True)  # removed shortname as index

    cols_to_drop = [
        'type',  'kv_base', 'numphases', 'phases_x',
        'element_name_x',
        'longitude', 'latitude', 'short_bus1_x',
        'distance', 'element_name_y', 'geometry',
        'p_kw_net', 'q_kvar_net', 's_kva_net',
        ]

    # list comprehend to only drop existing columns.
    cols_to_drop = [x for x in cols_to_drop if x in res_df.columns]
    res_df.drop(columns=cols_to_drop, inplace=True)

    cols_to_rename = {'kvbase': 'kv_base',
                      'line_geo': 'geometry', 'longname': 'long_name'}
    res_df.rename(columns=cols_to_rename, inplace=True)

    gdf = gpd.GeoDataFrame(
        res_df,
        geometry='geometry',
        crs=input_crs)

    return gdf


def export_gdf_as_gpkg(gdf, element_type, feeder, output_path):
    """
    Functionalization of gpgk export

    20230710 - edits to handle better relative output...
        should probably be revisited after more use.
    """
    # create output file name
    output_file_name = f"{feeder.name}_{element_type}.gpkg".lower()
    output_file_name = output_file_name.replace(' ', '_')

    cwd = os.getcwd()
    if output_path is None:
        output_path = cwd
    else:
        os.chdir(output_path)

    # export_location = os.path.join(output_path, output_file_name)
    export_location = output_file_name

    gdf.to_file(export_location, driver="GPKG")
    os.chdir(cwd)

    return os.path.join(output_path, export_location)


def phase_number_to_letter(
        phase_col,
        positive_sequence=True):
    """
    Function to turn a column of phase numbers (123) to alpha (abc).
    Assumes postive sequenc
    TODO: test for negative sequence?
    """
    if positive_sequence:
        phase_col = phase_col.str.replace('1', 'A')
        phase_col = phase_col.str.replace('2', 'B')
        phase_col = phase_col.str.replace('3', 'C')
    else:
        phase_col = phase_col.str.replace('1', 'A')
        phase_col = phase_col.str.replace('2', 'C')
        phase_col = phase_col.str.replace('3', 'B')
    return phase_col


def export_bus_gis(
        feeder,
        export_gpkg=True,
        input_crs=4326,
        output_crs=4326,
        output_path=None,
        ):
    """
    Export GIS for bus elements from feeder.
    If export_gpkg is False, return geodataframe instead.
    """
    if len(feeder.bus_voltages) == 0:
        return None

    # collect current powers
    feeder.merge_bus_net_powers()

    # merge coordinates from feeder.buses
    df = feeder.bus_voltages.copy()

    df['name'] = df.index
    df = df.merge(feeder.buses)

    # create geometry from joined coordinates
    gdf = gpd.GeoDataFrame(
        df,
        crs=input_crs,
        geometry=gpd.points_from_xy(df.longitude, df.latitude)
        )

    # modify crs if required
    if input_crs != output_crs:
        gdf.to_crs(output_crs, inplace=True)

    # clean up columns for export
    gdf['phases'] = phase_number_to_letter(gdf['phases'])

    voltage_columns = ['v1', 'v2', 'v3']
    gdf['max_v'] = gdf[voltage_columns].max(axis=1)
    gdf['min_v'] = gdf[voltage_columns].min(axis=1)
    gdf['ave_v'] = gdf[voltage_columns].mean(axis=1)

    column_order = ['name', 'kv_base', 'v1', 'ang1', 'v2', 'ang2',
                    'v3', 'ang3', 'max_v', 'min_v', 'ave_v',
                    'n_phases', 'phases', 'nodes',
                    'distance', 'primary', 'over_voltage', 'under_voltage',
                    'p_kw_net', 'q_kvar_net', 's_kva_net',
                    'geometry']

    gdf = gdf[column_order]

    # export gpkg
    if export_gpkg:
        return export_gdf_as_gpkg(gdf, 'buses', feeder, output_path)
    return gdf


def export_capacitor_gis(
        feeder,
        export_gpkg=True,
        input_crs=4326,
        output_crs=4326,
        output_path=None,
        ):
    """
    Export GIS for capacitor elements from feeder.
    """
    if len(feeder.capacitors) == 0:
        return None

    gdf = collect_point_type_gdf(feeder, 'capacitors', input_crs)

    # modify crs if required
    if input_crs != output_crs:
        gdf.to_crs(output_crs, inplace=True)

    # merge capaicty from feeder.capacity
    gdf = gdf.merge(feeder.capacity, left_on='name', right_on='name')
    # clean up columns for export
    gdf.set_index('name', inplace=True)
    cols_to_drop = ['longitude', 'latitude', 'kv_base', 'phases_x',
                    'type', 'numphases', 'totalcustomers', 'numcustomers']
    cols_to_rename = {'kvar_x': 'kvar_rated', 'kvar_y': 'kvar',
                      'kvbase': 'kv_base', 'phases_y': 'phases'}

    gdf.drop(columns=cols_to_drop, inplace=True)
    gdf.rename(columns=cols_to_rename, inplace=True)
    gdf['phases'] = phase_number_to_letter(gdf['phases'])

    # export gpkg
    if export_gpkg:
        return export_gdf_as_gpkg(gdf, 'capacitors', feeder, output_path)
    return gdf


def export_fuse_gis(
        feeder,
        export_gpkg=True,
        input_crs=4326,
        output_crs=4326,
        output_path=None,
        ):
    """
    Export GIS for fuse elements from feeder.
    """
    if len(feeder.fuses) == 0:
        return None

    element_df = feeder.fuses.copy()

    # merge coordinates from feeder.buses
    df = element_df.copy()
    df['fuse_name'] = df.index
    df = df.merge(feeder.buses, left_on='short_bus1', right_on='name')
    # create geometry from joined coordinates
    gdf = gpd.GeoDataFrame(df,
                           crs=input_crs,
                           geometry=gpd.points_from_xy(df.longitude,
                                                       df.latitude))

    # modify crs if required
    if input_crs != output_crs:
        gdf.to_crs(output_crs, inplace=True)

    # clean up columns for export
    gdf.set_index('fuse_name', inplace=True)

    cols_to_drop = ['longitude', 'latitude', 'n_phases', 'phases', 'idx']
    cols_to_rename = {'numphases': 'n_phases', }

    gdf.drop(columns=cols_to_drop, inplace=True)
    gdf.rename(columns=cols_to_rename, inplace=True)

    # export gpkg
    if export_gpkg:
        return export_gdf_as_gpkg(gdf, 'fuses', feeder, output_path)
    return gdf


def export_generator_gis(
        feeder,
        export_gpkg=True,
        input_crs=4326,
        output_crs=4326,
        output_path=None,
        ):
    """
    Export GIS for generator elements from feeder.
    """
    if len(feeder.generators) == 0:
        return None

    gdf = collect_point_type_gdf(feeder, 'generators', input_crs)

    # modify crs if required
    if input_crs != output_crs:
        gdf.to_crs(output_crs, inplace=True)

    # clean up columns for export
    gdf.set_index('name', inplace=True)
    cols_to_drop = ['longitude', 'latitude', 'phases_x']
    cols_to_rename = {'kv_base': 'kv_phase', 'kv': 'kv_base'}

    gdf.drop(columns=cols_to_drop, inplace=True)
    gdf.rename(columns=cols_to_rename, inplace=True)

    # export gpkg
    if export_gpkg:
        return export_gdf_as_gpkg(gdf, 'generators', feeder, output_path)
    return gdf


def export_line_gis(
        feeder,
        export_gpkg=True,
        input_crs=4326,
        output_crs=4326,
        output_path=None,
        ):
    """
    Export GIS for line elements from feeder.
    If export_gpkg is False, return geodataframe instead.
    """
    if len(feeder.lines) == 0:
        return None

    gdf = collect_line_type_gdf(feeder, 'lines', input_crs)

    cols_to_rename = {'phases_y': 'phases'}
    gdf.rename(columns=cols_to_rename, inplace=True)
    # correct data type
    cols_to_numeric = ['length', 'normamps', 'emergamps', 'totalcust']
    for col in cols_to_numeric:
        gdf[col] = pd.to_numeric(gdf[col])

    gdf['phases'] = phase_number_to_letter(gdf['phases'])

    # modify crs if required
    if input_crs != output_crs:
        gdf.to_crs(output_crs, inplace=True)

    # export gpkg
    if export_gpkg:
        return export_gdf_as_gpkg(gdf, 'lines', feeder, output_path)
    return gdf


def export_load_gis(
        feeder,
        export_gpkg=True,
        input_crs=4326,
        output_crs=4326,
        output_path=None,
        ):
    """
    Export GIS for load elements from feeder.
    """
    if len(feeder.loads) == 0:
        return None

    gdf = collect_point_type_gdf(feeder, 'loads', input_crs)

    # modify crs if required
    if input_crs != output_crs:
        gdf.to_crs(output_crs, inplace=True)

    # clean up columns for export
    gdf.set_index('name', inplace=True)
    cols_to_drop = ['longitude', 'latitude', 'n_phases', 'phases_y',
                    'kv_base']
    cols_to_rename = {'phases_x': 'n_phases', 'kvar_y': 'kvar',
                      'kv': 'kv_base'}

    gdf.drop(columns=cols_to_drop, inplace=True)
    gdf.rename(columns=cols_to_rename, inplace=True)

    # export gpkg
    if export_gpkg:
        return export_gdf_as_gpkg(gdf, 'loads', feeder, output_path)
    return gdf


def export_pv_gis(
        feeder,
        export_gpkg=True,
        input_crs=4326,
        output_crs=4326,
        output_path=None,
        ):
    """
    Export GIS for pv system elements from feeder.
    """
    if len(feeder.pv_systems) == 0:
        return None

    gdf = collect_point_type_gdf(feeder, 'pv_systems', input_crs)

    # modify crs if required
    if input_crs != output_crs:
        gdf.to_crs(output_crs, inplace=True)

    # clean up columns for export
    gdf.set_index('name', inplace=True)
    cols_to_drop = ['longitude', 'latitude', 'n_phases', 'phases_y',
                    'kv_base']
    cols_to_rename = {'phases_x': 'n_phases',
                      'kv': 'kv_base'}

    gdf.drop(columns=cols_to_drop, inplace=True)
    gdf.rename(columns=cols_to_rename, inplace=True)

    # export gpkg
    if export_gpkg:
        return export_gdf_as_gpkg(gdf, 'pv_systems', feeder, output_path)
    return gdf


def export_reactor_gis(
        feeder,
        export_gpkg=True,
        input_crs=4326,
        output_crs=4326,
        output_path=None,
        ):
    """
    Export GIS for reactor elements from feeder.
    If export_gpkg is False, return geodataframe instead.
    """
    if len(feeder.reactors) == 0:
        return None

    gdf = collect_line_type_gdf(feeder, 'reactors', input_crs)
    cols_to_drop = ['n_phases_x', 'kv_base']
    cols_to_rename = {'n_phases_y': 'n_phases',
                      'kv': 'kv_base'}
    gdf.drop(columns=cols_to_drop, inplace=True)
    gdf.rename(columns=cols_to_rename, inplace=True)

    gdf['phases'] = phase_number_to_letter(gdf['phases'])

    # modify crs if required
    if input_crs != output_crs:
        gdf.to_crs(output_crs, inplace=True)

    # export gpkg
    if export_gpkg:
        return export_gdf_as_gpkg(gdf, 'reactors', feeder, output_path)
    return gdf


def export_storage_gis(
        feeder,
        export_gpkg=True,
        input_crs=4326,
        output_crs=4326,
        output_path=None,
        ):
    """
    Export GIS for storage elements from feeder.
    """
    if len(feeder.storages) == 0:
        return None

    gdf = collect_point_type_gdf(feeder, 'storages', input_crs)

    # modify crs if required
    if input_crs != output_crs:
        gdf.to_crs(output_crs, inplace=True)

    # clean up columns for export
    gdf.set_index('name', inplace=True)

    cols_to_drop = ['longitude', 'latitude', 'n_phases_y', 'phases', 'kv']
    gdf.drop(columns=cols_to_drop, inplace=True)

    cols_to_rename = {'n_phases_x': 'n_phases'}

    gdf.rename(columns=cols_to_rename, inplace=True)

    # export gpkg
    if export_gpkg:
        return export_gdf_as_gpkg(gdf, 'storages', feeder, output_path)
    return gdf


def export_switch_gis(
        feeder,
        export_gpkg=True,
        input_crs=4326,
        output_crs=4326,
        output_path=None,
        ):
    """
    Export GIS for switch elements from feeder.
    If export_gpkg is False, return geodataframe instead.
    """
    if len(feeder.switches) == 0:
        return None

    gdf = collect_line_type_gdf(feeder, 'switches', input_crs)
    # correct data type
    cols_to_numeric = ['length', 'normamps', 'emergamps']
    for col in cols_to_numeric:
        gdf[col] = pd.to_numeric(gdf[col])

    # clean remaining columns
    cols_to_drop = ['totalcust']
    cols_to_rename = {'phases_y': 'phases',
                      'kv': 'kv_base'}
    gdf.drop(columns=cols_to_drop, inplace=True)
    gdf.rename(columns=cols_to_rename, inplace=True)
    gdf['phases'] = phase_number_to_letter(gdf['phases'])

    # modify crs if required
    if input_crs != output_crs:
        gdf.to_crs(output_crs, inplace=True)

    # export gpkg
    if export_gpkg:
        return export_gdf_as_gpkg(gdf, 'switches', feeder, output_path)
    return gdf


def export_transformer_gis(
        feeder,
        input_crs=4326,
        output_crs=4326,
        output_path=None,
        export_gpkg=True,
        as_centroid=False,):
    """
    Export GIS for transformer elements from feeder.
    If export_gpkg is False, return geodataframe instead.
    Default action is to export as lines.
    TODO: allow for conversion to points to reduce confusion
    """
    if len(feeder.transformers) == 0:
        return None

    gdf = collect_line_type_gdf(feeder, 'transformers', input_crs)

    cols_to_rename = {'phases_y': 'phases'}
    gdf.rename(columns=cols_to_rename, inplace=True)
    gdf['phases'] = phase_number_to_letter(gdf['phases'])

    # modify crs if required
    if input_crs != output_crs:
        gdf.to_crs(output_crs, inplace=True)

    # TODO: convert to points if as_lines is False
    if as_centroid:
        gdf['geometry'] = gdf['geometry'].centroid

    # export gpkg
    if export_gpkg:
        return export_gdf_as_gpkg(gdf, 'transformers', feeder, output_path)
    return gdf


def export_voltage_regulator_gis(
        feeder,
        export_gpkg=True,
        input_crs=4326,
        output_crs=4326,
        output_path=None,
        ):
    """
    Export GIS for voltage regulator elements from feeder.
    As multipoint where first point is monitored bus location and the
    second point is the transformer location.
    """
    if len(feeder.voltage_regulators) == 0:
        return None

    reg_df = feeder.voltage_regulators.copy()
    bus_df = feeder.buses.copy()

    # collect points for monitored bus
    bus_df['short_bus_name'] = bus_df.index
    reg_df['reg_name'] = reg_df.index

    # collect points for monitored bus
    pt_geo = pd.merge(
        reg_df, 
        bus_df[[
            'short_bus_name',
            'longitude',
            'latitude']],
        left_on='short_monitoredbus',
        right_on='short_bus_name')

    pt_geo['monitoredbus_geo'] = [Point(x, y) for x, y in
                                  zip(pt_geo.longitude, pt_geo.latitude)]
    cols_2_drop = ['short_bus_name', 'longitude', 'latitude']
    pt_geo.drop(columns=cols_2_drop, inplace=True)

    # collect points for transformer bus
    pt_geo = pd.merge(
        pt_geo,
        bus_df[[
            'short_bus_name',
            'longitude',
            'latitude']],
        left_on='transformer_short_bus1',
        right_on='short_bus_name')

    pt_geo['transformer_geo'] = [Point(x, y) for x, y in
                                 zip(pt_geo.longitude, pt_geo.latitude)]
    cols_2_drop = ['short_bus_name', 'longitude', 'latitude']
    pt_geo.drop(columns=cols_2_drop, inplace=True)

    # create multipoint geometry
    pt_geo['geometry'] = [MultiPoint([x, y]) for x, y in
                          zip(pt_geo.monitoredbus_geo, pt_geo.transformer_geo)]

    pt_geo.drop(columns=['monitoredbus_geo', 'transformer_geo'], inplace=True)

    pt_geo.set_index('reg_name', inplace=True)
    pt_geo.index.rename('name', inplace=True)

    gdf = gpd.GeoDataFrame(pt_geo,
                           geometry='geometry',
                           crs=input_crs)

    # modify crs if required
    if input_crs != output_crs:
        gdf.to_crs(output_crs, inplace=True)

    # export gpkg
    if export_gpkg:
        return export_gdf_as_gpkg(
            gdf,
            'voltage_regulators',
            feeder,
            output_path)
    return gdf


def export_voltage_source_gis(
        feeder,
        export_gpkg=True,
        input_crs=4326,
        output_crs=4326,
        output_path=None,
        ):
    """
    Export GIS for voltage source elements from feeder.
    """
    if len(feeder.voltage_sources) == 0:
        return None

    gdf = collect_point_type_gdf(feeder, 'voltage_sources', input_crs)

    # modify crs if required
    if input_crs != output_crs:
        gdf.to_crs(output_crs, inplace=True)

    # clean up columns for export
    gdf.set_index('name', inplace=True)
    cols_to_drop = ['longitude', 'latitude', 'phases_x']
    cols_to_rename = {'base_kv': 'kv_line',
                      'phases_y': 'phases'}

    gdf.drop(columns=cols_to_drop, inplace=True)
    gdf.rename(columns=cols_to_rename, inplace=True)
    gdf['phases'] = phase_number_to_letter(gdf['phases'])

    # export gpkg
    if export_gpkg:
        return export_gdf_as_gpkg(gdf, 'voltage_sources', feeder, output_path)
    return gdf
