"""
functions related to creation and colection of monitors
required for QSTS hosting capacity
"""
import dreams

import opendssdirect as dssdirect
import numpy as np
import pandas as pd


def add_monitors_to_feeder(feeder):
    """
    collect monitor definitions and execute redirect to add monitors to model

    These are the 'default' always on monitors

    SO - idealy, these should be light/only include the substation as of now
    """
    monitor_definitions = get_source_monitor_definition(feeder)

    monitor_redirect = dreams.Redirect(lines=monitor_definitions)

    feeder.monitor_redirect = monitor_redirect
    feeder.monitor_redirect.execute()

    return monitor_redirect

def identify_voltage_bus_elements(feeder, buses_to_mon=None):
    """
    collect element to monitor for bus voltage

    this is useful because not every bus of interest is related to a single
    object type or uniform terminal.

    repurposed to work with monitor selector objects.
    """
    if buses_to_mon is None:
        primary_v_bus = feeder.buses['primary'].index.to_list()
    else:
        primary_v_bus = buses_to_mon
    
    voltage_bus_elements = {}
    not_found = 0
    element_type = ''
    terminal = 0
    missing_buses = []

    for bus in primary_v_bus:
        element_to_monitor = []

        if bus in feeder.lines['short_bus1'].values:
            element_to_monitor = feeder.lines[feeder.lines['short_bus1'] == bus]
            terminal = 1
            element_type = 'line'

        elif bus in feeder.lines['short_bus2'].values:
            element_to_monitor = feeder.lines[feeder.lines['short_bus2'] == bus]
            terminal = 2
            element_type = 'line'

        elif bus in feeder.transformers['short_bus1'].values:
            element_to_monitor = feeder.transformers[feeder.transformers['short_bus1'] == bus]
            terminal = 1
            element_type = 'transformer'

        elif bus in feeder.transformers['short_bus2'].values:
            element_to_monitor = feeder.transformers[feeder.transformers['short_bus2'] == bus]
            terminal = 2
            element_type = 'transformer'

        # NOTE: reactors treated as lines, will error if no reactors...
        elif bus in feeder.reactors['short_bus1'].values:
            element_to_monitor = feeder.reactors[feeder.reactors['short_bus1'] == bus]
            terminal = 1
            element_type = 'reactor'  # was line...

        elif bus in feeder.reactors['short_bus2'].values:
            element_to_monitor = feeder.reactors[feeder.reactors['short_bus2'] == bus]
            terminal = 2
            element_type = 'reactor'
        else:
            missing_buses.append(bus)
            not_found += 1
            continue

        if len(element_to_monitor) > 0:
            element_to_monitor = element_to_monitor.iloc[0]

        # create structure of monitor links
        element_name = element_to_monitor.name
        element_long_name = f"{element_type}.{element_name}"

        voltage_bus_elements[bus] = {}
        voltage_bus_elements[bus]['element_long_name'] = element_long_name
        voltage_bus_elements[bus]['element_name'] = element_name
        voltage_bus_elements[bus]['element_type'] = element_type
        voltage_bus_elements[bus]['terminal'] = terminal

    if not_found > 0:
        # NOTE: if any not found, check:
        # feeder.switches
        # feeder.voltage_regulators
        # feeder.voltage_sources
        # feeder.capacitors
        print(f'not found {not_found}')
        print(missing_buses)

    return pd.DataFrame.from_dict(voltage_bus_elements).T


def get_therm_monitor_definitions(feeder):
    """
    Generate monitor definitons for lines and transformers

    required because different thresholds (amps vs kva) for different elements

    NOTE: I believe this is deprecated.
    """
    # overkill with elemetns to monitor - simply slices of line or xfmr df
    lines_to_monitor = get_lines_to_monitor(feeder)
    xfmrs_to_monitor = get_xfmrs_to_monitor(feeder)

    thermal_monitor_definitions = []

    monitor_type = 'therm'

    element_type = 'line'
    for line_name, _ in lines_to_monitor.iterrows():
        # use mode 0 for amp limits
        monitor_name = f"{monitor_type}__{line_name}"
        element_def = f"{element_type}.{line_name}"

        monitor_def = f"new monitor.{monitor_name} element={element_def} mode=0"  # is this the right mode?
        thermal_monitor_definitions.append(monitor_def)

    element_type = 'transformer'
    for xfmr_name, _ in xfmrs_to_monitor.iterrows():
        # use mode 1 fo kVA limits

        monitor_name = f"{monitor_type}__{xfmr_name}"
        element_def = f"{element_type}.{xfmr_name}"

        monitor_def = f"new monitor.{monitor_name} element={element_def} mode=1"
        thermal_monitor_definitions.append(monitor_def)

    return thermal_monitor_definitions

def get_lines_to_monitor(feeder):
    """
    return dataframe of medium voltage (over 1 kV) lines
    """
    # identify lines
    line_mask_1 = feeder.lines['kv_base_1'] > 1
    line_mask_2 = feeder.lines['kv_base_2'] > 1

    line_mask = line_mask_1 | line_mask_2
    lines_to_monitor = feeder.lines[line_mask]
    return lines_to_monitor

def get_xfmrs_to_monitor(feeder):
    """
    retrn dataframe of medium voltage (over 1 kv) transformers
    """
    # identify transformers
    xfmrs_to_monitor = []
    if len(feeder.transformers) > 0:
        xfmrs_to_monitor = feeder.transformers[feeder.transformers['kv'] > 1]

    return xfmrs_to_monitor

def get_source_monitor_definition(feeder):
    """
    Generate monitor definiton for p and q vsource monitor
    """
    monitor_lines = []
    monitor_type = 'vsource'
    for index in feeder.voltage_sources.index:
        monitor_name = f"{monitor_type}__{index}"
        element_name = f"{monitor_type}.{index}"
        source_mon_0 = f"new monitor.{monitor_name} " \
            f"element={element_name} mode=1 ppolar=false"
        monitor_lines.append(source_mon_0)
    return monitor_lines


def collect_monitors():
    """
    return dictionary of all system monitors as their respective object class
    """

    monitor_dict = {}

    valid_monitor = dssdirect.Monitors.First()

    while valid_monitor:
        norm_amps = np.nan
        kva = np.nan

        monitor_full_name = dssdirect.Monitors.Name()

        monitor_type = monitor_full_name.split('__')[0].lower()
        # init dictionary for element types
        if monitor_type not in monitor_dict:
            monitor_dict[monitor_type] = {}

        # NOTE: 'may' speed up if: use WFV code, to collect. likely refactor
        monitor_df = dssdirect.utils.monitor_to_dataframe()

        # process to collect base kV - to convert recorded voltages PU
        # set monitor as active element
        dssdirect.Circuit.SetActiveElement(dssdirect.Monitors.Element())

        element_type = dssdirect.ActiveClass.ActiveClassName().lower()
        element_name = dssdirect.ActiveClass.Name()

        # if line, collect norm amps
        if monitor_type == 'therm' and element_type == 'line':
            # collect norm_amps for PU calculation
            dssdirect.Lines.Name(element_name)
            norm_amps = dssdirect.Lines.NormAmps()

        if monitor_type == 'therm' and element_type == 'reactor':
            # collect norm_amps for PU calculation
            norm_amps = float(dreams.dss.cmd(f"? reactor.{element_name}.normamps"))

        # if transformer, collect kva
        if monitor_type == 'therm' and element_type == 'transformer':
            # collect norm_amps for PU calculation
            dssdirect.Transformers.Name(element_name)
            kva = dssdirect.Transformers.kVA()

        # get bus name (may be for bus2)
        busses = dssdirect.dss.CktElement.BusNames()

        if isinstance(busses, list):
            correct_bus = ''
            bus_name = monitor_full_name.split('__')[-1]

            for possible_bus in busses:
                if bus_name in possible_bus:
                    correct_bus = possible_bus

            bus = correct_bus
        else:
            bus = busses

        # handle gen_hca bus selection
        if element_type == 'pvsystem':
            bus = busses[0]

        # handle load_hca bus selection
        if element_type == 'load':
            bus = busses[0]

        # set active bus for kv (later pu in monitor class)
        dssdirect.Circuit.SetActiveBus(bus)
        kv_base = dssdirect.Bus.kVBase()

        if monitor_type == 'volt':
            monitor_object = VoltageMonitor(
                bus,
                monitor_df,
                kv_base
            )
            monitor_dict[monitor_type][bus] = monitor_object

        elif monitor_type == 'therm':
            if element_type == 'line' or element_type == 'reactor':
                monitor_object = ThermalMonitorCurrent(
                    element_name,
                    bus,
                    monitor_df,
                    norm_amps
                )
                monitor_dict[monitor_type][element_name] = monitor_object

            elif element_type == 'transformer':
                monitor_object = ThermalMonitorApparentPower(
                    element_name,
                    bus,
                    monitor_df,
                    kva
                )
                monitor_dict[monitor_type][element_name] = monitor_object

        elif monitor_type == 'vsource':
            monitor_object = VoltageSourceMonitor(
                element_name,
                bus,
                monitor_df,
                kva
            )
            monitor_dict[monitor_type][element_name] = monitor_object

        elif monitor_type == 'gen_hca_s' or monitor_type == 'load_hca_s':
            # for hca monitor, collect p and q
            monitor_object = HCAssetMonitor(
                element_name,
                bus,
                monitor_df,
            )
            monitor_dict[monitor_type][element_name] = monitor_object

        else:
            print(f"{element_type} not handled in collect_monitors")

        # advance monitor element
        valid_monitor = dssdirect.Monitors.Next()

    return monitor_dict


# types of monitors specific to this apporach
class VoltageMonitor():
    """
    Handle Voltage Monitors.
    Will retain bus name
    """
    def __init__(
            self,
            bus=None,
            df=None,
            kv_base=None,
            ) -> None:

        self.bus = bus
        self.short_bus = bus.split('.')[0]
        self.kv_base = kv_base

        # find what phases are valid for monitor
        phases = ['1', '2', '3']
        voltages = [f"V{x}" for x in phases if f"V{x}" in df.columns]

        self.valid_voltage_phases = voltages

        # calculate PU voltage
        pu_voltages = df[voltages].div(kv_base * 1e3, axis=0)

        df = pd.concat(
            [df,
             pu_voltages.add_suffix('_PU'),
             ], axis=1
        )

        self.pu_voltage_cols = [f"{x}_PU" for x in voltages]
        self.df = df.replace(0.0, np.nan)  # to resolve issue with zeros

    def get_vector_max_v(self):
        """
        return vector of max pu voltages
        """
        return self.df[self.pu_voltage_cols].max(axis=1)

    def get_vector_min_v(self):
        """
        return vector of minimum pu voltages
        """
        return self.df[self.pu_voltage_cols].min(axis=1)

    def get_vector_ave_v(self):
        """
        return vector of average pu voltages
        """
        return self.df[self.pu_voltage_cols].mean(axis=1)

    def get_single_max_v(self):
        """
        return single largest PU voltage
        """
        return self.get_vector_max_v().max()

    def get_single_min_v(self):
        """
        return single lowest PU voltage
        """
        return self.get_vector_min_v().min()

    def get_single_ave_v(self):
        """
        return single average PU voltage
        """
        return self.get_vector_ave_v().mean()


class ThermalMonitorCurrent():
    """
    Handle thermal monitors on lines by checking PU current
    """
    def __init__(
            self,
            name=None,
            bus=None,
            df=None,
            norm_amps=None,
            ) -> None:

        self.name = name
        self.bus = bus
        self.short_bus = bus.split('.')[0]
        self.norm_amps = norm_amps

        # find what phases are valid for monitor
        phases = ['1', '2', '3']
        phases = [x for x in phases if f"V{x}" in df.columns]
        currents = [f"I{x}" for x in phases]

        # calculate PU current
        pu_currents = df[currents].div(norm_amps, axis=0)
        max_single_phase_current = pu_currents.max(axis=1)
        pu_total_currents = df[currents].sum(axis=1).div(norm_amps, axis=0)

        df = pd.concat(
            [df,
             pu_currents.add_suffix('_PU'),
             pu_total_currents.rename('I_total_PU'),
             max_single_phase_current.rename('I_max_PU'),
             ], axis=1
        )

        self.df = df

    def get_max_thermal_pu(self):
        """
        return maximum total pu current
        """
        return self.df.I_max_PU.max()

    def get_thermal_pu_vector(self):
        """
        return pu current vector
        """
        return self.df.I_max_PU
    

class HCAssetMonitor():
    """
    Handle aseet monitors which may be load or generation.
    Negative P values are generation
    """
    def __init__(
            self,
            name=None,
            bus=None,
            df=None,
            ) -> None:

        self.name = name
        self.bus = bus
        self.short_bus = bus.split('.')[0]

        # find what phases are valid for monitor
        phases = ['1', '2', '3']
        valid_phases = [x for x in phases if f"P{x} (kW)" in df.columns]
        p_cols = [f"P{x} (kW)" for x in valid_phases]
        q_cols = [f"Q{x} (kvar)" for x in valid_phases]

        # calculate total powers
        total_p = df[p_cols].sum(axis=1)
        total_q = df[q_cols].sum(axis=1)

        df = pd.concat(
            [df,
             total_p.rename('P_total'),
             total_q.rename('Q_total')
             ], axis=1
        )

        self.df = df

    def get_p_vector(self):
        """
        return total P
        """
        return self.df.P_total
    
    def get_q_vector(self):
        """
        return total P
        """
        return self.df.Q_total

class ThermalMonitorApparentPower():
    """
    Handle thermal monitors on transformers by checking PU apparent power
    """
    def __init__(
            self,
            name=None,
            bus=None,
            df=None,
            kva=None,
            ) -> None:

        self.name = name
        self.bus = bus
        self.short_bus = bus.split('.')[0]
        self.kva = kva

        # find what phases are valid for monitor
        phases = ['1', '2', '3']
        valid_phases = [x for x in phases if f"Ang{x}" in df.columns]
        apparent_power_cols = [f"S{x} (kVA)" for x in valid_phases]

        # calculate total S
        total_s = df[apparent_power_cols].sum(axis=1)
        pu_s = total_s.div(kva, axis=0)

        df = pd.concat(
            [df,
             total_s.rename('S_total'),
             pu_s.rename('S_total_PU')
             ], axis=1
        )

        self.df = df

    def get_max_thermal_pu(self):
        """
        return maximum total pu apparent power
        """
        return self.df.S_total_PU.max()

    def get_thermal_pu_vector(self):
        """
        return pu apparent power vector
        """
        return self.df.S_total_PU


class VoltageSourceMonitor(
):
    """
    Handle Voltage Source Monitors.

    Assumes PPolar=false so monitor returns p and q
    """
    def __init__(
            self,
            name=None,
            bus=None,
            df=None,
            kv_base=None,
            ) -> None:

        self.name = name
        self.bus = bus
        self.short_bus = bus.split('.')[0]
        self.kv_base = kv_base

        # calculate total Q
        p_cols = [f"P{x} (kW)" for x in range(4) if f"P{x} (kW)" in df.columns]
        df['P_total_kW'] = df[p_cols].sum(axis=1)

        self.df = df

    def get_max_kw_delivered(self):
        """
        return maximum amount of kw delivered
        NOTE: positive is delivered
        """
        return (self.df['P_total_kW'] * -1).max()

    def get_median_kw_delivered(self):
        """
        return maximum amount of kw delivered
        NOTE: positive is delivered
        """
        return (self.df['P_total_kW'] * -1).median()

    def get_min_kw_delivered(self):
        """
        return minimum amount of kw delivered
        NOTE: positive is delivered, negative is backfeeding
        """
        return (self.df['P_total_kW'] * -1).min()

    def get_total_p_vector(self):
        """
        Negative is backfeeding
        """
        return (self.df['P_total_kW'] * -1)

# monitor selector helpers
def add_thermal_montiors_from_ms(te_to_mon, debug=False):
    """
    create thermal monitors in the format that is acceptable to hc process.
    return created monitor name list
    """
    added_monitor_names = []

    for te in te_to_mon:
        if te == '':
            # no monitor added
            continue
        
        element_long_name = te.lower()
        element_short_name = element_long_name.split('.')[1]
        monitor_line = f"new monitor.therm__{element_short_name} element={element_long_name} mode=0 enabled=true"
        # add to model
        res = dreams.dss.cmd(monitor_line)
        if debug:
            print(f"{monitor_line} >> {res}")

        if res != '':
            # duplicate...
            enable_cmd = f"enable monitor.therm__{element_short_name}"
            res = dreams.dss.cmd(enable_cmd)
            if debug:
                print(f"{enable_cmd} >> {res}")

        added_monitor_names.append(f"therm__{element_short_name}")

    return added_monitor_names

def add_voltage_monitors_from_ms(feeder, bus_to_mon, debug=False):
    """
    create voltage monitors in the format that is acceptable to hc process
    return created monitor name list
    """
    # identify connected element to monitor
    ve_to_mon_df = identify_voltage_bus_elements(feeder, buses_to_mon=bus_to_mon)

    added_monitor_names = []

    for bus, vmon_element in ve_to_mon_df.iterrows():

        element_def = vmon_element['element_long_name']
        terminal = vmon_element['terminal']
        
        monitor_name = f"volt__{bus}"

        monitor_line = f"new monitor.{monitor_name} element={element_def} terminal={terminal} mode=0 enabled=true"
        # add to model
        # dreams.dss.cmd(monitor_line)
        # added_monitor_names.append(monitor_name)

        # add to model
        res = dreams.dss.cmd(monitor_line)
        if debug:
            print(f"{monitor_line} >> {res}")

        if res != '':
            # duplicate...
            enable_cmd = f"enable monitor.{monitor_name}"
            res = dreams.dss.cmd(enable_cmd)
            if debug:
                print(f"{enable_cmd} >> {res}")
                
        added_monitor_names.append(monitor_name)

    return added_monitor_names

def disable_monitors(added_monitors):
    """
    disables passed in monitors.
    """
    for monitor in added_monitors:
        montior_name = f"monitor.{monitor}"
        cmd = f"disable {montior_name}"
        res = dreams.dss.cmd(cmd)
        # print(res)
