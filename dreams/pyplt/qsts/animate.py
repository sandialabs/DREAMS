"""
Functions to animate feeder flows
"""
import os
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from shapely.geometry import Point
import opendssdirect as dssdirect
import dreams
import contextily as cx


def get_line_flow_key(feeder):
    """
    Based of current state of passed in feeder, create line flow key
    to help with identifying reverse flow.
    """
    line_gdf = dreams.gis.export_line_gis(feeder, export_gpkg=False)
    line_flow_key = line_gdf.kw > 1e-3
    return line_flow_key


def plot_feeder_flow(
        feeder,
        line_scale=50,  # scales Amp flow
        line_min=0.5,
        marker_scale=1,  # scales kw of load
        marker_min=5,
        source_scale=1/10,  # scales source kw
        source_min=5,
        line_flow_key=None,
        anon_plot=True,
        show_storage=False,
        storage_offset=-0.0002,
        show_pv=False,
        pv_offset=0.0002,
        ax=None,
        cx_type=None,
        input_crs=None,
        cx_zoom=10,
        generation_only=False,
        load_color='cyan',
        generator_color='magenta'
        ):
    """
    Plot feeder topology with flow indictions on buses, and amp indicators
    on lines.
    optionally show storages or pv systems.
    """
    if ax is None:
        fig = plt.figure()
        ax = fig.add_subplot(111)
    else:
        fig = plt.gcf()

    feeder.update_capacity()
    feeder.update_powers()
    if input_crs is None:
        raw_source = dreams.gis.export_voltage_source_gis(
            feeder,
            export_gpkg=False)
        input_crs = raw_source.crs.to_string()

    bus_gdf = dreams.gis.export_bus_gis(
        feeder, export_gpkg=False, input_crs=input_crs)
    line_gdf = dreams.gis.export_line_gis(
        feeder, export_gpkg=False, input_crs=input_crs)

    line_gdf['amps_norm'] = abs(
        line_gdf['normamps'] * line_gdf['%normal'] / 100)

    voltage_source = dreams.gis.export_voltage_source_gis(
        feeder,
        export_gpkg=False,
        input_crs=input_crs)

    line_width = line_gdf['amps_norm']/line_scale + line_min

    v_source_power = dssdirect.Circuit.TotalPower()[0]

    if line_flow_key is None:
        # do not indicate flow
        line_gdf.plot(
            aspect=1,
            column='amps_norm',
            linewidth=line_width,
            color='black',
            zorder=1,
            label='Line',
            ax=ax,
            capstyle='round'
        )
    else:
        # positive kw mask is defined, look for directionality.
        current_flow = get_line_flow_key(feeder)
        positive_flow_mask = line_flow_key == current_flow
        if sum(positive_flow_mask) > 0:
            line_gdf[positive_flow_mask].plot(
                aspect=1,
                column='amps_norm',
                linewidth=line_width[positive_flow_mask],
                color='black',
                zorder=1,
                label='Normal Flow',
                ax=ax,
                capstyle='round'
            )

        # check for negative flow
        negative_flow_mask = ~positive_flow_mask
        if sum(negative_flow_mask) > 0:
            line_gdf[negative_flow_mask].plot(
                aspect=1,
                column='amps_norm',
                linewidth=line_width[negative_flow_mask],
                color='red',
                zorder=1,
                label='Reverse Flow',
                capstyle='round',
                ax=ax
            )

    if v_source_power <= 0:
        # normal generation
        v_color = generator_color
        v_source_name = 'Voltage Source'
    else:
        v_color = load_color
        v_source_name = 'Voltage Source (Reverse Flow)'

    if not generation_only:
        voltage_source.plot(
            aspect=1,
            ax=ax,
            zorder=3,
            color=v_color,
            marker="o",
            markersize=abs(v_source_power) * source_scale + source_min,
            edgecolor='grey',
            linewidth=1,
            )

        voltage_source.plot(
            aspect=1,
            ax=ax,
            zorder=3,
            color='grey',
            marker='*',
            markersize=(abs(v_source_power) * source_scale + source_min)*0.25,
            linewidth=1,
            label=v_source_name
            )

    gen_bus = bus_gdf[bus_gdf.p_kw_net < 0]
    if len(gen_bus) > 0:
        gen_bus.plot(
            aspect=1,
            column='p_kw_net',
            ax=ax,
            color=generator_color,
            edgecolor='black',
            linewidth=0.25,
            markersize=abs(gen_bus['p_kw_net']) * marker_scale + marker_min,
            zorder=3,
            label='Net Generation Bus'
        )

    if not generation_only:
        load_bus = bus_gdf[bus_gdf.p_kw_net > 0]
        if len(load_bus) > 0:
            load_bus.plot(
                aspect=1,
                column='p_kw_net',
                ax=ax,
                color=load_color,
                edgecolor='black',
                linewidth=0.25,
                markersize=abs(load_bus['p_kw_net']) * marker_scale + marker_min,
                zorder=3,
                label='Net Load Bus'
            )

    if feeder.stats['n_storages'] > 0 and show_storage:
        storage_geo = dreams.gis.export_storage_gis(
            feeder,
            export_gpkg=False,
            input_crs=input_crs)

        storage_geo['geometry'] = storage_geo['geometry'].apply(
            lambda geom: Point(
                geom.x + storage_offset,
                geom.y + storage_offset)
                )
        storage_geo.plot(
            aspect=1,
            color='lightgrey',
            label='Storage',
            zorder=2,
            markersize=40,
            edgecolor='black',
            linewidth=0.5,
            marker='s',
            alpha=0.75,
            ax=ax,
        )

    if feeder.stats['n_pv'] > 0 and show_pv:
        pv_geo = dreams.gis.export_pv_gis(
            feeder,
            export_gpkg=False,
            input_crs=input_crs)

        pv_geo['geometry'] = pv_geo['geometry'].apply(
            lambda geom: Point(
                geom.x + pv_offset,
                geom.y + pv_offset)
                )
        pv_geo.plot(
            aspect=1,
            color='yellow',
            label='PV System',
            zorder=2,
            markersize=40,
            edgecolor='black',
            linewidth=0.5,
            marker='*',
            alpha=0.75,
            ax=ax,
        )

    if anon_plot:
        ax.xaxis.set_visible(False)
        ax.yaxis.set_visible(False)

    valid_cx_type = {
        'osm': cx.providers.OpenStreetMap.Mapnik,
        'esri': cx.providers.Esri.WorldImagery,
        'carto': cx.providers.CartoDB.Voyager
    }

    if cx_type in valid_cx_type:
        cx.add_basemap(
            ax,
            zoom=cx_zoom,  # higher = more res
            crs=line_gdf.crs.to_string(),
            source=valid_cx_type[cx_type],
            attribution=False,  # removes source of map text from image
            )

    # Create a new axis for the legend
    #  x, y, then x, y, span - only first two matter due to hidding
    legend_ax = fig.add_axes([1.2, 0.75, 0, 0])

    # Copy legend elements to the new legend
    handles, labels = ax.get_legend_handles_labels()
    legend_ax.legend(handles, labels)

    # Hide the new axis
    legend_ax.axis('off')
    return (fig, ax)


def plot_feeder_violations(
        feeder,
        line_scale=50,  # scales Amp flow
        line_min=0.5,
        marker_scale=1,  # scales kw of load
        marker_min=60,
        source_scale=1/10,  # scales source kw
        source_min=60,
        line_flow_key=None,
        anon_plot=True,
        show_storage=True,
        storage_offset=-0.0002,
        show_pv=True,
        pv_offset=0.0002,
        ax=None,
        cx_type=None,
        input_crs=None,
        cx_zoom=10,
        reverse_flow_color='cyan',
        figsize=None,
        ):
    """
    Plot feeder topology with flow indictions on buses, and amp indicators
    on lines.
    optionally show storages or pv systems.
    """
    if ax is None:
        if figsize is None:
            fig = plt.figure()
        else:
            fig = plt.figure(figsize=figsize)

        ax = fig.add_subplot(111)
    else:
        fig = plt.gcf()

    feeder.update_capacity()
    feeder.update_powers()
    if input_crs is None:
        raw_source = dreams.gis.export_voltage_source_gis(
            feeder,
            export_gpkg=False)
        input_crs = raw_source.crs.to_string()

    bus_gdf = dreams.gis.export_bus_gis(
        feeder, export_gpkg=False, input_crs=input_crs)

    line_gdf = dreams.gis.export_line_gis(
        feeder, export_gpkg=False, input_crs=input_crs)

    xfmr_gdf = dreams.gis.export_transformer_gis(
        feeder, export_gpkg=False, input_crs=input_crs, as_centroid=True)

    line_gdf['amps_norm'] = abs(
        line_gdf['normamps'] * line_gdf['%normal'] / 100)

    voltage_source = dreams.gis.export_voltage_source_gis(
        feeder,
        export_gpkg=False,
        input_crs=input_crs)

    line_width = line_gdf['amps_norm']/line_scale + line_min

    v_source_power = dssdirect.Circuit.TotalPower()[0]

    if line_flow_key is None:
        # do not indicate flow
        line_gdf.plot(
            aspect=1,
            column='amps_norm',
            linewidth=line_width,
            color='black',
            zorder=1,
            label='Line',
            ax=ax,
            capstyle='round'
        )
    else:
        # positive kw mask is defined, look for directionality.
        current_flow = get_line_flow_key(feeder)
        positive_flow_mask = line_flow_key == current_flow
        if sum(positive_flow_mask) > 0:
            line_gdf[positive_flow_mask].plot(
                aspect=1,
                column='amps_norm',
                linewidth=line_width[positive_flow_mask],
                color='black',
                zorder=1,
                label='Normal Flow',
                ax=ax,
                capstyle='round'
            )

        # check for negative flow
        negative_flow_mask = ~positive_flow_mask
        if sum(negative_flow_mask) > 0:
            line_gdf[negative_flow_mask].plot(
                aspect=1,
                column='amps_norm',
                linewidth=line_width[negative_flow_mask],
                color=reverse_flow_color,
                zorder=1,
                label='Reverse Flow',
                capstyle='round',
                ax=ax
            )

    v_color='white'
    if v_source_power <= 0:
        # normal generation
        v_source_name = 'Voltage Source'
    else:
        v_source_name = 'Voltage Source (Reverse Flow)'

    voltage_source.plot(
        aspect=1,
        ax=ax,
        zorder=4,
        color=v_color,
        marker='o',
        markersize=(abs(v_source_power) * source_scale + source_min)*0.25,
        linewidth=1,
        edgecolor='black',
        label=v_source_name
    )


    if feeder.stats['n_storages'] > 0 and show_storage:
        storage_geo = dreams.gis.export_storage_gis(
            feeder,
            export_gpkg=False,
            input_crs=input_crs)

        storage_geo['geometry'] = storage_geo['geometry'].apply(
            lambda geom: Point(
                geom.x + storage_offset,
                geom.y + storage_offset)
                )
        storage_geo.plot(
            aspect=1,
            color='lightgrey',
            label='Storage',
            zorder=1,
            markersize=marker_min,
            edgecolor='black',
            linewidth=0.5,
            marker='s',
            #alpha=0.75,
            ax=ax,
        )

    if feeder.stats['n_pv'] > 0 and show_pv:
        pv_geo = dreams.gis.export_pv_gis(
            feeder,
            export_gpkg=False,
            input_crs=input_crs)

        pv_geo['geometry'] = pv_geo['geometry'].apply(
            lambda geom: Point(
                geom.x + pv_offset,
                geom.y + pv_offset)
                )
        pv_geo.plot(
            aspect=1,
            color='white',
            label='PV System',
            zorder=3,
            markersize=marker_min,
            edgecolor='black',
            linewidth=0.3,
            marker='*',
            #alpha=0.75,
            ax=ax,
        )

    # violations...
    line_overloads = line_gdf['%normal'] > 100
    line_gdf[line_overloads].plot(
        linewidth=line_width[line_overloads],
        aspect=1,
        color='orange',
        label='Overloaded Line',
        ax=ax,
        zorder=4)

    voltage_violation = bus_gdf['over_voltage'] | bus_gdf['under_voltage']
    bus_gdf[voltage_violation].plot(
        aspect=1,
        color='yellow',
        label='Voltage Violation',
        ax=ax,
        edgecolor='black',
        linewidth=0.5,
        zorder=2)

    xfmr_overloads = xfmr_gdf['%normal'] > 100
    xfmr_gdf[xfmr_overloads].plot(
        aspect=1,
        color='red',
        label='Overloaded Transformer',
        ax=ax,
        marker='s',
        edgecolor='black',
        linewidth=0.5,
        zorder=3)

    if anon_plot:
        ax.xaxis.set_visible(False)
        ax.yaxis.set_visible(False)

    valid_cx_type = {
        'osm': cx.providers.OpenStreetMap.Mapnik,
        'esri': cx.providers.Esri.WorldImagery,
        'carto': cx.providers.CartoDB.Voyager
    }

    if cx_type in valid_cx_type:
        cx.add_basemap(
            ax,
            zoom=cx_zoom,  # higher = more res
            crs=line_gdf.crs.to_string(),
            source=valid_cx_type[cx_type],
            attribution=False,  # removes source of map text from image
            )

    # Create a new axis for the legend
    #  x, y, then x, y, span - only first two matter due to hidding
    legend_ax = fig.add_axes([1.2, 0.75, 0, 0])

    # Copy legend elements to the new legend
    handles, labels = ax.get_legend_handles_labels()
    legend_ax.legend(handles, labels)

    # Hide the new axis
    legend_ax.axis('off')
    return (fig, ax)


def make_feeder_flow_animation(
        scenario,
        output_path,
        seed=None,
        scenario_step=None,
        frame_delay=1000,
        animation_name='feeder_flow',
        sup_title='',
        export_frames=False
        ):
    """
    stuff
    """
    feeder = scenario.feeder

    # check for created steps
    if not scenario.steps_created:
        # write steps
        print('making seeds.')
        scenario.create_simulation_seeds()

    # check if seed exists
    if seed is None:
        seed = scenario.all_seeds[0]
    else:
        if seed not in scenario.all_seeds:
            print('invalid seed...')
            seed = scenario.all_seeds[0]

    # check if step exists
    if scenario_step is None:
        # choose first step
        scenario_step = list(scenario.seed[seed].keys())[0]
    else:
        if scenario_step not in list(scenario.seed[seed].keys()):
            print('invalid step...')
            scenario_step = list(scenario.seed[seed].keys())[0]

    # restart feeder
    scenario.go_to_step(seed=seed, step=scenario_step, qsts_step=0)
    feeder.restart()

    # run redirects
    scenario.execute_control_redirects(scenario_step)
    scenario.execute_base_redirects()

    # run step redirects
    for _, redirect in scenario.seed[seed][scenario_step].items():
        redirect.execute()

    scenario.init_qsts()
    line_flow_key = dreams.pyplt.qsts.get_line_flow_key(feeder)

    qsts_step = 0
    # attempt animation..
    num_frames = int(scenario.duration_seconds / scenario.qsts_step_size_sec)

    fig, ax = plt.subplots(1, 1)
    fig.set_size_inches(10, 6)

    feeder.solve()
    dreams.pyplt.qsts.plot_feeder_flow(
        feeder,
        line_flow_key=line_flow_key,
        ax=ax)

    ax.set_title(f'{sup_title}\nScenario Step {scenario_step}, QSTS Step {qsts_step}')

    def update(frame):
        ax.clear()
        feeder.solve()
        dreams.pyplt.qsts.plot_feeder_flow(
            feeder, line_flow_key=line_flow_key, ax=ax)
        ax.set_title(f'{sup_title}\nScenario Step {scenario_step}, QSTS Step {frame}')

        if export_frames:
            frame_folder = os.path.join(output_path, f"{animation_name}_frames")
            os.makedirs(frame_folder, exist_ok=True)
            fig.savefig(os.path.join(frame_folder, f"{animation_name}_frame_{frame}.png"))
        return (fig, ax)

    animation = FuncAnimation(
        plt.gcf(),
        update,
        frames=num_frames,
        interval=frame_delay)

    animation.save(os.path.join(output_path, f"{animation_name}.gif"))
