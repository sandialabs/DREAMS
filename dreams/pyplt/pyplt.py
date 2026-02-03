"""
Updated python plotting functions that utilize class approach
and updated dataframe collections.

Mostly for general feeder information and snapshot results.
"""
import os
import warnings
import matplotlib.pyplot as plt
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import pandas as pd

import dreams

warnings.simplefilter("ignore", UserWarning)  # for CRS warning on centroids


def save_pyplot(fig,
                plot_name,
                output_directory=None):
    """
    Standard function to handle saving figure to directory that may
    or may not exist.
    """
    if output_directory is None:
        output_directory = os.getcwd()
    else:
        if not os.path.exists(output_directory):
            os.mkdir(output_directory)

    output_path = os.path.join(output_directory, plot_name)
    fig.savefig(output_path,
                facecolor='white',
                transparent=False)


def plotly_voltage_profile(
        feeder,
        secondary_kv_limit=0.5,
        width=900,
        height=600,
        ):
    """
    Create interactive plotly plot.  Originally zoomed to ANSI voltage
    violation range.
    Use the Autoscale button to scale view to all data.
    TODO Handle fully identified secondary phases
    """
    # maniuplate data into form useful for plotly express
    columns_to_plot = ['v1', 'v2', 'v3', 'distance', 'kv_base']

    voltages_df = feeder.bus_voltages[columns_to_plot].copy()
    voltages_df.reset_index(inplace=True)
    voltages_df['primary'] = voltages_df['kv_base'] > secondary_kv_limit

    voltage_name = ['v1', 'v2', 'v3']
    phase_name = ['A', 'B', 'C']
    # handle primary voltages
    primary_mask = voltages_df['primary']
    df_to_concat = []
    for v_col, phase in zip(voltage_name, phase_name):
        pv_data = voltages_df[primary_mask].copy()
        pv_data = pv_data[['name', v_col, 'distance', 'kv_base']]
        pv_data.rename(columns={v_col: 'voltage'}, inplace=True)
        pv_data['phase'] = f"{phase} Primary"
        df_to_concat.append(pv_data)

    # handle secondary voltages
    for v_col, phase in zip(voltage_name, phase_name):
        secondary_data = voltages_df[~primary_mask].copy()
        secondary_data = secondary_data[['name', v_col, 'distance', 'kv_base']]
        secondary_data.rename(columns={v_col: 'voltage'}, inplace=True)
        secondary_data['phase'] = "Secondary"
        df_to_concat.append(secondary_data)

    plotly_express_df = pd.concat(df_to_concat)
    # this is likely not required anymore as most elements are manually renamed
    coloumn_rename = {
        'name': 'Bus Name',
        'voltage': 'Voltage [PU]',
        'distance': 'Distance from Substation [km]',
        'phase': 'Phase',
        'kv_base': 'kV Base'
    }
    plotly_express_df.rename(columns=coloumn_rename, inplace=True)

    # standard hover label format
    hovertemplate = r"""<b>Bus:  %{customdata[0]}</b><br>
    %{y:.4f} V PU<br>
    %{customdata[2]}<br>
    %{x:.2f} km from substation<br>
    %{customdata[1]:.2f} kV Base<extra></extra>
    """

    fig = px.scatter(
        plotly_express_df, x="Distance from Substation [km]",
        y="Voltage [PU]",
        color="Phase",
        hover_data=['Bus Name', 'kV Base', 'Phase']
        )

    # alter plotting order for secondary below primary
    fig.data = (fig.data[-1], fig.data[0], fig.data[1], fig.data[2])

    # add pv
    has_pv = False
    if len(feeder.pv_systems) > 0:
        has_pv = True
        pv_df = feeder.pv_systems.copy()
        columns_to_keep = [
            'kv', 'kva', 'bus1', 'short_bus1', 'bus1_nodes', 'bus1_phase'
        ]
        pv_df = pv_df[columns_to_keep]

        bus_columns = [
            'v1', 'v2', 'v3', 'distance'
        ]

        pv_dist = pd.merge(pv_df,
                           feeder.bus_voltages[bus_columns],
                           how='left',
                           left_on='short_bus1',
                           right_index=True
                           )

        pv_dist.reset_index(inplace=True)

        voltage_name = ['v1', 'v2', 'v3']
        phase_name = ['A', 'B', 'C']

        df_to_concat = []
        for v_col, phase in zip(voltage_name, phase_name):
            pv_data = pv_dist.copy()
            pv_data = pv_data[['name', v_col, 'distance', 'kv', 'bus1']]

            pv_data.rename(columns={v_col: 'voltage'}, inplace=True)
            pv_data['phase'] = f"PV on {phase} Phase"
            df_to_concat.append(pv_data)

        pv_concat = pd.concat(df_to_concat)

        pv_hoovertemplate = r"""<b>Bus:  %{customdata[0]}</b><br>
        %{y:.4f} V PU<br>
        Bus1 %{customdata[2]}<br>
        %{x:.2f} km from substation<br>
        %{customdata[1]:.2f} kV Base<extra></extra>
        """

        # marker 18 is hex star
        pv_fig = px.scatter(
            pv_concat, x="distance",
            y="voltage",
            color="phase",
            hover_data=['name', 'kv', 'bus1'],
            )

        # manully color voltage points
        pv_fig.data[0].marker.line = {'color': 'black', 'width': 1}
        pv_fig.data[1].marker.line = {'color': 'red', 'width': 1}
        pv_fig.data[2].marker.line = {'color': 'blue', 'width': 1}

        for n in range(0, 3):
            pv_fig.data[n].hovertemplate = pv_hoovertemplate
            pv_fig.data[n].marker.symbol = 18
            pv_fig.data[n].marker.color = 'yellow'

    # manully color voltage points
    fig.data[0].marker.color = 'orange'
    fig.data[1].marker.color = 'black'
    fig.data[2].marker.color = 'red'
    fig.data[3].marker.color = 'blue'

    # manually set hover template
    fig.data[0].hovertemplate = hovertemplate
    fig.data[1].hovertemplate = hovertemplate
    fig.data[2].hovertemplate = hovertemplate
    fig.data[3].hovertemplate = hovertemplate

    # make limit dash lines
    x_lim = [0, plotly_express_df['Distance from Substation [km]'].max()]
    limit_line_style = {'color': 'grey', 'width': 2, 'dash': 'dot'}
    over_voltage_fig = go.Figure(
        go.Scatter(
            x=x_lim,
            y=[1.05, 1.05],
            line=limit_line_style,
            name='Over Voltage',
            showlegend=False
        )
    )

    under_voltage_fig = go.Figure(
        go.Scatter(
            x=x_lim,
            y=[0.95, 0.95],
            line=limit_line_style,
            name='Under Voltage',
            showlegend=False
        )
    )

    # combine voltage limits to phas voltage data
    fig = go.Figure(data=over_voltage_fig.data +
                    under_voltage_fig.data +
                    fig.data)

    if has_pv:
        # combine pv fig to other voltages
        fig = go.Figure(data=pv_fig.data + fig.data)
        # TODO explore if possible to put pv on top... seems oddly hard.

    fig.update_layout(
        title={'text': f"{feeder.name}<br>Voltage Profile",
               'y': 0.9,
               'x': 0.5,
               'xanchor': 'center',
               'yanchor': 'top',
               },
        xaxis_title="Distance from Substation [km]",
        yaxis_title="Voltage [PU]",
        width=width,
        height=height,
        yaxis_range=[0.94, 1.06],
        hoverlabel={'font_size': 16},
            )
    # 1080, 720  # another possibly useful size

    # for traces to axis...
    fig.update_xaxes(showspikes=True, spikethickness=1)
    fig.update_yaxes(showspikes=True, spikethickness=1)

    fig.show()

    return fig


def plot_topology(
        feeder,
        anon_plot=True,
        equal_aspect=False,
        plot_substation=True,
        fig_size=(11, 8),
        show_plot=True,
        save_figure=False,
        output_directory=None,
        ax=None,
        **kwargs
                  ):
    """
    Attempt at basic topology plot using data frame approach
    """
    if ax is None:
        fig = plt.figure(figsize=fig_size)
        ax = fig.add_subplot(111)
    else:
        fig = plt.gcf()

    # redo of topo plot...
    line_geo = dreams.gis.export_line_gis(feeder, export_gpkg=False)

    primary_mask = line_geo['primary']

    legend_entries = 1  # for primary lines

    if plot_substation:
        legend_entries += 1
        sub = dreams.gis.export_voltage_source_gis(feeder, export_gpkg=False)
        sub.plot(
            color=[0, 1, 0],
            zorder=4,
            label='Substation',
            edgecolor='black',
            linewidth=0.5,
            markersize=30,
            ax=ax,
            aspect=1)

    line_geo[primary_mask].plot(
        color='black',
        zorder=2,
        label='Primary',
        figsize=fig_size,
        ax=ax,
        aspect=1)

    if feeder.stats['n_secondary_lines'] > 0:
        legend_entries += 1
        line_geo[~primary_mask].plot(
            color='cyan',
            zorder=1,
            label='Secondary',
            ax=ax,
            aspect=1)

    if feeder.stats['n_transformers'] > 0:
        legend_entries += 1
        xfmr_geo = dreams.gis.export_transformer_gis(
            feeder,
            export_gpkg=False)
        xfmr_geo.plot(
            color='grey',
            linestyle='--',
            label='Transformer',
            zorder=2,
            ax=ax,
            aspect=1)
        xfmr_geo.centroid.plot(
            color='grey',
            zorder=3,
            markersize=1,
            marker='s',
            ax=ax,
            aspect=1,)

    if feeder.stats['n_switches'] > 0:
        legend_entries += 1
        switch_geo = dreams.gis.export_switch_gis(feeder, export_gpkg=False)
        switch_geo.plot(
            color='magenta',
            label='Switch',
            zorder=3,
            ax=ax,
            aspect=1
            )
        switch_geo.centroid.plot(
            color='magenta',
            zorder=3,
            markersize=1,
            marker='s',
            ax=ax,
            aspect=1)

    if feeder.stats['n_capacitors'] > 0:
        legend_entries += 1
        cap_geo = dreams.gis.export_capacitor_gis(feeder, export_gpkg=False)
        cap_geo.plot(
            color='red',
            label='Capacitor',
            zorder=3,
            markersize=10,
            marker='s',
            ax=ax,
            aspect=1
        )

    if feeder.stats['n_pv'] > 0:
        legend_entries += 1
        pv_geo = dreams.gis.export_pv_gis(feeder, export_gpkg=False)
        pv_geo.plot(
            color='yellow',
            edgecolor='black',
            linewidth=0.5,
            label='PV System',
            zorder=3,
            markersize=30,
            marker='*',
            ax=ax,
            aspect=1
            )

    if feeder.stats['n_generators'] > 0:
        legend_entries += 1
        gen_geo = dreams.gis.export_generator_gis(feeder, export_gpkg=False)
        gen_geo.plot(
            color='blue',
            edgecolor='black',
            linewidth=0.5,
            label='Generator',
            zorder=3,
            markersize=30,
            marker='$G$',
            ax=ax,
            aspect=1
            )
    if feeder.stats['n_storages'] > 0:
        legend_entries += 1
        gen_geo = dreams.gis.export_storage_gis(feeder, export_gpkg=False)
        gen_geo.plot(
            color='cyan',
            edgecolor='black',
            linewidth=0.5,
            label='Storage',
            zorder=3,
            markersize=30,
            marker='$S$',
            ax=ax,
            aspect=1
            )

    if feeder.stats['n_regulators'] > 0:
        legend_entries += 1
        vreg_geo = dreams.gis.export_voltage_regulator_gis(
            feeder,
            export_gpkg=False)
        vreg_geo.plot(
            color='white',
            edgecolor='black',
            linewidth=1.0,
            label='Voltage Regulator',
            zorder=3,
            markersize=80,
            marker='d',
            ax=ax,
            aspect=1
            )

    if anon_plot:
        ax.xaxis.set_visible(False)
        ax.yaxis.set_visible(False)

    if equal_aspect:
        plt.gca().set_aspect('equal')

    ax.set_title(f"{feeder.name}")

    # Put a legend below current axis
    if legend_entries > 4:
        n_columns = 4
    else:
        n_columns = int(legend_entries/2)
    ax.legend(loc='upper center',
              bbox_to_anchor=(0.5, -0.0666),
              fancybox=True,
              shadow=True,
              ncol=n_columns)

    plt.tight_layout()

    if save_figure:
        plot_name = f'{feeder.name}_topology.png'.lower()
        plot_name = plot_name.replace(' ', '_').replace('\\', '_')
        save_pyplot(fig,
                    plot_name,
                    output_directory=output_directory)

    if show_plot:
        plt.show(block=False)
    else:
        plt.close(fig)

    return (fig, ax)


def plot_voltage_box_whisker(
        feeder,
        secondary_kv_limit=0.5,
        show_limits=True,
        show_plot=True,
        save_figure=False,
        output_directory=None,
        zoom_to_limits=False,
        ):
    """
    Plot voltage box whisker by phase

    TODO: add options to indicate other elements, such as pv, caps, ev... etc
    TODO: revist once secondary phases are known. (graph process figured out)
    """
    primary_mask = feeder.bus_voltages['kv_base'] > secondary_kv_limit

    plot_secondary = False
    if sum(~primary_mask) > 0:
        plot_secondary = True

    voltage_colors = [[0, 0, 0], [1, 0, 0], [0, 0, 1],
                      [0.5, 0.5, 0.5], [1, 0.5, 0.5], [0.5, 0.5, 1]]
    secondary_color = [1, 0.678, 0]
    voltage_colors[3] = secondary_color

    # colled data to plot
    data_to_box = [
        feeder.bus_voltages[primary_mask]['v1'].dropna(),
        feeder.bus_voltages[primary_mask]['v2'].dropna(),
        feeder.bus_voltages[primary_mask]['v3'].dropna(),
        ]
    data_labels = [
        'A Primary',
        'B Primary',
        'C Primary',
        ]

    if plot_secondary:
        sec = [
            feeder.bus_voltages[~primary_mask]['v1'],
            feeder.bus_voltages[~primary_mask]['v2'],
            feeder.bus_voltages[~primary_mask]['v3'],
            ]
        data_to_box.append(pd.concat(sec).dropna())
        data_labels.append('Secondary')

    # create figure and subplots
    fig = plt.figure()
    ax = fig.add_subplot(111)

    box_plot = ax.boxplot(
        data_to_box,
        vert=1,
        notch='True',
        patch_artist=True,
        )

    # change face color of each 'patch'
    box_index = 0
    for patch in box_plot['boxes']:
        patch.set_facecolor(voltage_colors[box_index])
        box_index += 1

    # changing linewidth of caps
    for cap in box_plot['caps']:
        cap.set(linewidth=2)

    # changing linewidth of whiskers
    for whisker in box_plot['whiskers']:
        whisker.set(linewidth=2)

    # changing color and linewidth of  medians
    for median in box_plot['medians']:
        median.set(color='white', linewidth=0.5)

    ax.set_title(f"{feeder.name}\nVoltages")

    # ensure names are placed with data
    ax.set_xticklabels(data_labels)

    if show_limits:
        limit_x = [0.5, len(data_to_box)+0.5]
        ax.plot(
            limit_x,
            np.ones_like(limit_x)*1.05,
            '--',
            c=[.4, .4, .4],
            )
        ax.plot(
            limit_x,
            np.ones_like(limit_x)*0.95,
            '--',
            c=[.4, .4, .4],
            )

    # plt.xlabel('Phase') # seems redundant.
    plt.ylabel('Voltage [PU]')
    # for grid behind data plot
    ax.set_axisbelow(True)
    ax.grid(color='lightgrey')
    plt.tight_layout()

    if zoom_to_limits:
        ax.set_ylim(0.94, 1.06)

    if save_figure:
        plot_name = f'{feeder.name}_Voltage Box Whisker.png'.lower()
        plot_name = plot_name.replace(' ', '_').replace('\\', '_')
        save_pyplot(fig,
                    plot_name,
                    output_directory=output_directory)

    if show_plot:
        plt.show(block=False)
    else:
        plt.close(fig)

    return (fig, ax)


def plot_voltage_profile(
        feeder,
        secondary_kv_limit=0.5,
        show_limits=True,
        show_plot=True,
        save_figure=False,
        output_directory=None,
        zoom_to_limits=False,
        ):
    """
    Plot standard voltages over distance from substation by phase
    and primary secondary.

    TODO: add options to indicate other elements, such as pv, caps, ev... etc
    TODO: revist once secondary phases are known.
    """
    primary_mask = feeder.bus_voltages['kv_base'] > secondary_kv_limit

    plot_secondary = False
    if sum(~primary_mask) > 0:
        plot_secondary = True

    voltage_colors = [[0, 0, 0], [1, 0, 0], [0, 0, 1],
                      [0.5, 0.5, 0.5], [1, 0.5, 0.5], [0.5, 0.5, 1]]
    secondary_color = [1.0, 0.6784, 0]  # ['#FFAD00']
    marker_size = 2

    # create figure and subplots
    fig = plt.figure()
    ax = fig.add_subplot(111)

    ax.scatter(
        feeder.bus_voltages[primary_mask]['distance'],
        feeder.bus_voltages[primary_mask]['v1'],
        color=voltage_colors[0], marker='o', s=marker_size,
        label='A Primary', zorder=3
        )
    ax.scatter(
        feeder.bus_voltages[primary_mask]['distance'],
        feeder.bus_voltages[primary_mask]['v2'],
        color=voltage_colors[1], marker='o', s=marker_size,
        label='B Primary', zorder=2
        )
    ax.scatter(
        feeder.bus_voltages[primary_mask]['distance'],
        feeder.bus_voltages[primary_mask]['v3'],
        color=voltage_colors[2], marker='o', s=marker_size,
        label='C Primary', zorder=1
        )
    if plot_secondary:
        ax.scatter(
            feeder.bus_voltages[~primary_mask]['distance'],
            feeder.bus_voltages[~primary_mask]['v1'],
            color=secondary_color, marker='o', s=marker_size,
            label='Secondary', zorder=0
            )
        ax.scatter(
            feeder.bus_voltages[~primary_mask]['distance'],
            feeder.bus_voltages[~primary_mask]['v2'],
            color=secondary_color, marker='o', s=marker_size,
            zorder=0
            )
        ax.scatter(
            feeder.bus_voltages[~primary_mask]['distance'],
            feeder.bus_voltages[~primary_mask]['v3'],
            color=secondary_color, marker='o', s=marker_size,
            zorder=0
            )
    if show_limits:
        bus_dist = [-0.5, feeder.bus_voltages['distance'].max()+0.5]
        ax.plot(
            bus_dist,
            np.ones_like(bus_dist)*1.05,
            '--',
            c=[.4, .4, .4],
            )
        ax.plot(
            bus_dist,
            np.ones_like(bus_dist)*0.95,
            '--',
            c=[.4, .4, .4],
            )

    zoom_name = ''
    if zoom_to_limits:
        ax.set_ylim(0.94, 1.06)
        zoom_name = ' - Limit Zoom'

    ax.set_title(f'{feeder.name}\nVoltage Profile{zoom_name}')
    ax.legend(loc=0)

    # removed because the squished look makes me feel like data may be missing
    # ax1.set_xlim([feeder.bus_voltages['distance'].min(),
    #             feeder.bus_voltages['distance'].max()])

    ax.set_axisbelow(True)
    plt.xlabel('Distance from Substation [km]')
    plt.ylabel('Voltage [PU]')
    plt.grid(color='lightgrey')
    plt.tight_layout()

    if save_figure:
        plot_name = f'{feeder.name}_Voltage Profile{zoom_name}.png'.lower()
        plot_name = plot_name.replace(' ', '_').replace('\\', '_')
        save_pyplot(fig,
                    plot_name,
                    output_directory=output_directory)

    if show_plot:
        plt.show(block=False)
    else:
        plt.close(fig)

    return (fig, ax)


def plot_seed_voltage(
        seed_result,
        step_labels=None,
        step_title=None,
        show_plot=True,
        save_figure=False,
        output_directory=None,
        ):
    """
    Plot Max, Average, and Minimum voltages from Seed result
    """
    df = seed_result.extremes_df

    has_secondary = 'secondary_voltage_max' in df.columns

    fig = plt.figure()

    n_plots = 1 + has_secondary
    grid = plt.GridSpec(n_plots, 1)

    axes = []
    axes.append(fig.add_subplot(grid[0]))

    df['primary_voltage_max'].plot(
        ax=axes[0],
        color='red',
        label='Maximum')
    df['primary_voltage_ave'].plot(
        ax=axes[0],
        color='black',
        label='Average')
    df['primary_voltage_min'].plot(
        ax=axes[0],
        color='blue',
        label='Minimum')
    axes[0].set_title(f"Primary Voltages\nSeed {seed_result.seed}")

    if has_secondary:
        axes.append(fig.add_subplot(grid[1]))
        df['secondary_voltage_max'].plot(
            ax=axes[1],
            color='red',
            label='Maximum')
        df['secondary_voltage_ave'].plot(
            ax=axes[1],
            color='black',
            label='Average')
        df['secondary_voltage_min'].plot(
            ax=axes[1],
            color='blue',
            label='Minimum')
        axes[1].set_title(f"Secondary Voltages\nSeed {seed_result.seed}")

    x = range(0, len(df))
    if step_title is None:
        step_title = 'Step'

    for ax in axes:
        ax.yaxis.set_label_text("Bus Voltage [PU]")
        ax.xaxis.set_label_text(step_title)
        ax.set_axisbelow(True)
        ax.grid(color='lightgray')
        ax.plot(x, np.ones_like(x)*1.05, '--', c=[.4, .4, .4])
        ax.plot(x, np.ones_like(x)*0.95, '--', c=[.4, .4, .4])

        # handle step labels.
        if step_labels is not None:
            ax.set_xticks(range(0, len(step_labels)))
            ax.set_xticklabels(step_labels, rotation=-45, ha='left')

        ax.legend(
            loc=7,
            bbox_to_anchor=(1.15, 0.5),
        )

    plt.tight_layout()

    if save_figure:
        plot_name = f'seed_{seed_result.seed}_Voltages.png'.lower()
        plot_name = plot_name.replace(' ', '_').replace('\\', '_')
        save_pyplot(fig,
                    plot_name,
                    output_directory=output_directory)

    if show_plot:
        plt.show(block=False)
    else:
        plt.close(fig)

    return (fig, axes)


def plot_seed_line_capacity(
        seed_result,
        step_labels=None,
        step_title=None,
        show_plot=True,
        save_figure=False,
        output_directory=None,):
    """
    Plot Max and Average line capacities from Seed result
    """
    df = seed_result.extremes_df
    has_secondary = 'secondary_line_max_capacity' in df.columns

    fig = plt.figure()

    n_plots = 1 + has_secondary
    grid = plt.GridSpec(n_plots, 1)

    axes = []
    axes.append(fig.add_subplot(grid[0]))

    df['primary_line_max_capacity'].plot(ax=axes[0],
                                         color='red',
                                         label='Max')
    df['primary_line_ave_capacity'].plot(ax=axes[0],
                                         color='black',
                                         label='Average')
    axes[0].set_title(f"Primary Line Capacity\nSeed {seed_result.seed}")

    if has_secondary:
        axes.append(fig.add_subplot(grid[1]))
        df['secondary_line_max_capacity'].plot(ax=axes[1],
                                               color='red',
                                               label='Max')
        df['secondary_line_ave_capacity'].plot(ax=axes[1],
                                               color='black',
                                               label='Average')
        axes[1].set_title(f"Secondary Line Capacity\nSeed {seed_result.seed}")

    x = range(0, len(df))
    if step_title is None:
        step_title = 'Step'
    for ax in axes:
        ax.yaxis.set_label_text("Used Capacity [%]")
        ax.xaxis.set_label_text(step_title)
        ax.set_axisbelow(True)
        ax.grid(color='lightgray')
        ax.plot(x, np.ones_like(x)*100.0, '--', c=[.4, .4, .4])
        old_ylim = ax.get_ylim()
        new_ylim = (0.0, old_ylim[1])
        ax.set_ylim(new_ylim)
        # handle step labels.
        if step_labels is not None:
            ax.set_xticks(range(0, len(step_labels)))
            ax.set_xticklabels(step_labels, rotation=-45, ha='left')
        ax.legend()

    plt.tight_layout()

    if save_figure:
        plot_name = f'seed_{seed_result.seed}_line capacity.png'.lower()
        plot_name = plot_name.replace(' ', '_').replace('\\', '_')
        save_pyplot(fig,
                    plot_name,
                    output_directory=output_directory)

    if show_plot:
        plt.show(block=False)
    else:
        plt.close(fig)

    return (fig, axes)


def plot_seed_transformer_capacity(
        seed_result,
        step_labels=None,
        step_title=None,
        show_plot=True,
        save_figure=False,
        output_directory=None,
        ):
    """
    Plot Max, and Max transformer capacity from Seed result
    """
    df = seed_result.extremes_df
    has_transformers = 'transformer_max_capacity' in df.columns

    if not has_transformers:
        # no transformers to plot
        return

    fig = plt.figure()

    n_plots = 1
    grid = plt.GridSpec(n_plots, 1)

    axes = []
    axes.append(fig.add_subplot(grid[0]))

    df['transformer_max_capacity'].plot(ax=axes[0],
                                        color='red',
                                        label='Maximum')
    df['transformer_ave_capacity'].plot(ax=axes[0],
                                        color='black',
                                        label='Average')
    axes[0].set_title(f"Transformer Capacity\nSeed {seed_result.seed}")

    x = range(0, len(df))
    if step_title is None:
        step_title = 'Step'
    for ax in axes:
        ax.yaxis.set_label_text("Used Capacity [%]")
        ax.xaxis.set_label_text(step_title)
        ax.set_axisbelow(True)
        ax.grid(color='lightgray')
        ax.plot(x, np.ones_like(x)*100.0, '--', c=[.4, .4, .4])
        old_ylim = ax.get_ylim()
        new_ylim = (0.0, old_ylim[1])
        ax.set_ylim(new_ylim)
        ax.legend()
        # handle step labels.
        if step_labels is not None:
            ax.set_xticks(range(0, len(step_labels)))
            ax.set_xticklabels(step_labels, rotation=-45, ha='left')

    plt.tight_layout()

    if save_figure:
        plot_name = f'seed_{seed_result.seed}_line capacity.png'.lower()
        plot_name = plot_name.replace(' ', '_').replace('\\', '_')
        save_pyplot(fig,
                    plot_name,
                    output_directory=output_directory)

    if show_plot:
        plt.show(block=False)
    else:
        plt.close(fig)

    return (fig, axes)


def plot_seed_substation_powers(
        seed_result,
        step_title=None,
        step_labels=None,
        show_plot=True,
        save_figure=False,
        output_directory=None,
        ):
    """
    Plot Real and Reactive Substation powers from Seed result
    """
    df = seed_result.extremes_df

    fig = plt.figure()

    n_plots = 2
    grid = plt.GridSpec(n_plots, 1)

    axes = []
    axes.append(fig.add_subplot(grid[0]))
    axes.append(fig.add_subplot(grid[1]))

    df['substation_active_kw'].plot(
        ax=axes[0],
        color='black',
        label='Active Power'
        )
    df['substation_rective_kvar'].plot(
        ax=axes[1],
        color='black',
        label='Reactive Power'
        )

    axes[0].set_title(f"Substation Delivered Powers\nSeed {seed_result.seed}")

    axes[0].yaxis.set_label_text("Active Power [kW]")
    axes[1].yaxis.set_label_text("Reactive Power [kVAR]")

    x = range(0, len(df))
    if step_title is None:
        step_title = 'Step'

    for ax in axes:
        ax.xaxis.set_label_text(step_title)
        ax.set_axisbelow(True)
        ax.grid(color='lightgray')
        ax.plot(x, np.ones_like(x)*0.0, '--', c=[.4, .4, .4])

        # handle step labels.
        if step_labels is not None:
            ax.set_xticks(range(0, len(step_labels)))
            ax.set_xticklabels(step_labels, rotation=-45, ha='left')

        ax.legend()

    plt.tight_layout()

    if save_figure:
        plot_name = f'seed_{seed_result.seed}_substation powers.png'.lower()
        plot_name = plot_name.replace(' ', '_').replace('\\', '_')
        save_pyplot(fig,
                    plot_name,
                    output_directory=output_directory)

    if show_plot:
        plt.show(block=False)
    else:
        plt.close(fig)

    return (fig, axes)


def plot_seed_load_allocation(
        seed_result,
        show_plot=True,
        save_figure=False,
        output_directory=None,
        legend_outside=True,
        ax=None,
        **kwargs,
        ):
    """
    Plot Allocated powers and counts related to seed load elements.

    ax is expected to be a group of two ax objects.
    """
    if isinstance(seed_result, dict):
        # handle selection and collection of allocations from results
        if 'allocation_id' not in seed_result:
            print('Not standard result data')
            return
        allocations = {}
        for _, row in seed_result['allocation_id'].iterrows():
            name = row['allocation_name']
            data_name = row['allocation_data_name']
            allocations[name] = seed_result[data_name]
    else:
        allocations = seed_result.allocation_dfs
    has_loads = False

    loads = {}
    for name, df in allocations.items():
        if 'additional_loads' in df.columns:
            has_loads = True
            # is load type item.
            loads[name] = df

    if not has_loads:
        return

    axes = []

    if ax is None:
        fig = plt.figure()
        grid = plt.GridSpec(2, 1)
        axes.append(fig.add_subplot(grid[0]))  # for kw /kwar
        axes.append(fig.add_subplot(grid[1]))  # for item counts
    else:
        fig = plt.gcf()
        ax1, ax2 = ax
        axes.append(ax1)  # for kw /kwar
        axes.append(ax2)  # for item counts

    n_allocations = 0
    for name, df in loads.items():
        axes[0].step(df.index,
                     df['total_kw'],
                     label=f"{name} kW",
                     where='mid')
        axes[0].step(df.index,
                     df['total_kvar'],
                     label=f"{name} kVAR",
                     linestyle='--',
                     where='mid')

        axes[1].step(df.index,
                     df['additional_loads'],
                     label=f"{name}",
                     where='mid')

        # keep count
        if n_allocations == 0:
            total_kw = df['total_kw'].copy()
            total_kvar = df['total_kvar'].copy()
            total_allocations = df['additional_loads'].copy()
        else:
            # add
            total_kw += df['total_kw']
            total_kvar += df['total_kvar']
            total_allocations += df['additional_loads']
        n_allocations += 1

    axes[0].step(total_kw.index,
                 total_kw.values,
                 label="Total kW",
                 color='black',
                 where='mid')
    axes[0].step(total_kvar.index,
                 total_kvar.values,
                 label="Total kVAR",
                 linestyle='--',
                 color='grey',
                 where='mid')

    axes[1].step(total_allocations.index,
                 total_allocations.values,
                 label="Total",
                 color='black',
                 where='mid',
                 linestyle='--',
                 )

    axes[0].set_title(f"Load Element Allocations\nSeed {seed_result.seed}")
    axes[0].yaxis.set_label_text("Load kW and kVAR")
    axes[1].yaxis.set_label_text("Number of Allocations")

    # check for step title.
    if seed_result.scenario.step_title is None:
        step_title = "Step"
    else:
        step_title = seed_result.scenario.step_title

    for ax in axes:
        ax.xaxis.set_label_text(step_title)

        # handle step labels.
        if seed_result.scenario.step_labels is not None:
            step_labels = seed_result.scenario.step_labels
            ax.set_xticks(range(0, len(step_labels)))
            ax.set_xticklabels(step_labels, rotation=-45, ha='left')

        ax.set_axisbelow(True)
        ax.grid(color='lightgray')
        ax.legend()

    plt.tight_layout()

    # set legends outside of plot
    if legend_outside:
        for ax in axes:
            legend = ax.get_legend()
            # handle case of no legend
            if legend is None:
                continue
            # handle case of blank legend... (may not occur)
            if len(legend.texts) == 0:
                continue
            legend.set_bbox_to_anchor((1.05, 1.05))

    if save_figure:
        plot_name = f'seed_{seed_result.seed}_load allocation.png'.lower()
        plot_name = plot_name.replace(' ', '_').replace('\\', '_')
        save_pyplot(fig,
                    plot_name,
                    output_directory=output_directory)

    if show_plot:
        plt.show(block=False)

    return (fig, axes)


def plot_seed_pv_allocation(
        seed_result,
        show_plot=True,
        save_figure=False,
        output_directory=None,
        pv_scaling=1.0,
        legend_outside=True,
        ax=None,
        **kwargs,
        ):
    """
    Plot Allocated powers and counts related to seed pv elements.

    if passing in an ax, it should be a list of two ax.
    """
    if isinstance(seed_result, dict):
        # handle selection and collection of allocations from results
        if 'allocation_id' not in seed_result:
            print('Not standard result data')
            return
        allocations = {}
        for _, row in seed_result['allocation_id'].iterrows():
            name = row['allocation_name']
            data_name = row['allocation_data_name']
            allocations[name] = seed_result[data_name]

        loaded_data = True
        seed = ''
    else:
        allocations = seed_result.allocation_dfs
        loaded_data = False
        seed = seed_result.seed
    has_pv = False

    pv = {}
    for name, df in allocations.items():
        if 'additional_pv' in df.columns:
            if df['additional_pv'].sum() > 0:
                has_pv = True
                # is load type item.
                pv[name] = df

    if not has_pv:
        return

    axes = []

    if ax is None:
        fig = plt.figure()
        grid = plt.GridSpec(2, 1)
        axes.append(fig.add_subplot(grid[0]))  # for kva
        axes.append(fig.add_subplot(grid[1]))  # for item counts
    else:
        fig = plt.gcf()
        ax1, ax2 = ax
        axes.append(ax1)  # for kva
        axes.append(ax2)  # for item counts

    n_allocations = 0
    for name, df in pv.items():
        axes[0].step(df.index,
                     df['total_kva'] * pv_scaling,
                     label=f"{name}",
                     where='mid')

        axes[1].step(df.index,
                     df['additional_pv'],
                     label=f"{name}",
                     where='mid')

        # keep count
        if n_allocations == 0:
            total_kva = df['total_kva'].copy() * pv_scaling
            # total_kvar = df['total_kvar'].copy()
            total_allocations = df['additional_pv'].copy()
        else:
            # add
            total_kva += df['total_kva'] * pv_scaling
            # total_kvar += df['total_kvar'] * pv_scaling
            total_allocations += df['additional_pv']
        n_allocations += 1

    axes[0].step(total_kva.index,
                 total_kva.values,
                 label="Total kVA",
                 color='black',
                 linestyle='--',
                 where='mid'
                 )

    axes[1].step(total_allocations.index,
                 total_allocations.values,
                 label="Total",
                 color='black',
                 where='mid',
                 linestyle='--',
                 )

    axes[0].set_title("PV Allocations")
    axes[0].yaxis.set_label_text("kVA")
    axes[1].yaxis.set_label_text("Number of Allocations")

    # check for step title.
    if not loaded_data:
        if seed_result.scenario.step_title is None:
            step_title = "Step"
        else:
            step_title = seed_result.scenario.step_title
    else:
        step_title = 'Step'

    for ax in axes:
        ax.xaxis.set_label_text(step_title)

        if loaded_data:
            step_labels = list(seed_result['step_id']['step_label'].values)
        else:
            step_labels = seed_result.scenario.step_labels

        # handle step labels.
        if step_labels is not None:
            ax.set_xticks(range(0, len(step_labels)))
            ax.set_xticklabels(step_labels, rotation=-45, ha='left')

        ax.set_axisbelow(True)
        ax.grid(color='lightgrey')
        ax.legend()

    plt.tight_layout()

    # set legends outside of plot
    if legend_outside:
        for l_ax in axes:
            legend = l_ax.get_legend()
            # handle case of no legend
            if legend is None:
                continue
            # handle case of blank legend... (may not occur)
            if len(legend.texts) == 0:
                continue
            legend.set_bbox_to_anchor((1.05, 1.05))

    if save_figure:
        plot_name = f'seed_{seed}_pv allocation.png'.lower()
        plot_name = plot_name.replace(' ', '_').replace('\\', '_')
        save_pyplot(fig,
                    plot_name,
                    output_directory=output_directory)

    if show_plot:
        plt.show(block=False)

    return (fig, axes)


def plot_seed_storage_allocation(
        seed_result,
        show_plot=True,
        save_figure=False,
        output_directory=None,
        legend_outside=True,
        ax=None,
        **kwargs,
        ):
    """
    Plot Allocated powers and counts related to seed sttorage elements.

    if passing in an ax, it should be a list of two ax.
    """
    if isinstance(seed_result, dict):
        # handle selection and collection of allocations from results
        if 'allocation_id' not in seed_result:
            print('Not standard result data')
            return
        allocations = {}
        for _, row in seed_result['allocation_id'].iterrows():
            name = row['allocation_name']
            data_name = row['allocation_data_name']
            allocations[name] = seed_result[data_name]

        loaded_data = True
        seed = ''
    else:
        allocations = seed_result.allocation_dfs
        loaded_data = False
        seed = seed_result.seed
    has_storage = False

    storages = {}
    for name, df in allocations.items():
        if 'additional_storages' in df.columns:
            if df['additional_storages'].sum() > 0:
                has_storage = True
                # is load type item.
                storages[name] = df

    if not has_storage:
        return

    axes = []

    if ax is None:
        fig = plt.figure()
        grid = plt.GridSpec(2, 1)
        axes.append(fig.add_subplot(grid[0]))  # for kva
        axes.append(fig.add_subplot(grid[1]))  # for item counts
    else:
        fig = plt.gcf()
        ax1, ax2 = ax
        axes.append(ax1)  # for kva
        axes.append(ax2)  # for item counts

    n_allocations = 0
    for name, df in storages.items():
        axes[0].step(df.index,
                     df['total_kva'],
                     label=f"{name}",
                     where='mid')

        axes[1].step(df.index,
                     df['additional_storages'],
                     label=f"{name}",
                     where='mid')

        # keep count
        if n_allocations == 0:
            total_kva = df['total_kva'].copy()
            total_allocations = df['additional_storages'].copy()
        else:
            # add
            total_kva += df['total_kva']
            total_allocations += df['additional_storages']
        n_allocations += 1

    axes[0].step(total_kva.index,
                 total_kva.values,
                 label="Total kW",
                 color='black',
                 where='mid',
                 linestyle='--',
                 )

    axes[1].step(total_allocations.index,
                 total_allocations.values,
                 label="Total",
                 color='black',
                 where='mid',
                 linestyle='--',
                 )

    axes[0].set_title("Storage Allocations")
    axes[0].yaxis.set_label_text("kW")
    axes[1].yaxis.set_label_text("Number of Allocations")

    # check for step title.
    if not loaded_data:
        if seed_result.scenario.step_title is None:
            step_title = "Step"
        else:
            step_title = seed_result.scenario.step_title
    else:
        step_title = 'Step'

    for ax in axes:
        ax.xaxis.set_label_text(step_title)

        if loaded_data:
            step_labels = list(seed_result['step_id']['step_label'].values)
        else:
            step_labels = seed_result.scenario.step_labels

        # handle step labels.
        if step_labels is not None:
            ax.set_xticks(range(0, len(step_labels)))
            ax.set_xticklabels(step_labels, rotation=-45, ha='left')

        ax.set_axisbelow(True)
        ax.grid(color='lightgrey')
        ax.legend()

    plt.tight_layout()

    # set legends outside of plot
    if legend_outside:
        for l_ax in axes:
            legend = l_ax.get_legend()
            # handle case of no legend
            if legend is None:
                continue
            # handle case of blank legend... (may not occur)
            if len(legend.texts) == 0:
                continue
            legend.set_bbox_to_anchor((1.05, 1.05))

    if save_figure:
        plot_name = f'seed_{seed}_storage allocation.png'.lower()
        plot_name = plot_name.replace(' ', '_').replace('\\', '_')
        save_pyplot(fig,
                    plot_name,
                    output_directory=output_directory)

    if show_plot:
        plt.show(block=False)

    return (fig, axes)


# generator allocation
def plot_seed_generator_allocation(
        seed_result,
        show_plot=True,
        save_figure=False,
        output_directory=None,
        legend_outside=True,
        ax=None,
        **kwargs,
        ):
    """
    Plot Allocated powers and counts related to seed generator elements.

    if passing in an ax, it should be a list of two ax.
    """
    if isinstance(seed_result, dict):
        # handle selection and collection of allocations from results
        if 'allocation_id' not in seed_result:
            print('Not standard result data')
            return
        allocations = {}
        for _, row in seed_result['allocation_id'].iterrows():
            name = row['allocation_name']
            data_name = row['allocation_data_name']
            allocations[name] = seed_result[data_name]

        loaded_data = True
        seed = ''
    else:
        allocations = seed_result.allocation_dfs
        loaded_data = False
        seed = seed_result.seed
    has_generator = False

    generators = {}
    for name, df in allocations.items():
        if 'additional_wind_generators' in df.columns:
            if df['additional_wind_generators'].sum() > 0:
                has_generator = True
                # is load type item.
                generators[name] = df

    if not has_generator:
        return

    axes = []

    if ax is None:
        fig = plt.figure()
        grid = plt.GridSpec(2, 1)
        axes.append(fig.add_subplot(grid[0]))  # for kva
        axes.append(fig.add_subplot(grid[1]))  # for item counts
    else:
        fig = plt.gcf()
        ax1, ax2 = ax
        axes.append(ax1)  # for kva
        axes.append(ax2)  # for item counts

    n_allocations = 0
    for name, df in generators.items():
        axes[0].step(df.index,
                     df['total_kw'],
                     label=f"{name}",
                     where='mid')

        axes[1].step(df.index,
                     df['additional_wind_generators'],
                     label=f"{name}",
                     where='mid')

        # keep count
        if n_allocations == 0:
            total_kva = df['total_kw'].copy()
            total_allocations = df['additional_wind_generators'].copy()
        else:
            # add
            total_kva += df['total_kw']
            total_allocations += df['additional_wind_generators']
        n_allocations += 1

    axes[0].step(total_kva.index,
                 total_kva.values,
                 label="Total kW",
                 color='black',
                 where='mid',
                 linestyle='--',
                 )

    axes[1].step(total_allocations.index,
                 total_allocations.values,
                 label="Total",
                 color='black',
                 where='mid',
                 linestyle='--',
                 )

    axes[0].set_title("Generator Allocations")
    axes[0].yaxis.set_label_text("kW")
    axes[1].yaxis.set_label_text("Number of Allocations")

    # check for step title.
    if not loaded_data:
        if seed_result.scenario.step_title is None:
            step_title = "Step"
        else:
            step_title = seed_result.scenario.step_title
    else:
        step_title = 'Step'

    for ax in axes:
        ax.xaxis.set_label_text(step_title)

        if loaded_data:
            step_labels = list(seed_result['step_id']['step_label'].values)
        else:
            step_labels = seed_result.scenario.step_labels

        # handle step labels.
        if step_labels is not None:
            ax.set_xticks(range(0, len(step_labels)))
            ax.set_xticklabels(step_labels, rotation=-45, ha='left')

        ax.set_axisbelow(True)
        ax.grid(color='lightgrey')
        ax.legend()

    plt.tight_layout()

    # set legends outside of plot
    if legend_outside:
        for l_ax in axes:
            legend = l_ax.get_legend()
            # handle case of no legend
            if legend is None:
                continue
            # handle case of blank legend... (may not occur)
            if len(legend.texts) == 0:
                continue
            legend.set_bbox_to_anchor((1.05, 1.05))

    if save_figure:
        plot_name = f'seed_{seed}_generator allocation.png'.lower()
        plot_name = plot_name.replace(' ', '_').replace('\\', '_')
        save_pyplot(fig,
                    plot_name,
                    output_directory=output_directory)

    if show_plot:
        plt.show(block=False)

    return (fig, axes)
# end gen allocation


def plot_seed_pv_to_load(
        seed_result,
        show_plot=True,
        save_figure=False,
        output_directory=None,
        load_scaling=1.0,
        pv_scaling=1.0,
        legend_outside=True,
        ):
    """
    Plot Allocated pv ratings to max demand ratio
    and allocation counts total.

    Note: just sums load - doesn't account for scaling...
    """
    allocations = seed_result.allocation_dfs
    load_sum = seed_result.feeder.loads['kw'].sum()*load_scaling
    has_pv = False

    pv = {}
    for name, df in allocations.items():
        if 'additional_pv' in df.columns:
            if df['additional_pv'].sum() > 0:
                has_pv = True
                # is load type item.
                pv[name] = df

    if not has_pv:
        return

    fig = plt.figure()
    grid = plt.GridSpec(2, 1)
    axes = []
    axes.append(fig.add_subplot(grid[0]))  # for der to load ratio
    axes.append(fig.add_subplot(grid[1]))  # for item counts
    n_allocations = 0
    for name, df in pv.items():

        # plot allocation n
        axes[1].step(df.index,
                     df['additional_pv'],
                     label=f"{name}",
                     where='mid')

        # initialize counts
        if n_allocations == 0:
            total_kva = df['total_kva'].copy() * pv_scaling
            total_allocations = df['additional_pv'].copy()
        else:
            # add to count
            total_kva += df['total_kva'] * pv_scaling
            total_allocations += df['additional_pv']
        n_allocations += 1

    # plot der 2 load ratio
    axes[0].step(total_kva.index,
                 total_kva.values / load_sum,
                 # label="Total KVA",
                 color='black',
                 where='mid')

    axes[1].step(total_allocations.index,
                 total_allocations.values,
                 label="Total",
                 color='black',
                 where='mid')

    axes[0].set_title("PV Capacity to Demand Ratio and PV Allocations\n"
                      f"Seed {seed_result.seed}")
    axes[0].yaxis.set_label_text("Ratio")
    axes[1].yaxis.set_label_text("Number of Allocations")

    axes[1].legend()

    # check for step title.
    if seed_result.scenario.step_title is None:
        step_title = "Step"
    else:
        step_title = seed_result.scenario.step_title

    for ax in axes:
        ax.xaxis.set_label_text(step_title)

        # handle step labels.
        if seed_result.scenario.step_labels is not None:
            step_labels = seed_result.scenario.step_labels
            ax.set_xticks(range(0, len(step_labels)))
            ax.set_xticklabels(step_labels, rotation=-45, ha='left')

        ax.set_axisbelow(True)
        ax.grid(color='lightgrey')

    plt.tight_layout()

    # set legends outside of plot
    if legend_outside:
        for ax in axes:
            legend = ax.get_legend()
            # handle case of no legend
            if legend is None:
                continue
            # handle case of blank legend... (may not occur)
            if len(legend.texts) == 0:
                continue
            legend.set_bbox_to_anchor((1.05, 1.05))

    if save_figure:
        plot_name = f'seed_{seed_result.seed}_pv to load.png'.lower()
        plot_name = plot_name.replace(' ', '_').replace('\\', '_')
        save_pyplot(fig,
                    plot_name,
                    output_directory=output_directory)

    if show_plot:
        plt.show(block=False)

    return (fig, axes)


def plot_scenario_voltage(
        results,
        step_labels=None,
        step_title=None,
        show_plot=True,
        save_figure=False,
        output_directory=None,
        ):
    """
    Plot Max, Average, and Minimum voltages from scenarios
    """
    df = results.dfs  # this is really a dictionary of dataframes

    has_secondary = 'secondary_voltage_max' in df.keys()

    fig = plt.figure()

    n_plots = 1 + has_secondary
    grid = plt.GridSpec(n_plots, 1)

    axes = []
    axes.append(fig.add_subplot(grid[0]))
    primary_voltages = [
        'primary_voltage_max',
        'primary_voltage_ave',
        'primary_voltage_min',
        ]

    for voltage in primary_voltages:
        df[voltage].plot(ax=axes[0], color='lightgrey', legend=False)

    df[voltage]['ave'].plot(
        ax=axes[0],
        color='lightgrey',
        label='Seed',
        legend=True)

    df['primary_voltage_max']['ave'].plot(
        ax=axes[0],
        color='red',
        label='Maximum',
        legend=True)
    df['primary_voltage_ave']['ave'].plot(
        ax=axes[0],
        color='black',
        label='Average',
        legend=True)
    df['primary_voltage_min']['ave'].plot(
        ax=axes[0],
        color='blue',
        label='Minimum',
        legend=True)

    axes[0].set_title(f"{results.scenario.name}\nPrimary Voltages")
    x = range(0, len(df['primary_voltage_max']['ave']))

    if has_secondary:
        axes.append(fig.add_subplot(grid[1]))
        secondary_voltages = [
            'secondary_voltage_max',
            'secondary_voltage_ave',
            'secondary_voltage_min']
        for voltage in secondary_voltages:
            df[voltage].plot(ax=axes[1], color='lightgrey', legend=False)

        df[voltage]['ave'].plot(
            ax=axes[1],
            color='lightgrey',
            label='Seed',
            legend=True)

        df['secondary_voltage_max']['ave'].plot(
            ax=axes[1],
            color='red',
            label='Maximum',
            legend=True)
        df['secondary_voltage_ave']['ave'].plot(
            ax=axes[1],
            color='black',
            label='Average',
            legend=True)
        df['secondary_voltage_min']['ave'].plot(
            ax=axes[1],
            color='blue',
            label='Minimum',
            legend=True)
        axes[1].set_title("Secondary Voltages")

    for ax in axes:
        ax.yaxis.set_label_text("Bus Voltage [PU]")
        ax.set_axisbelow(True)
        ax.grid(color='lightgrey')
        ax.plot(x, np.ones_like(x)*1.05, '--', c=[.4, .4, .4])
        ax.plot(x, np.ones_like(x)*0.95, '--', c=[.4, .4, .4])

        # handle wierd legend issue
        valid_handles = []
        valid_lables = []
        handles_and_labels = ax.get_legend_handles_labels()

        valid_entries = [
            'Seed', 'Average', 'Maximum', 'Minimum'
        ]

        for handle, label in zip(handles_and_labels[0], handles_and_labels[1]):
            if label in valid_entries:
                valid_handles.append(handle)
                valid_lables.append(label)
        ax.legend(
            handles=valid_handles,
            labels=valid_lables,
            loc='upper right',
            bbox_to_anchor=(1.4, 1.0)
            )

        # handle step labels.
        if step_labels is not None:
            ax.set_xticks(range(0, len(step_labels)))
            ax.set_xticklabels(step_labels, rotation=-45, ha='left')

        if step_title is None:
            ax.xaxis.set_label_text("Step")
        else:
            ax.xaxis.set_label_text(step_title)

    plt.tight_layout()

    if save_figure:
        plot_name = f'scenario_{results.scenario.name}_voltages.png'.lower()
        plot_name = plot_name.replace(' ', '_').replace('\\', '_')
        save_pyplot(fig,
                    plot_name,
                    output_directory=output_directory)

    if show_plot:
        plt.show(block=False)
    else:
        plt.close(fig)

    return (fig, axes)


def plot_scenario_line_capacity(
        results,
        step_labels=None,
        step_title=None,
        show_plot=True,
        save_figure=False,
        output_directory=None,
        ):
    """
    Plot Max and average line capacites from scenarios
    """
    df = results.dfs  # this is really a dictionary of dataframes

    has_secondary = 'secondary_line_max_capacity' in df.keys()

    fig = plt.figure()

    n_plots = 1 + has_secondary
    grid = plt.GridSpec(n_plots, 1)
    axes = []
    axes.append(fig.add_subplot(grid[0]))

    primary_lines = [
        'primary_line_max_capacity',
        'primary_line_ave_capacity'
        ]

    for line in primary_lines:
        df[line].plot(ax=axes[0], color='lightgrey', legend=False)

    df['primary_line_max_capacity']['ave'].plot(
        ax=axes[0],
        color='lightgrey',
        label='Seed',
        legend=True)

    df['primary_line_max_capacity']['ave'].plot(
        ax=axes[0],
        color='red',
        label='Maximum',
        legend=True)
    df['primary_line_ave_capacity']['ave'].plot(
        ax=axes[0],
        color='black',
        label='Average',
        legend=True)

    axes[0].set_title(f"{results.scenario.name}\nPrimary Line Capacity")
    x = range(0, len(df['primary_line_max_capacity']['ave']))

    if has_secondary:
        axes.append(fig.add_subplot(grid[1]))
        secondary_lines = [
            'secondary_line_max_capacity',
            'secondary_line_ave_capacity',
            ]

        for line in secondary_lines:
            df[line].plot(ax=axes[1], color='lightgrey', legend=False)

        df['secondary_line_max_capacity']['ave'].plot(
            ax=axes[1],
            color='lightgrey',
            label='Seed',
            legend=True)

        df['secondary_line_max_capacity']['ave'].plot(
            ax=axes[1],
            color='red',
            label='Maximum',
            legend=True)
        df['secondary_line_ave_capacity']['ave'].plot(
            ax=axes[1],
            color='black',
            label='Average',
            legend=True)
        axes[1].set_title("Secondary Line Capacity")
    if step_title is None:
        step_title = 'Step'

    for ax in axes:
        ax.yaxis.set_label_text("Used Capacity [%]")
        ax.xaxis.set_label_text(step_title)
        ax.set_axisbelow(True)
        ax.grid(color='lightgrey')
        ax.plot(x, np.ones_like(x)*100.0, '--', c=[.4, .4, .4])
        old_ylim = ax.get_ylim()
        new_ylim = (0.0, old_ylim[1])
        ax.set_ylim(new_ylim)

        # handle wierd legend issue
        valid_handles = []
        valid_lables = []
        handles_and_labels = ax.get_legend_handles_labels()
        valid_entries = [
                    'Seed', 'Average', 'Maximum', 'Minimum'
                ]

        for handle, label in zip(handles_and_labels[0], handles_and_labels[1]):
            if label in valid_entries:
                valid_handles.append(handle)
                valid_lables.append(label)

        ax.legend(
            handles=valid_handles,
            labels=valid_lables,
            loc='upper right',
            bbox_to_anchor=(1.4, 1.0)
            )

        # handle step labels.
        if step_labels is not None:
            ax.set_xticks(range(0, len(step_labels)))
            ax.set_xticklabels(step_labels, rotation=-45, ha='left')

        if step_title is None:
            ax.xaxis.set_label_text("Step")
        else:
            ax.xaxis.set_label_text(step_title)

    plt.tight_layout()

    if save_figure:
        name = results.scenario.name
        plot_name = f'scenario_{name}_line_capacity.png'.lower()
        plot_name = plot_name.replace(' ', '_').replace('\\', '_')
        save_pyplot(fig,
                    plot_name,
                    output_directory=output_directory)

    if show_plot:
        plt.show(block=False)
    else:
        plt.close(fig)
    return (fig, axes)


def plot_scenario_transformer_capacity(
        results,
        step_labels=None,
        step_title=None,
        show_plot=True,
        save_figure=False,
        output_directory=None,
        ):
    """
    Plot Max and average transformer capacity from scenarios
    """
    df = results.dfs  # this is really a dictionary of dataframes
    has_transformers = 'transformer_max_capacity' in df.keys()

    if not has_transformers:
        # no transformers to plot
        return

    fig = plt.figure()

    n_plots = 1
    grid = plt.GridSpec(n_plots, 1)
    axes = []
    axes.append(fig.add_subplot(grid[0]))

    transformer_datas = ['transformer_max_capacity',
                         'transformer_ave_capacity']

    for data in transformer_datas:
        df[data].plot(ax=axes[0], color='lightgrey', legend=False)

    df['transformer_max_capacity']['ave'].plot(
        ax=axes[0],
        color='lightgrey',
        label='Seed',
        legend=True)
    df['transformer_max_capacity']['ave'].plot(
        ax=axes[0],
        color='red',
        label='Maximum',
        legend=True)
    df['transformer_ave_capacity']['ave'].plot(
        ax=axes[0],
        color='black',
        label='Average',
        legend=True)

    axes[0].set_title(f"{results.scenario.name}\nTransformer Capacity")
    x = range(0, len(df['transformer_ave_capacity']['ave']))
    if step_title is None:
        step_title = 'Step'

    for ax in axes:
        ax.yaxis.set_label_text("Used Capacity [%]")
        ax.xaxis.set_label_text(step_title)
        ax.set_axisbelow(True)
        ax.grid(color='lightgrey')
        ax.plot(x, np.ones_like(x)*100.0, '--', c=[.4, .4, .4])
        old_ylim = ax.get_ylim()
        new_ylim = (0.0, old_ylim[1])
        ax.set_ylim(new_ylim)
        # handle step labels.
        if step_labels is not None:
            ax.set_xticks(range(0, len(step_labels)))
            ax.set_xticklabels(step_labels, rotation=-45, ha='left')

    # handle wierd legend issue
    valid_handles = []
    valid_lables = []
    handles_and_labels = ax.get_legend_handles_labels()
    valid_entries = [
        'Seed', 'Average', 'Maximum', 'Minimum'
    ]

    for handle, label in zip(handles_and_labels[0], handles_and_labels[1]):
        if label in valid_entries:
            valid_handles.append(handle)
            valid_lables.append(label)
    ax.legend(
        handles=valid_handles,
        labels=valid_lables,
        loc='upper right',
        bbox_to_anchor=(1.4, 1.0)
        )

    plt.tight_layout()

    if save_figure:
        name = results.scenario.name
        plot_name = f'scenario_{name}_transformer_capacity.png'.lower()
        plot_name = plot_name.replace(' ', '_').replace('\\', '_')
        save_pyplot(fig,
                    plot_name,
                    output_directory=output_directory)

    if show_plot:
        plt.show(block=False)
    else:
        plt.close(fig)

    return (fig, axes)
