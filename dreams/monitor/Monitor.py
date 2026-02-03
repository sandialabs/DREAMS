"""
Code directly related to Monitors
"""
import pandas as pd
import numpy as np
import opendssdirect as dssdirect
import dreams


def add_monitors_to_feeder(
        feeder,
        update=True):
    """
    Adds monitors to voltage sources, lines, pv systems, and transfromers
    Creates and executes a monitor redirect that is then saved to the feeder.

    TODO find better way to collect all system information
    lines will always collect bus 1 - but that mean all buses will be monitored

    - Current plan is to extract bus voltages from monitors during step result
    creation
    If there was a PU way, that'd be ideal
    It's slow to handle thousands of elements iteratively...

    TODO add list of elements to collect to eliminate block comment
    """
    if update:
        feeder.update()

    monitor_lines = []

    # create voltage source monitor
    monitor_type = 'vsource'
    for index in feeder.voltage_sources.index:
        monitor_name = f"{monitor_type}_{index}"
        element_name = f"{monitor_type}.{index}"
        source_mon_0 = f"new monitor.{monitor_name}_mode0 " \
            f"element={element_name} mode=0"
        monitor_lines.append(source_mon_0)

    monitor_type = 'pvsystem'
    for index in feeder.pv_systems.index:
        monitor_name = f"{monitor_type}_{index}"
        element_name = f"{monitor_type}.{index}"
        pv_mon_mode3 = f"new monitor.{monitor_name}_mode3 " \
            f"element={element_name} mode=3"
        monitor_lines.append(pv_mon_mode3)
        pv_mon_mode1 = f"new monitor.{monitor_name}_mode1 " \
            f"element={element_name} mode=1 ppolar=no"
        monitor_lines.append(pv_mon_mode1)

    monitor_type = 'storage'
    for index in feeder.storages.index:
        monitor_name = f"{monitor_type}_{index}"
        element_name = f"{monitor_type}.{index}"
        mon_mode7 = f"new monitor.{monitor_name}_mode7 " \
            f"element={element_name} mode=7"
        monitor_lines.append(mon_mode7)
        mon_mode1 = f"new monitor.{monitor_name}_mode1 " \
            f"element={element_name} mode=1 ppolar=no"
        monitor_lines.append(mon_mode1)

    monitor_type = 'generator'
    for index in feeder.generators.index:
        monitor_name = f"{monitor_type}_{index}"
        element_name = f"{monitor_type}.{index}"
        mon_mode1 = f"new monitor.{monitor_name}_mode1 " \
            f"element={element_name} mode=1 ppolar=no"
        monitor_lines.append(mon_mode1)

    """
    # TODO: allow for list of monitored elements....
    # handle line monitoring
    # Collects data at bus 1.
    monitor_type = 'line'
    for index in feeder.lines.index:
        monitor_name = f"{monitor_type}_{index}"
        element_name = f"{monitor_type}.{index}"
        line_mon_0 = f"new monitor.{monitor_name}_mode0 " \
            f"element={element_name} mode=0"
        monitor_lines.append(line_mon_0)

    # handle transformers
    # TODO: use mode 0 - calculate power?
    monitor_type = 'transformer'
    for index in feeder.transformers.index:
        monitor_name = f"{monitor_type}_{index}"
        element_name = f"{monitor_type}.{index}"
        xfmr_mon_1 = f"new monitor.{monitor_name}_mode1 " \
            f"element={element_name} mode=1"
        monitor_lines.append(xfmr_mon_1)

    # TODO: load, caps, vreg... (for bus voltages)...

    """

    monitor_redirect = dreams.Redirect(lines=monitor_lines)

    feeder.monitor_redirect = monitor_redirect
    feeder.monitor_redirect.execute()


def collect_monitors(origin='2023'):
    """
    Collect all monitors from simulation.

    Currently returns 'raw' dictionary of results.
    SHOULD be updated to return dictionary of class
    instead of
    monitor_dict[monitor_type][monitor_names[monitor_name_index]]['...'] = ...
    create
    name = monitor_names[monitor_name_index]
    monitor_dict[monitor_type][name] = dreams.hc.ObjectClass(name, ...)
    Use classes to further process results for easier analysis and aggregation

    """
    monitor_dict = {}

    valid_monitor = dssdirect.Monitors.First()

    dt_created = False

    while valid_monitor:
        monitor_full_name = dssdirect.Monitors.Name()
        monitor_element_full_name = dssdirect.Monitors.Element()
        monitor_type = monitor_element_full_name.split('.')[0].lower()
        monitor_short_name = monitor_element_full_name.split('.')[1].lower()

        # init dictionary for element types
        if monitor_type not in monitor_dict:
            monitor_dict[monitor_type] = {}

        # NOTE: should speed up if: use wills code, to collect passed
        monitor_df = dssdirect.utils.monitor_to_dataframe()

        if not dt_created:
            time_int = monitor_df['hour'].astype(int)*3600 \
                + monitor_df['second'].astype(int)
            monitor_df['dt'] = pd.to_datetime(
                time_int,
                unit='s',
                origin=origin,
                )
            original_df = monitor_df.copy()
            dt_created = True
        else:
            monitor_df['dt'] = original_df['dt'].copy()

        # process to collect base kV - to convert recorded voltages PU
        # set monitor as active element
        dssdirect.Circuit.SetActiveElement(dssdirect.Monitors.Element())

        # get bus name
        bus1 = dssdirect.dss.CktElement.BusNames()
        if len(bus1) > 1 or isinstance(bus1, list):
            bus1 = bus1[0]

        # set active bus
        dssdirect.Circuit.SetActiveBus(bus1)

        # get base kV
        kv_base = dssdirect.Bus.kVBase()

        # Collect information for capacity analysis
        if monitor_type == 'transformer':
            dssdirect.Transformers.Name(monitor_short_name)
            xfmr_kv = dssdirect.Transformers.kV()
            kva = dssdirect.Transformers.kVA()
            monitor_object = dreams.monitor.TransformerMonitor(
                name=monitor_short_name,
                df=monitor_df,
                bus1=bus1,
                xfmr_kv=xfmr_kv,
                kva=kva,
                origin=origin
                )
            monitor_dict[monitor_type][monitor_full_name] = monitor_object

        # TODO handle object creation - capacitor, transformer...
        elif monitor_type == 'vsource':
            monitor_object = dreams.monitor.VoltageSourceMonitor(
                name=monitor_short_name,
                df=monitor_df,
                bus1=bus1,
                kv_base=kv_base,
                origin=origin,
                )
            # ASSERT no name - assume only one source.
            monitor_dict[monitor_type] = monitor_object

        elif monitor_type == 'line':
            dssdirect.Lines.Name(monitor_short_name)
            norm_amps = dssdirect.Lines.NormAmps()
            monitor_object = dreams.monitor.LineMonitor(
                name=monitor_short_name,
                df=monitor_df,
                bus1=bus1,
                kv_base=kv_base,
                norm_amps=norm_amps,
                origin=origin
                )

            monitor_dict[monitor_type][monitor_short_name] = monitor_object

        elif monitor_type == 'pvsystem':
            # get kva rating.
            dssdirect.PVsystems.Name(monitor_short_name)
            kva_rating = dssdirect.PVsystems.kVARated()
            monitor_object = dreams.monitor.PVSystemMonitor(
                name=monitor_short_name,
                df=monitor_df,
                bus1=bus1,
                kv_base=kv_base,
                kva_rating=kva_rating,
                origin=origin
                )
            monitor_dict[monitor_type][monitor_full_name] = monitor_object

        elif monitor_type == 'storage':
            monitor_object = dreams.monitor.StorageMonitor(
                name=monitor_short_name,
                df=monitor_df,
                bus1=bus1,
                kv_base=kv_base,
                origin=origin
                )
            monitor_dict[monitor_type][monitor_full_name] = monitor_object

        elif monitor_type == 'generator':
            monitor_object = dreams.monitor.GeneratorMonitor(
                name=monitor_short_name,
                df=monitor_df,
                bus1=bus1,
                kv_base=kv_base,
                origin=origin
                )
            monitor_dict[monitor_type][monitor_full_name] = monitor_object

        # advance monitor element
        valid_monitor = dssdirect.Monitors.Next()

    return monitor_dict


def collect_monitors_old():
    """
    Collect all monitors from simulation.

    for posterity / not break everything while adapting new approach
    """
    monitor_dict = {}

    # collect system information for later reference
    xfmr_df = dssdirect.utils.transformers_to_dataframe()

    # collect monitor information into dictionary
    monitor_names = dssdirect.Monitors.AllNames()
    valid_monitor = dssdirect.Monitors.First()

    monitor_name_index = -1
    while valid_monitor:
        monitor_name_index += 1
        monitor_name = dssdirect.Monitors.Element()
        monitor_type = monitor_name.split('.')[0].lower()
        monitor_short_name = monitor_name.split('.')[1].lower()

        # init dictionary for element types
        if monitor_type not in monitor_dict:
            monitor_dict[monitor_type] = {}

        monitor_dict[monitor_type][monitor_names[monitor_name_index]] = {}
        monitor_dict[monitor_type][monitor_names[monitor_name_index]]['element'] = monitor_name

        monitor_dict[monitor_type][monitor_names[monitor_name_index]]['df'] = dssdirect.utils.monitor_to_dataframe()

        # process to collect base kV - to convert recorded voltages PU
        # set monitor as active element
        dssdirect.Circuit.SetActiveElement(dssdirect.Monitors.Element())

        # get bus name
        bus = dssdirect.dss.CktElement.BusNames()
        if len(bus) > 1 or type(bus) == list:
            bus = bus[0]

        # set active bus
        dssdirect.Circuit.SetActiveBus(bus)
        monitor_dict[monitor_type][monitor_names[monitor_name_index]]['bus1'] = bus

        # get base kV
        monitor_dict[monitor_type][monitor_names[monitor_name_index]]['kV_base'] = dssdirect.Bus.kVBase()

        # Collect information for capacity analysis
        if monitor_type == 'transformer':
            # dssdirect.Circuit.SetActiveElement(ele_fullName)
            # NOTE the above doesn't work...
            # thus the use of the data frame search
            if monitor_short_name in xfmr_df.index:
                # get kVA rating
                monitor_dict[monitor_type][monitor_names[monitor_name_index]]['kVA'] = xfmr_df.loc[monitor_short_name].kVA
                monitor_dict[monitor_type][monitor_names[monitor_name_index]]['xfmr_kV'] = xfmr_df.loc[monitor_short_name].kV
            else:
                monitor_dict[monitor_type][monitor_names[monitor_name_index]]['kVA'] = np.nan
                monitor_dict[monitor_type][monitor_names[monitor_name_index]]['xfmr_kV'] = np.nan

        elif monitor_type == 'line':
            # get amp rating
            dssdirect.Circuit.SetActiveElement(monitor_name)
            monitor_dict[monitor_type][monitor_names[monitor_name_index]]['norm_Amps'] = dssdirect.Lines.NormAmps()

        # advance monitor element
        valid_monitor = dssdirect.Monitors.Next()

    return monitor_dict


class LineMonitor():
    """
    Handle Line Monitors.

    Currently, relatively slow due to calculations and general number of lines.
    """
    def __init__(
            self,
            name=None,
            df=None,
            bus1=None,
            kv_base=None,
            norm_amps=None,
            over_voltage_threshold=1.05,
            under_voltage_threshold=0.95,
            over_capacity_threshold=1.00,
            origin='2023',
            ) -> None:

        self.name = name
        self.bus1 = bus1
        self.short_bus = bus1.split('.')[0]
        self.kv_base = kv_base
        self.norm_amps = norm_amps
        self.origin = origin
        self.over_voltage_threshold = over_voltage_threshold
        self.under_voltage_threshold = under_voltage_threshold
        self.over_capacity_threshold = over_capacity_threshold

        # attempt at more performant code...
        # find what phases are valid for monitor
        phases = ['1', '2', '3']
        phases = [x for x in phases if f"V{x}" in df.columns]
        voltages = [f"V{x}" for x in phases]
        currents = [f"I{x}" for x in phases]

        # calculate PU voltage
        pu_voltages = df[voltages].div(kv_base * 1e3, axis=0)
        # calculate PU current
        pu_currents = df[currents].div(norm_amps, axis=0)
        pu_total_currents = df[currents].sum(axis=1).div(norm_amps, axis=0)

        df = pd.concat(
            [df,
             pu_voltages.add_suffix('_PU'),
             pu_currents.add_suffix('_PU'),
             pu_total_currents.rename('I_total_PU'),
             pu_voltages.gt(over_voltage_threshold).any(axis=1).rename('over_voltage'),
             pu_voltages.lt(under_voltage_threshold).any(axis=1).rename('under_voltage'),
             pu_total_currents.gt(over_capacity_threshold).rename('over_capacity'),
             ], axis=1
        )

        self.df = df

        self.steps_over_capacity = sum(df['over_capacity'])
        self.steps_over_voltage = sum(df['over_voltage'])
        self.steps_under_voltage = sum(df['under_voltage'])

    def get_max_v(self):
        """
        return largest PU voltage
        """
        return self.df[['V1_PU', 'V2_PU', 'V3_PU']].max().max()

    def get_min_v(self):
        """
        return lowest PU voltage
        """
        return self.df[['V1_PU', 'V2_PU', 'V3_PU']].min().min()

    def get_max_current_pu(self):
        """
        return maximum total pu current
        """
        return self.df.I_total_PU.max()


class PVSystemMonitor():
    """
    Placeholder for QSTS result handling

    NOTE: possible speed up with alt df gen
    """
    def __init__(
            self,
            name=None,
            df=None,
            bus1=None,
            kv_base=None,
            kva_rating=None,
            origin='2023',
            ) -> None:

        self.name = name
        self.bus1 = bus1
        self.kv_base = kv_base
        self.kva_rating = kva_rating
        self.origin = origin

        # NOTE: this is still not super fast... / bordring slow
        # the datetime index could be done once?
        # create date time index
        time_int = df['hour'].astype(int)*3600 + df['second'].astype(int)
        df['dt'] = pd.to_datetime(time_int,
                                  unit='s',
                                  origin=self.origin)

        self.df = df


class StorageMonitor():
    """
    Placeholder for QSTS result handling

    NOTE: should speed up if: use wills code, 
    """
    def __init__(
            self,
            name=None,
            df=None,
            bus1=None,
            kv_base=None,
            kva_rating=None,
            origin='2023',
            ) -> None:

        self.name = name
        self.bus1 = bus1
        self.kv_base = kv_base
        self.kva_rating = kva_rating
        self.origin = origin

        # NOTE: this is still not super fast... / bordring slow
        # the datetime index could be done once?
        # create date time index
        time_int = df['hour'].astype(int)*3600 + df['second'].astype(int)
        df['dt'] = pd.to_datetime(time_int,
                                  unit='s',
                                  origin=self.origin)

        self.df = df


class GeneratorMonitor():
    """
    Standard object to collect monitor results
    """
    def __init__(
            self,
            name=None,
            df=None,
            bus1=None,
            kv_base=None,
            kva_rating=None,
            origin='2023',
            ) -> None:

        self.name = name
        self.bus1 = bus1
        self.kv_base = kv_base
        self.kva_rating = kva_rating
        self.origin = origin

        self.df = df


class TransformerMonitor():
    """
    Placeholder for QSTS result handling

    S comes from an expected mode 1 monitor...
    Voltage will also be desired...
    """
    def __init__(
            self,
            name=None,
            df=None,
            bus1=None,
            xfmr_kv=None,
            kva=None,
            origin='2023',
            ) -> None:

        self.name = name
        self.bus1 = bus1
        self.xfmr_kv = xfmr_kv
        self.kva = kva
        self.origin = origin

        # calculate total S
        s_cols = [f"S{x} (kVA)" for x in range(4) if f"S{x} (kVA)" in df.columns]
        df['S Total (kVA)'] = df[s_cols].sum(axis=1)
        df['s_total_pu'] = df['S Total (kVA)'] / self.kva

        self.df = df

    def get_max_kva(self):
        """
        return max of total apparent power
        """
        return self.df['S Total (kVA)'].max()

    def get_max_s_pu(self):
        """
        return max of total apparent power in PU
        """
        return self.df['s_total_pu'].max()


class VoltageSourceMonitor():
    """
    Handle Voltage Source Monitors.
    """
    def __init__(
            self,
            name=None,
            df=None,
            bus1=None,
            kv_base=None,
            origin='2023') -> None:

        self.name = name
        self.bus1 = bus1
        self.short_bus = bus1.split('.')[0]
        self.kv_base = kv_base
        self.origin = origin

        # perform data frame calculations
        # NOTE may be handled with mode 1?

        # handle each phase for power calculations
        phases = ['1', '2', '3']
        for phase in phases:
            # in case a phase is not used... untested if less than 3
            if f"V{phase}" not in df.columns:
                continue

            # calculate PU voltage
            df[f"V{phase}_PU"] = df[f"V{phase}"] / (self.kv_base * 1e3)

            # calculate complex power from phasor data
            # S = V I*
            v_ang = df[f"VAngle{phase}"] * (np.pi/180)
            v_complex = [complex(v*np.cos(ang), v*np.sin(ang)) for
                         v, ang in zip(df[f"V{phase}"], v_ang)]

            i_ang = df[f"IAngle{phase}"] * (np.pi/180)
            i_complex = [complex(i*np.cos(ang), i*np.sin(ang)) for
                         i, ang in zip(df[f"I{phase}"], i_ang)]

            s_complex = v_complex * np.conjugate(i_complex) / 1e3  # for SkVA

            # Seperate into P and Q
            p_out = np.real(s_complex)
            q_out = np.imag(s_complex)

            # put powers into df
            df[f"S{phase}_kVA"] = [np.abs(x) for x in s_complex]
            df[f"P{phase}_kW"] = p_out
            df[f"Q{phase}_kVAR"] = q_out

        # calculate total S
        s_cols = [f"S{x}_kVA" for x in range(4) if f"S{x}_kVA" in df.columns]
        df['S_total_kVA'] = df[s_cols].sum(axis=1)

        # calculate total P
        p_cols = [f"P{x}_kW" for x in range(4) if f"P{x}_kW" in df.columns]
        df['P_total_kW'] = df[p_cols].sum(axis=1)

        self.df = df

    def get_min_v(self):
        """
        return minimum PU voltage
        """
        v_cols = ['V1_PU', 'V2_PU', 'V3_PU',]
        return self.df[v_cols].min().min()

    def get_max_v(self):
        """
        return maximum PU voltage
        """
        v_cols = ['V1_PU', 'V2_PU', 'V3_PU',]
        return self.df[v_cols].max().max()

    def get_max_kw_delivered(self):
        """
        return maximum amount of kw delivered
        NOTE: positive is delivered
        """
        return (self.df['P_total_kW'] * -1).max()

    def get_min_kw_delivered(self):
        """
        return minimum amount of kw delivered
        NOTE: positive is delivered, negative is backfeeding
        """
        return (self.df['P_total_kW'] * -1).min()
