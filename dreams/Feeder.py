"""
Object definition for Feeder class to facilitate object oriented approach.
"""
import os
import pandas as pd
import opendssdirect as dssdirect

import dreams


class Feeder:
    """
    Collect general information for feeder - still a work in progress.
    Currently accepts the feeder path, and a name.

    Assumes the secondary kv limit as 0.5 and coordinate reference
    system (CRS) as 4326 - though both can be changed.

    The graph creation options is essentially a placeholder for options
    in the future.
    """
    def __init__(
            self,
            path,
            name='Unnamed_Feeder',
            secondary_kv_limit=0.5,
            load_mult=1.0,
            create_graph=False,
            crs=4326
            ):
        cwd = os.getcwd()

        # Store basic information
        if os.path.exists(path):
            self.path = path
        else:
            raise ValueError(f'Feeder Path "{path}" does not exist!')

        self.name = name
        self.secondary_kv_limit = secondary_kv_limit
        self.crs = crs
        self.load_mult = load_mult

        # Initialize attributes for later assignement via 'pass by reference'
        # these will update each solution
        self.capacity = None
        self.powers = None
        self.bus_voltages = None

        # These will typically not need to update every solution
        self.buses = None
        self.capacitors = None
        self.fuses = None
        self.generators = None
        self.lines = None
        self.loads = None
        self.pv_systems = None
        self.reactors = None
        self.transformers = None
        self.storages = None
        self.switches = None
        self.voltage_regulators = None
        self.voltage_sources = None

        # These deal with the graph process which is still WIP
        self.graph = None
        self.element_nodes = None

        # this is for qsts monitor redirect saving
        self.monitor_redirect = None

        self.is_solved = dreams.dss.solve_system(self.path)

        # this is for the HC part.
        self.scenarios = []

        if self.is_solved:
            # Update object to match DSS model states
            self.update()  # TODO handle
        else:
            self.stats = None

        # NOTE: this needs to be reworked post updated df collection
        if create_graph:
            print('Graph still WIP...')

        # because dssdirect commands can often change the working directory
        os.chdir(cwd)

    def __repr__(self) -> str:
        repr_str = [
            f"Feeder '{self.name}', crs={self.crs}\n"
            f"Useful methods: .solve .update .id_violations .plot\n"
            f"Useful attribtutes: .buses .lines .loads .transformers .stats\n"
            f"among others...\n"
        ]
        return "".join(repr_str)

    def update(self):
        """
        Updates all dataframes associated with feeder and feeder.stats
        """
        self.update_bus_voltages()
        self.update_capacity()
        self.update_powers()
        self.collect_element_dfs()  # NOTE: may not really need to be done
        self.stats = self.collect_feeder_stats()

    def solve(self,
              set_mode=False,
              mode='snapshot',
              load_mult=None):
        """
        Simple solve command to dss.  Returns boolean of convergence
        """
        if load_mult is None:
            load_mult = self.load_mult

        if set_mode:
            dreams.dss.cmd(f'solve mode={mode} loadmult={load_mult}')
        else:
            dreams.dss.cmd(f'solve loadmult={load_mult}')

        return dssdirect.Solution.Converged()

    def restart(self):
        """
        Relaod original feeder file, return boolena of convergence.
        """
        dreams.dss.cmd('clear all')
        dreams.dss.solve_system(self.path)
        return dssdirect.Solution.Converged()

    def id_violations(self):
        """
        returns dicitonary dataframes identifying capacity and voltage
        violations. Also identifies zero voltage nodes.
        """
        return dreams.dss.id_violations()

    def collect_element_dfs(self):
        """
        collect dataframes of 'all' feeder elements.
        Includes short_bus for connected elements.

        TODO: compare speed of this to faster(?) vining code
        """
        self.buses = dreams.dss.get_bus_info_df(
            self.secondary_kv_limit)
        self.capacitors = dreams.dss.get_capacitor_df()
        self.fuses = dreams.dss.get_fuse_df()
        self.generators = dreams.dss.get_generator_df()
        self.lines = dreams.dss.get_line_df(
            secondary_kv_limit=self.secondary_kv_limit
            )
        self.loads = dreams.dss.get_load_df(
            secondary_kv_limit=self.secondary_kv_limit
            )
        self.pv_systems = dreams.dss.get_pv_df()
        self.reactors = dreams.dss.get_reactor_df(
            secondary_kv_limit=self.secondary_kv_limit)
        self.storages = dreams.dss.get_storage_df()
        self.switches = dreams.dss.get_line_df(
            switches=True,
            secondary_kv_limit=self.secondary_kv_limit)
        self.transformers = dreams.dss.get_transformer_df()
        self.voltage_regulators = dreams.dss.get_voltage_regulator_df()
        self.voltage_sources = dreams.dss.get_voltage_source_df()

    def collect_feeder_stats(self):
        """
        functions used to collect general feeder stats, returns dictionary.
        """
        secondary_kv_limit = self.secondary_kv_limit
        # if feeder solves, collect solution information
        ckt_info = dreams.dss.get_feeder_counts(secondary_kv_limit)

        min_max = self.get_extremes(
            secondary_kv_limit=secondary_kv_limit,
            update_system=False,
            )

        # get only the number of violations
        vio = dreams.dss.id_violations()
        n_vio = {key: vio[key] for key in vio.keys() &
                 {'n_over_capacity',
                  'n_over_voltage',
                  'n_under_voltage',
                  'n_zero_voltage'}}

        # combine dictionaries into one
        full_dict = {**ckt_info, **min_max, **n_vio}

        # store information to self
        full_dict['path'] = self.path
        full_dict['name'] = self.name

        return full_dict

    def get_stats_df(self):
        """
        Updates feeder statistics and returns dataframe
        """
        self.stats = self.collect_feeder_stats()
        return pd.DataFrame.from_dict(self.stats, orient='index')

    def create_graph(self, solve_feeder=False):
        """
        create networkx graph of feeder, links dataframes to buses
        TODO: this is still in developement / though has been shown to work
        """
        self.graph = dreams.Graph(self, solve_feeder=solve_feeder)

    def plot(self,
             kind='profile',
             **kwargs):
        """
        Plot various kinds of python plots in a panda-esq way.

        Voltage plots use feeder.bus_voltage

        TODO: Handle line plotting... use gdf? (yes)
        """
        if kind.lower() == 'profile':
            return dreams.pyplt.plot_voltage_profile(
                self,
                secondary_kv_limit=self.secondary_kv_limit,
                **kwargs)

        elif kind.lower() == 'box':
            return dreams.pyplt.plot_voltage_box_whisker(
                self,
                secondary_kv_limit=self.secondary_kv_limit,
                **kwargs)

        elif kind.lower() == 'plotly':
            return dreams.pyplt.plotly_voltage_profile(
                self,
                secondary_kv_limit=self.secondary_kv_limit,
                **kwargs)

        elif kind.lower() == 'topo':
            return dreams.pyplt.plot_topology(
                self,
                **kwargs)
        else:
            print("Invalid kind of plot entered.")
            print("Valid kinds: profile, box, plotly, topo")

    def update_capacity(self):
        """
        Updater feeder capacity information
        """
        self.capacity = dreams.dss.get_capacity_df()

    def update_powers(self):
        """
        Updater feeder element power information
        """
        self.powers = dreams.dss.get_powers_df()

    def merge_bus_net_powers(
            self,
            return_df=False):
        """
        Merge the current powers to the feeders bus data frame
        """
        # ensure bus data frame exists
        if not hasattr(self, 'buses'):
            # NOTE: may have to change once update is optimized
            self.update()

        # remove previous powers if they exist
        columns_to_drop = [
            'p_kw_net',
            'q_kvar_net',
            's_kva_net'
        ]
        for column in columns_to_drop:
            if column in self.buses.columns:
                self.buses.drop(column, axis=1, inplace=True)

        # ensure power data frame exists
        if not hasattr(self, 'powers'):
            self.update_powers()

        buses_to_associate = {
            'load': 'loads',
            'pvsystem': 'pv_systems',
            'storage': 'storages',
            }
        # TODO incoroporate other sources or sinks... generators... etc

        power_to_sum = [
            'p_kw',
            'q_kvar',
            's_kva'
        ]

        for power_type in power_to_sum:
            element_sums = []
            for bus_type, attribute_name in buses_to_associate.items():
                if bus_type not in self.powers.type.unique():
                    continue
                mask = self.powers.type == bus_type
                elements = self.powers[mask]

                feeder_data = getattr(self, attribute_name).reset_index()
                feeder_data = feeder_data[['name', 'short_bus1']]

                # join short_bus_1 to elements
                element_buses = pd.merge(
                    elements,
                    feeder_data,
                    how='left',
                    left_on='short_name',
                    right_on='name',  # from index reset
                    )

                # sum bus powers and append to list
                element_sums.append(
                    element_buses.groupby('short_bus1')[power_to_sum].sum())

            # concat element bus contributions, sum by bus again for net power
            bus_total_power = pd.concat(element_sums).groupby('short_bus1').sum()
        # ensure net name
        bus_total_power.columns = [x + '_net' for x in bus_total_power.columns]

        # merge
        bus_powers = pd.merge(
            self.buses,
            bus_total_power,
            how='left',
            suffixes=('', '_net'),
            left_index=True,
            right_index=True
        )
        bus_powers.fillna(0, inplace=True)

        self.buses = bus_powers

        if return_df:
            return bus_powers

    def update_bus_voltages(self):
        """
        Update feeder bus voltage information.
        """
        self.bus_voltages = dreams.dss.get_bus_voltage_df()

    def get_extremes(
            self,
            secondary_kv_limit=None,
            update_system=True):
        """
        Collect capacity and voltage extremes.
        If update_system is true (default), update feeder capactiy and
        bus voltages as well as updating feeder stats.

        returns dictionary.

        TODO remove zero voltage elements from under voltage stats.
        """
        if secondary_kv_limit is None:
            secondary_kv_limit = self.secondary_kv_limit

        if update_system:
            self.update_capacity()
            self.update_powers()
            self.update_bus_voltages()

        results = {}  # for collecting returnable values in dictionary form
        voltages = pd.DataFrame()  # for masking raw values from feeder

        secondary_v_limit = secondary_kv_limit*1000  # voltage limit in volts

        voltages['Vmag'] = dssdirect.Circuit.AllBusVMag()
        voltages['VPU'] = dssdirect.Circuit.AllBusMagPu()

        # masks for easier data collection
        primary_mask = voltages['Vmag'] >= secondary_v_limit
        secondary_mask = voltages['Vmag'] < secondary_v_limit

        has_secondary = sum(secondary_mask) > 0

        # primary voltage collection
        results['primary_voltage_max'] = voltages['VPU'][primary_mask].max()
        results['primary_voltage_min'] = voltages['VPU'][primary_mask].min()
        results['primary_voltage_ave'] = voltages['VPU'][primary_mask].mean()

        # secondary voltage collection
        if has_secondary:
            results['secondary_voltage_max'] = voltages[
                'VPU'][secondary_mask].max()
            results['secondary_voltage_min'] = voltages[
                'VPU'][secondary_mask].min()
            results['secondary_voltage_ave'] = voltages[
                'VPU'][secondary_mask].mean()

        capacity_df = self.capacity
        line_mask = capacity_df['type'] == 'line'
        xfmr_mask = capacity_df['type'] == 'transformer'

        primary_mask = capacity_df['kvbase'] >= (secondary_v_limit/1000.00)
        secondary_mask = capacity_df['kvbase'] < (secondary_v_limit/1000.00)

        primary_line_mask = line_mask & primary_mask

        primary_capacity = capacity_df[primary_line_mask]

        results['primary_line_max_capacity'] = primary_capacity[
            '%normal'].max()
        results['primary_line_ave_capacity'] = primary_capacity[
            '%normal'].mean()

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

        # Collect substation powers
        total_powers = dssdirect.Circuit.TotalPower()
        results['substation_active_kw'] = -1.0 * total_powers[0]
        results['substation_rective_kvar'] = -1.0 * total_powers[1]

        # TODO: Collect System losses
        total_losses = dssdirect.Circuit.Losses()
        results['total_losses_kw'] = total_losses[0] / 1e3
        results['total_losses_kvar'] = total_losses[1] / 1e3

        if update_system:
            # update feeder statistics.
            self.stats.update(results)

        return results
