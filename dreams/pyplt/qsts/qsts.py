"""
Plotting functions specifically for QSTS results.

Taking a more modular approach than the snapshot plots becase learning.

Step data to plot:
* extremes (min max ave for voltage, capacity, and pv)
* violation_dfs - more of individual info
* violation_counts - might be interesting - could do a percent in violation
* pv stuff (if existing is included in extremes)
* source power - P and Q and S - ensure negative/postive standard is variable

Thinking that maybe if ax and fig are returned, composite figures could be
made from that...

"""
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import cmasher as cmr
import numpy as np
import dreams


def plot_step_source_power_element(
        step_result,
        sign_convention=1,
        kind=1,
        use_dt=False,
        total_sum=True,
        ax=None,
        colors=None,
        legend=True,
        **kwargs
        ):
    """
    plot the power from a monitor.
    depending on kind will return Real (1), Reactive (2), or apparent Power (3)
    Sign convetntion can be 1 for reak power delivered to be positve
    and capacitive power to also be positive.

    optional use of date time index, setting of plot color and display of 
    legend are also possible.

    """
    monitor = step_result.monitors['vsource']
    df = monitor.df.copy()
    sign = 1.0
    x_label = 'QSTS Step'

    if ax is None:
        ax = plt.gca()

    if kind == 1:
        columns = ['P1_kW', 'P2_kW', 'P3_kW']
        y_label = 'Real Power [kW]'
        if sign_convention == 1:
            sign = -1.0

    elif kind == 2:
        columns = ['Q1_kVAR', 'Q2_kVAR', 'Q3_kVAR']
        y_label = 'Reactive Power [kVAR]'
        if sign_convention == 1:
            sign = -1.0

    else:
        # return apparent power
        columns = ['S1_kVA', 'S2_kVA', 'S3_kVA']
        y_label = 'Apparent Power [kVA]'

    if use_dt:
        df = df.set_index('dt')
        x_label = ''

    if colors is None:
        colors = ['black', 'red', 'blue']

    if total_sum:
        df['Total'] = df[columns].sum(axis=1)
        columns = ['Total']

    return_ax = (sign*df[columns]).plot(ax=ax, color=colors, **kwargs)

    if legend:
        clean_legend = [x.split('_')[0] for x in columns]
        return_ax.legend(clean_legend)
    else:
        return_ax.get_legend().remove()

    return_ax.set_axisbelow(True)
    return_ax.xaxis.grid(True, which="minor")
    return_ax.grid(color='lightgray')
    return_ax.set(xlabel=x_label, ylabel=y_label)

    return return_ax


def plot_step_system_extreme_element(
        step_result,
        kind=1,
        use_dt=False,
        ax=None,
        colors=None,
        legend=True,
        **kwargs
        ):
    """
    Plot specific set of columns collected from qsts step result
    should handle:
    1 primary voltage
    2 secondary voltage
    3 primary line capacity
    4 secondary line capacity
    5 transformer capacity
    6 soloar irradiance
    7 total system kw from pv

    Add 10 for maximum only
    Add 10, multiply by -1 for minimum only

    """
    df = step_result.extremes.copy()
    x_label = 'QSTS Step'

    if ax is None:
        ax = plt.gca()

    if kind == 1:
        # primary Voltage
        columns = [
            'primary_voltage_max',
            'primary_voltage_ave',
            'primary_voltage_min',
            ]
        y_label = 'Primary Voltage [PU]'
        default_color = ['red', 'black', 'blue']
        split_index = -1

    elif kind == 11:
        # primary Voltage max
        columns = [
            'primary_voltage_max',
            ]
        y_label = 'Primary Voltage [PU]'
        default_color = ['red']
        split_index = -1

    elif kind == -11:
        # primary Voltage Minimum
        columns = [
            'primary_voltage_min',
            ]
        y_label = 'Primary Voltage [PU]'
        default_color = ['blue']
        split_index = -1

    elif kind == 2:
        # secondary voltage
        columns = [
            'secondary_voltage_max',
            'secondary_voltage_ave',
            'secondary_voltage_min',
            ]
        y_label = 'Secondary Voltage [PU]'
        default_color = ['red', 'black', 'blue']
        split_index = -1

    elif kind == 12:
        # secondary voltage max
        columns = [
            'secondary_voltage_max',
            ]
        y_label = 'Secondary Voltage [PU]'
        default_color = ['red']
        split_index = -1

    elif kind == -12:
        # secondary voltage min
        columns = [
            'secondary_voltage_min',
            ]
        y_label = 'Secondary Voltage [PU]'
        default_color = ['blue']
        split_index = -1

    elif kind == 3:
        # primary line capacity
        columns = [
            'primary_line_max_capacity',
            'primary_line_ave_capacity',
            ]
        y_label = 'Used Primary Line Capacity [%]'
        default_color = ['red', 'black']
        split_index = -2

    elif kind == 13:
        # primary line max
        columns = [
            'primary_line_max_capacity',
            ]
        y_label = 'Used Primary Line Capacity [%]'
        default_color = ['red']
        split_index = -2

    elif kind == 4:
        # secondary line capacity
        columns = [
            'secondary_line_max_capacity',
            'secondary_line_ave_capacity',
            ]
        y_label = 'Used Secondary Line Capacity [%]'
        default_color = ['red', 'black']
        split_index = -2

    elif kind == 14:
        # secondary line max
        columns = [
            'secondary_line_max_capacity',
            ]
        y_label = 'Used Secondary Line Capacity [%]'
        default_color = ['red']
        split_index = -2

    elif kind == 5:
        # transformer capacity
        columns = [
            'transformer_max_capacity',
            'transformer_ave_capacity',
            ]
        y_label = 'Used Transformer Capacity [%]'
        default_color = ['red', 'black']
        split_index = -2

    elif kind == 15:
        # transformer capacity
        columns = [
            'transformer_max_capacity',
            ]
        y_label = 'Used Transformer Capacity [%]'
        default_color = ['red']
        split_index = -2

    elif kind == 6:
        # solar irradiance PU
        columns = ['irradiance']
        y_label = 'Solar Irradiance [PU]'
        default_color = 'black'
        split_index = 0

    elif kind == 7:
        # system solar generation
        columns = ['system_pv_p_kw']
        y_label = 'Solar Generation [kW]'
        default_color = 'black'
        split_index = 0

    elif kind == 8:
        # system solar generation
        columns = ['system_pv_q_kvar']
        y_label = 'Solar Generation [kVAR]'
        default_color = 'black'
        split_index = 0

    elif kind == 9:
        # system solar generation power factor
        columns = ['system_pv_pf']
        y_label = 'Power Factor'
        default_color = 'black'
        split_index = 0

    elif kind == 10:
        # system solar generation apparent power
        columns = ['system_pv_s']
        y_label = 'Solar Generation [kVA]'
        default_color = 'black'
        split_index = 0

    elif kind == 'storage_p':
        # system solar generation apparent power
        columns = ['system_storage_p_kw']
        y_label = 'Storage Generation [kW]'
        default_color = 'black'
        split_index = 0

    elif kind == 'storage_q':
        # system solar generation apparent power
        columns = ['system_storage_q_kvar']
        y_label = 'Storage Generation [kVAR]'
        default_color = 'black'
        split_index = 0

    elif kind == 'storage_soc':
        # system solar generation apparent power
        columns = ['system_storage_ave_soc']
        y_label = 'Storage Average SOC [%]'
        default_color = 'black'
        split_index = 0

    elif kind == 'storage_kwh':
        # system solar generation apparent power
        columns = ['system_storage_available_kwh']
        y_label = 'Storage Available Energy [kWh]'
        default_color = 'black'
        split_index = 0

    elif kind == 'generator_p':
        # system generator generation apparent power
        columns = ['system_generator_p_kw']
        y_label = 'Generator Generation [kW]'
        default_color = 'black'
        split_index = 0

    elif kind == 'generator_q':
        # system generator generation apparent power
        columns = ['system_generator_q_kvar']
        y_label = 'Generator Generation [kVAR]'
        default_color = 'black'
        split_index = 0

    elif kind == 'generator_s':
        # system generator generation apparent power
        columns = ['system_generator_s_kva']
        y_label = 'Generator Generation [kVA]'
        default_color = 'black'
        split_index = 0

    elif kind == 'generator_pf':
        # system generator generation apparent power
        columns = ['system_generator_pf']
        y_label = 'Generator Average PF'
        default_color = 'black'
        split_index = 0

    else:
        print(f"Invalid kind of {kind}")
        return None

    if use_dt:
        # this is sketchy...
        dt = step_result.monitors['vsource'].df.dt.copy()
        df.index = dt
        x_label = ''

    if colors is None:
        colors = default_color

    return_ax = df[columns].plot(ax=ax, color=colors, **kwargs)

    if legend and split_index != 0:
        clean_legend = [x.split('_')[split_index].capitalize() for x
                        in columns]
        return_ax.legend(clean_legend)
    else:
        return_ax.get_legend().remove()

    return_ax.set_axisbelow(True)
    return_ax.xaxis.grid(True, which="minor")
    return_ax.grid(color='lightgray')
    return_ax.set(xlabel=x_label, ylabel=y_label)

    return return_ax


def plot_step_violation_element(
        step_result,
        kind=1,
        as_percent=False,
        use_dt=False,
        title_labels=True,
        legend=False,
        ax=None,
        colors=None,
        **kwargs
        ):
    """
    Plot specific set of columns collected from qsts step result
    should handle:
    1 Over Voltage Count
    2 Under Voltage
    3 Line over capacity
    4 Transformer Over Capacity

    kwargs passted to pandas dataframe plot function
    """
    count_df = step_result.violation_counts.copy()
    feeder = step_result.scenario.feeder

    x_label = 'QSTS Step'
    default_color = 'black'

    if ax is None:
        ax = plt.gca()

    if kind == 1:
        # Over Voltage
        df = count_df['n_over_voltage'].copy()
        y_label = 'Over Voltage Buses'
        if as_percent:
            total_bus = len(feeder.buses)
            df = df/total_bus * 100.00

    elif kind == 2:
        # Under Voltage
        df = count_df['n_under_voltage'].copy()
        y_label = 'Under Voltage Buses'
        if as_percent:
            total_bus = len(feeder.buses)
            df = df/total_bus * 100.00

    elif kind == 3:
        # Line over capacity
        df = count_df['n_over_capacity_lines'].copy()
        y_label = 'Over Capacity Lines'
        if as_percent:
            total_lines = len(feeder.lines)
            df = df/total_lines * 100.00

    elif kind == 4:
        # transformer over capacity
        df = count_df['n_over_capacity_transformers'].copy()
        y_label = 'Over Capacity Transformers'
        if as_percent:
            total_transformers = len(feeder.transformers)
            df = df/total_transformers * 100.00

    if use_dt:
        dt = step_result.monitors['vsource'].df.dt.copy()
        df.index = dt
        x_label = ''

    if colors is None:
        colors = default_color

    return_ax = df.plot(ax=ax, color=colors, **kwargs)

    return_ax.set_axisbelow(True)
    return_ax.xaxis.grid(True, which="minor")
    return_ax.grid(color='lightgray')
    if title_labels:
        return_ax.set(xlabel=x_label, title=y_label)
        if as_percent:
            return_ax.set(ylabel='[%]')
        else:
            return_ax.set(ylabel='Count')

    else:
        return_ax.set(xlabel=x_label, ylabel=y_label)

    if legend is False:
        legened = return_ax.get_legend()
        if legened is not None:
            legened.remove()

    return return_ax


def plot_step_source_power(
        step_result,
        sign_convention=1,
        use_dt=False,
        total_sum=True,
        **kwargs
        ):
    """
    Use element function to create full power plot for step
    """
    fig = plt.figure()
    grid = plt.GridSpec(2, 1)
    axes = []
    axes.append(fig.add_subplot(grid[0]))  # for P
    axes.append(fig.add_subplot(grid[1]))  # for Q

    plot_step_source_power_element(
        step_result,
        kind=1,
        use_dt=use_dt,
        ax=axes[0],
        total_sum=total_sum,
        sign_convention=sign_convention,
        **kwargs)
    plot_step_source_power_element(
        step_result,
        kind=2,
        use_dt=use_dt,
        ax=axes[1],
        total_sum=total_sum,
        sign_convention=sign_convention,
        **kwargs)

    axes[0].set_title(f"Real and Reactive Source Power \n"
                      f"Seed {step_result.seed}, Step {step_result.step}")
    plt.tight_layout()

    return (fig, axes)


def plot_step_voltages(
        step_result,
        use_dt=False,
        include_limits=True,
        **kwargs):
    """
    Use element function to create full voltage plot for step
    """
    values = sum(~step_result.extremes['secondary_voltage_ave'].isna())
    has_secondary = values > 0

    fig = plt.figure()

    if has_secondary:
        grid = plt.GridSpec(2, 1)
    else:
        grid = plt.GridSpec(1, 1)
    axes = []

    axes.append(fig.add_subplot(grid[0]))  # for Primary Voltages
    plot_step_system_extreme_element(
        step_result,
        kind=1,
        use_dt=use_dt,
        ax=axes[0],
        **kwargs)

    if has_secondary:
        axes.append(fig.add_subplot(grid[1]))  # for Secondary (if available)
        plot_step_system_extreme_element(
            step_result,
            kind=2,
            use_dt=use_dt,
            ax=axes[1],
            **kwargs)

    for ax in axes:
        ax.set_axisbelow(True)
        ax.grid(color='lightgray')
        if include_limits:
            x = ax.lines[0].get_xdata()
            ax.plot(x, np.ones_like(x)*1.05, ':', c=[.4, .4, .4], zorder=0)
            ax.plot(x, np.ones_like(x)*0.95, ':', c=[.4, .4, .4], zorder=0)

    axes[0].set_title(f"System Voltages\n"
                      f"Seed {step_result.seed}, Step {step_result.step}")
    plt.tight_layout()

    return (fig, axes)


def plot_step_line_capacity(
        step_result,
        use_dt=False,
        include_limits=True,
        **kwargs):
    """
    Use element function to create line capacity plot for step
    """
    values = sum(~step_result.extremes['secondary_line_max_capacity'].isna())
    has_secondary = values > 0

    fig = plt.figure()

    if has_secondary:
        grid = plt.GridSpec(2, 1)
    else:
        grid = plt.GridSpec(1, 1)
    axes = []

    axes.append(fig.add_subplot(grid[0]))  # for Primary Voltages
    plot_step_system_extreme_element(
        step_result,
        kind=3,
        use_dt=use_dt,
        ax=axes[0],
        **kwargs)

    if has_secondary:
        axes.append(fig.add_subplot(grid[1]))  # for Secondary (if available)
        plot_step_system_extreme_element(
            step_result,
            kind=4,
            use_dt=use_dt,
            ax=axes[1],
            **kwargs)

    for ax in axes:
        ax.set_axisbelow(True)
        ax.grid(color='lightgray')
        if include_limits:
            x = ax.lines[0].get_xdata()
            ax.plot(x, np.ones_like(x)*100, ':', c=[.4, .4, .4], zorder=0)

    axes[0].set_title(f"Line Capacity\n"
                      f"Seed {step_result.seed}, Step {step_result.step}")
    plt.tight_layout()

    return (fig, axes)


def plot_step_transformer_capacity(
        step_result,
        use_dt=False,
        include_limits=True,
        **kwargs):
    """
    Use element function to create transformer capacity plot for step
    """

    fig = plt.figure()

    grid = plt.GridSpec(1, 1)
    axes = []

    axes.append(fig.add_subplot(grid[0]))  # for transformer capacity
    plot_step_system_extreme_element(
        step_result,
        kind=5,
        use_dt=use_dt,
        ax=axes[0],
        **kwargs)

    for ax in axes:
        ax.set_axisbelow(True)
        ax.grid(color='lightgray')
        if include_limits:
            x = ax.lines[0].get_xdata()
            ax.plot(x, np.ones_like(x)*100, ':', c=[.4, .4, .4], zorder=0)

    axes[0].set_title(f"Transformer Capacity\n"
                      f"Seed {step_result.seed}, Step {step_result.step}")
    plt.tight_layout()

    return (fig, axes)


def plot_step_pv_contribution(
        step_result,
        use_dt=False,
        **kwargs):
    """
    Use element function to create pv contribution plot for step
    """

    fig = plt.figure()

    grid = plt.GridSpec(1, 1)
    axes = []

    axes.append(fig.add_subplot(grid[0]))
    plot_step_system_extreme_element(
        step_result,
        kind=7,
        use_dt=use_dt,
        ax=axes[0],
        **kwargs)

    for ax in axes:
        ax.set_axisbelow(True)
        ax.grid(color='lightgray')

    axes[0].set_title(f"PV Generation\n"
                      f"Seed {step_result.seed}, Step {step_result.step}")
    plt.tight_layout()

    return (fig, axes)


def plot_step_violation(
        step_result,
        as_percent=True,
        use_dt=False,
        colors='black',
        **kwargs
        ):
    """
    Create violation plot for step
    kwargs passted to pandas dataframe plot function
    """
    fig = plt.figure()
    grid = plt.GridSpec(2, 2)

    axes = []
    if as_percent:
        append = 'Percents'
    else:
        append = 'Counts'

    for counter in list(range(0, 4)):
        axes.append(fig.add_subplot(grid[counter]))
        plot_step_violation_element(
            step_result,
            kind=counter+1,
            use_dt=use_dt,
            ax=axes[counter],
            as_percent=as_percent,
            colors=colors,
            **kwargs)

    fig.suptitle(f"System Violation {append}\n"
                 f"Seed {step_result.seed}, Step {step_result.step}")
    plt.tight_layout()

    return (fig, axes)


def plot_seed_voltages(
        seed_result,
        primary=True,
        use_dt=False,
        ax=None,
        line_style=None,
        cmap=None,
        show_limits=True,
        legend=True,
        legend_outside=True,
        title=None,
        **kwargs
        ):
    """
    plot seed voltages
    """
    fig = plt.figure()

    if primary:
        min_max_kind = [11, -11]
        if line_style is None:
            line_style = 'solid'
    else:
        min_max_kind = [12, -12]
        if line_style is None:
            line_style = 'dashed'

    if ax is None:
        ax = plt.gca()

    if cmap is None:
        cmap = cmr.torch_r

    n_steps = len(seed_result.step_results)
    cmap = cmr.get_sub_cmap(cmap, 0.2, .9, N=n_steps)

    for step, step_result in seed_result.step_results.items():
        ax = dreams.pyplt.qsts.plot_step_system_extreme_element(
            step_result,
            kind=min_max_kind[0],
            use_dt=use_dt,
            ax=ax,
            legend=False,
            linestyle=line_style,
            colors=cmap.colors[step],
        )
        ax = dreams.pyplt.qsts.plot_step_system_extreme_element(
            step_result,
            kind=min_max_kind[1],
            use_dt=use_dt,
            ax=ax,
            legend=False,
            linestyle=line_style,
            colors=cmap.colors[step]
        )

    if show_limits:
        x = ax.lines[0].get_xdata()
        ax.plot(
            x,
            np.ones_like(x)*1.05,
            ':',
            c=[.4, .4, .4],
            zorder=0,
            )
        ax.plot(
            x,
            np.ones_like(x)*0.95,
            ':',
            c=[.4, .4, .4],
            zorder=0,
            )

    if title is None:
        ax.set_title("Maximum and Minimum Voltages")
    else:
        ax.set_title(title)

    if legend:
        # check for step title.
        if seed_result.scenario.step_title is None:
            step_title = "Step"
        else:
            step_title = seed_result.scenario.step_title

        # handle step labels.
        if seed_result.scenario.step_labels is not None:
            step_labels = seed_result.scenario.step_labels
        else:
            step_labels = [int(x) for x in range(len(cmap.colors))]

        ax.legend(
            [mpatches.Patch(color=cmap_color) for cmap_color in cmap.colors],
            step_labels,
            title=step_title)
        ax.set_axisbelow(True)
        ax.grid(color='lightgray')

    plt.tight_layout()

    if legend_outside and legend:
        legend = ax.get_legend()
        # handle case of no legend
        if legend is not None:
            # handle case of blank legend... (may not occur)
            if len(legend.texts) > 0:
                # this hardcoded placement feels dangerous.
                legend.set_bbox_to_anchor((1.2, 1.03))

    return (fig, ax)


def plot_seed_capacity(
        seed_result,
        primary=True,
        lines=True,
        use_dt=False,
        ax=None,
        line_style=None,
        cmap=None,
        show_limits=True,
        legend=True,
        legend_outside=True,
        title=None,
        **kwargs
        ):
    """
    plot seed capacities of lines, and transformers
    """
    fig = plt.figure()

    if lines and primary:
        # primary lines
        kind = "Primary Lines"
        min_max_kind = [13]
        if line_style is None:
            line_style = 'solid'
    elif lines:
        # secondary lines
        kind = "Secondary Lines"
        min_max_kind = [14]
        if line_style is None:
            line_style = 'dashed'
    else:
        # transformer
        kind = "Transformers"
        min_max_kind = [15]
        if line_style is None:
            line_style = 'solid'

    if ax is None:
        ax = plt.gca()
    if cmap is None:
        cmap = cmr.torch_r

    n_steps = len(seed_result.step_results)
    cmap = cmr.get_sub_cmap(cmap, 0.2, .9, N=n_steps)

    for step, step_result in seed_result.step_results.items():
        dreams.pyplt.qsts.plot_step_system_extreme_element(
            step_result,
            kind=min_max_kind[0],
            use_dt=use_dt,
            ax=ax,
            legend=False,
            linestyle=line_style,
            colors=cmap.colors[step],
        )

    if show_limits:
        x = ax.lines[0].get_xdata()
        ax.plot(x,
                np.ones_like(x)*100,
                ':',
                c=[.4, .4, .4],
                zorder=0)

    if title is None:
        ax.set_title(f"Maximum Used Capacity of System {kind}")
    else:
        ax.set_title(title)

    if legend:
        # check for step title.
        if seed_result.scenario.step_title is None:
            step_title = "Step"
        else:
            step_title = seed_result.scenario.step_title

        # handle step labels.
        if seed_result.scenario.step_labels is not None:
            step_labels = seed_result.scenario.step_labels
        else:
            step_labels = [int(x) for x in range(len(cmap.colors))]

        ax.legend(
            [mpatches.Patch(color=cmap_color) for cmap_color in cmap.colors],
            step_labels,
            title=step_title)
        ax.set_axisbelow(True)
        ax.grid(color='lightgray')

    plt.tight_layout()

    if legend_outside and legend:
        legend = ax.get_legend()
        # handle case of no legend
        if legend is not None:
            # handle case of blank legend... (may not occur)
            if len(legend.texts) > 0:
                # this hardcoded placement feels dangerous.
                legend.set_bbox_to_anchor((1.2, 1.03))

    return (fig, ax)


def plot_seed_power(
        seed_result,
        kind=1,
        use_dt=False,
        ax=None,
        line_style=None,
        cmap=None,
        show_zero=True,
        legend=True,
        legend_outside=True,
        title=None,
        **kwargs
        ):
    """
    plot seed real (1) reactive (2), or apparent power(3) summations.

    """
    fig = plt.figure()

    if kind == 1:
        power_kind = 'Real'
    elif kind == 2:
        power_kind = 'Reactive'
    else:
        power_kind = 'Apparent'

    if ax is None:
        ax = plt.gca()

    if cmap is None:
        cmap = cmr.torch_r

    n_steps = len(seed_result.step_results)
    cmap = cmr.get_sub_cmap(cmap, 0.2, .9, N=n_steps)

    for step, step_result in seed_result.step_results.items():
        dreams.pyplt.qsts.plot_step_source_power_element(
            step_result,
            kind=kind,
            use_dt=use_dt,
            ax=ax,
            legend=False,
            colors=cmap.colors[step],
            linestyle=line_style
        )

    if show_zero:
        x = ax.lines[0].get_xdata()
        ax.plot(x,
                np.ones_like(x)*0,
                ':',
                c=[.4, .4, .4],
                zorder=0)

    if title is None:
        ax.set_title(f"{power_kind} Power Delivered From Substation")
    else:
        ax.set_title(title)

    if legend:
        # check for step title.
        if seed_result.scenario.step_title is None:
            step_title = "Step"
        else:
            step_title = seed_result.scenario.step_title

        # handle step labels.
        if seed_result.scenario.step_labels is not None:
            step_labels = seed_result.scenario.step_labels
        else:
            step_labels = [int(x) for x in range(len(cmap.colors))]

        ax.legend(
            [mpatches.Patch(color=cmap_color) for cmap_color in cmap.colors],
            step_labels,
            title=step_title)
        ax.set_axisbelow(True)
        ax.grid(color='lightgray')

    plt.tight_layout()

    if legend_outside and legend:
        legend = ax.get_legend()
        # handle case of no legend
        if legend is not None:
            # handle case of blank legend... (may not occur)
            if len(legend.texts) > 0:
                # this hardcoded placement feels dangerous.
                legend.set_bbox_to_anchor((1.2, 1.03))

    return (fig, ax)


def plot_seed_pv(
        seed_result,
        use_dt=False,
        ax=None,
        line_style=None,
        cmap=None,
        legend=True,
        legend_outside=True,
        title=None,
        pv_kind=7,
        **kwargs
        ):
    """
    plot seed pv contributions
    """
    fig = plt.figure()
    if ax is None:
        ax = plt.gca()
    if cmap is None:
        cmap = cmr.torch_r

    n_steps = len(seed_result.step_results)
    cmap = cmr.get_sub_cmap(cmap, 0.2, .9, N=n_steps)
    missing_steps = []

    for step, step_result in seed_result.step_results.items():
        try:
            dreams.pyplt.qsts.plot_step_system_extreme_element(
                step_result,
                kind=pv_kind,
                use_dt=use_dt,
                ax=ax,
                # legend=False,
                # linestyle=line_style,
                colors=cmap.colors[step],
            )
        except KeyError:
            # first step may not have any pv
            missing_steps.append(step)

    if len(missing_steps) > 0:
        x = ax.lines[0].get_xdata()
        for missing_step in missing_steps:
            ax.plot(x,
                    np.full(x.shape, np.nan),
                    c=cmap.colors[missing_step],
                    zorder=0)
    if title is None:
        ax.set_title("PV Seed Results")
    else:
        ax.set_title(title)

    if legend:
        # check for step title.
        if seed_result.scenario.step_title is None:
            step_title = "Step"
        else:
            step_title = seed_result.scenario.step_title

        # handle step labels.
        if seed_result.scenario.step_labels is not None:
            step_labels = seed_result.scenario.step_labels
        else:
            step_labels = [int(x) for x in range(len(cmap.colors))]

        ax.legend(
            [mpatches.Patch(color=cmap_color) for cmap_color in cmap.colors],
            step_labels,
            title=step_title)
        ax.set_axisbelow(True)
        ax.grid(color='lightgray')

    plt.tight_layout()

    if legend_outside and legend:
        legend = ax.get_legend()
        # handle case of no legend
        if legend is not None:
            # handle case of blank legend... (may not occur)
            if len(legend.texts) > 0:
                # this hardcoded placement feels dangerous.
                legend.set_bbox_to_anchor((1.2, 1.03))

    return (fig, ax)

def plot_seed_storage(
        seed_result,
        use_dt=False,
        ax=None,
        line_style=None,
        cmap=None,
        legend=True,
        legend_outside=True,
        title=None,
        storage_kind='storage_p',
        **kwargs
        ):
    """
    plot seed storage contributions
    """
    fig = plt.figure()
    if ax is None:
        ax = plt.gca()
    if cmap is None:
        cmap = cmr.torch_r

    n_steps = len(seed_result.step_results)
    cmap = cmr.get_sub_cmap(cmap, 0.2, .9, N=n_steps)
    missing_steps = []

    for step, step_result in seed_result.step_results.items():
        try:
            dreams.pyplt.qsts.plot_step_system_extreme_element(
                step_result,
                kind=storage_kind,
                use_dt=use_dt,
                ax=ax,
                # legend=False,
                # linestyle=line_style,
                colors=cmap.colors[step],
            )
        except KeyError:
            # first step may not have any pv
            missing_steps.append(step)

    if len(missing_steps) > 0:
        x = ax.lines[0].get_xdata()
        for missing_step in missing_steps:
            ax.plot(x,
                    np.full(x.shape, np.nan),
                    c=cmap.colors[missing_step],
                    zorder=0)
    if title is None:
        ax.set_title("Storage Seed Results")
    else:
        ax.set_title(title)

    if legend:
        # check for step title.
        if seed_result.scenario.step_title is None:
            step_title = "Step"
        else:
            step_title = seed_result.scenario.step_title

        # handle step labels.
        if seed_result.scenario.step_labels is not None:
            step_labels = seed_result.scenario.step_labels
        else:
            step_labels = [int(x) for x in range(len(cmap.colors))]

        ax.legend(
            [mpatches.Patch(color=cmap_color) for cmap_color in cmap.colors],
            step_labels,
            title=step_title)
        ax.set_axisbelow(True)
        ax.grid(color='lightgray')

    plt.tight_layout()

    if legend_outside and legend:
        legend = ax.get_legend()
        # handle case of no legend
        if legend is not None:
            # handle case of blank legend... (may not occur)
            if len(legend.texts) > 0:
                # this hardcoded placement feels dangerous.
                legend.set_bbox_to_anchor((1.2, 1.03))

    return (fig, ax)


# gen
def plot_seed_generator(
        seed_result,
        use_dt=False,
        ax=None,
        line_style=None,
        cmap=None,
        legend=True,
        legend_outside=True,
        title=None,
        generator_kind='generator_p',
        **kwargs
        ):
    """
    plot seed generator contributions
    """
    fig = plt.figure()
    if ax is None:
        ax = plt.gca()
    if cmap is None:
        cmap = cmr.torch_r

    n_steps = len(seed_result.step_results)
    cmap = cmr.get_sub_cmap(cmap, 0.2, .9, N=n_steps)
    missing_steps = []

    for step, step_result in seed_result.step_results.items():
        try:
            dreams.pyplt.qsts.plot_step_system_extreme_element(
                step_result,
                kind=generator_kind,
                use_dt=use_dt,
                ax=ax,
                # legend=False,
                # linestyle=line_style,
                colors=cmap.colors[step],
            )
        except KeyError:
            # first step may not have any pv
            missing_steps.append(step)

    if len(missing_steps) > 0:
        x = ax.lines[0].get_xdata()
        for missing_step in missing_steps:
            ax.plot(x,
                    np.full(x.shape, np.nan),
                    c=cmap.colors[missing_step],
                    zorder=0)
    if title is None:
        ax.set_title("Generator Seed Results")
    else:
        ax.set_title(title)

    if legend:
        # check for step title.
        if seed_result.scenario.step_title is None:
            step_title = "Step"
        else:
            step_title = seed_result.scenario.step_title

        # handle step labels.
        if seed_result.scenario.step_labels is not None:
            step_labels = seed_result.scenario.step_labels
        else:
            step_labels = [int(x) for x in range(len(cmap.colors))]

        ax.legend(
            [mpatches.Patch(color=cmap_color) for cmap_color in cmap.colors],
            step_labels,
            title=step_title)
        ax.set_axisbelow(True)
        ax.grid(color='lightgray')

    plt.tight_layout()

    if legend_outside and legend:
        legend = ax.get_legend()
        # handle case of no legend
        if legend is not None:
            # handle case of blank legend... (may not occur)
            if len(legend.texts) > 0:
                # this hardcoded placement feels dangerous.
                legend.set_bbox_to_anchor((1.2, 1.03))

    return (fig, ax)


def plot_seed_violations(
        seed_result,
        use_dt=False,
        as_percent=True,
        line_style=None,
        cmap=None,
        legend=True,
        x_rotation=None,
        title=None,
        **kwargs
        ):
    """
    Use element function to create full power plot
    kwargs passted to pandas dataframe plot function
    """
    fig = plt.figure()
    grid = plt.GridSpec(2, 2)

    axes = []

    if as_percent:
        append = 'Percents'
    else:
        append = 'Counts'

    if x_rotation is None and use_dt:
        x_rotation = 60

    if cmap is None:
        cmap = cmr.torch_r

    n_steps = len(seed_result.step_results)
    cmap = cmr.get_sub_cmap(cmap, 0.2, .9, N=n_steps)

    missing_steps = []

    for counter in list(range(0, 4)):
        axes.append(fig.add_subplot(grid[counter]))

        for step, step_result in seed_result.step_results.items():
            try:
                dreams.pyplt.qsts.plot_step_violation_element(
                    step_result,
                    kind=counter+1,
                    use_dt=use_dt,
                    ax=axes[counter],
                    as_percent=as_percent,
                    linestyle=line_style,
                    colors=cmap.colors[step],
                    rot=x_rotation,
                    **kwargs
                )
            except KeyError:
                # not all steps have violations?
                # thinik think this is not a thing.
                missing_steps.append(step)

    if legend:
        # check for step title.
        if seed_result.scenario.step_title is None:
            step_title = "Step"
        else:
            step_title = seed_result.scenario.step_title

        # handle step labels.
        if seed_result.scenario.step_labels is not None:
            step_labels = seed_result.scenario.step_labels
        else:
            step_labels = [int(x) for x in range(len(cmap.colors))]

        fig.legend(
            [mpatches.Patch(color=cmap_color) for cmap_color in cmap.colors],
            step_labels,
            title=step_title,
            loc=7,
            bbox_to_anchor=(1.15, 0.5),
            )

        fig.subplots_adjust(right=0.85)

    if title is None:
        fig.suptitle(f"System Violation {append}")
    else:
        fig.suptitle(title)

    plt.tight_layout()

    return (fig, axes)
