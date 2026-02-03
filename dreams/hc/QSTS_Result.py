"""
Classes for QSTS result handling
"""
import os
import pandas as pd
import xarray as xr
import dreams


class QSTSStepResult():
    """
    Collection of step results from QSTS.
    Specifically: extremes, violation_dfs, violation_counts, monitors, and
    element_allocations.

    Since it's QSTS, all results are lists or dataframes.
    Collects PV information (if available)

    Can do plotting at this stage - if desired...
    """
    def __init__(
            self,
            scenario,
            seed,
            step,
            system_statistics=None,
            violations=None,
            bus_voltages=None,
            ) -> None:

        self.scenario = scenario
        self.feeder = scenario.feeder
        self.seed = seed
        self.step = step
        self.raw_violations = violations
        self.bus_voltages = bus_voltages

        # handle output name
        output_name = scenario.name
        output_name = output_name.lower().replace(' ', '_')

        self.output_name = output_name

        # handle output path
        base_path = scenario.base_path
        output_path = os.path.join(base_path, 'results')

        if not os.path.exists(output_path):
            os.makedirs(output_path, exist_ok=True)

        self.output_path = output_path

        # collect extremes / min max averages
        self.extremes = pd.DataFrame.from_dict(
            system_statistics,
            orient='index')

        violations = pd.DataFrame.from_dict(
            violations,
            orient='index')

        # collect violation information into dataframes
        violation_dfs = {}
        violation_type = [
            'over_voltage',
            'under_voltage',
            'over_capacity',
            'over_capacity_transformers',
            'over_capacity_lines',
            ]
        for violation in violation_type:
            df_to_concat = []
            for key, value in violations[violation].items():
                # NOTE: corrected warning, issue.  unclear if other effects...
                df_copy = value.copy()
                df_copy['qsts_step'] = key
                df_to_concat.append(df_copy)
            violation_id_df = pd.concat(df_to_concat)
            violation_dfs[violation] = violation_id_df.reset_index()
        self.violation_dfs = violation_dfs

        # collect violation counts into dataframe
        count_columns = [
            'n_over_capacity_transformers',
            'n_over_capacity_lines',
            'n_over_capacity',
            'n_over_voltage',
            'n_under_voltage',
            'n_zero_voltage',
            # added 20250808
            'percent_violation_voltage',
            'percent_violation_primary_voltage',
            'percent_violation_secondary_voltage',
            'percent_violation_xfmr_capacity',
            'percent_violation_line_capacity',
            'percent_violation_primary_line_capacity',
            'percent_violation_secondary_line_capacity'
            ]
        self.violation_counts = violations[count_columns]

        # handle monitors into extremes dictionary
        self.monitors = dreams.monitor.collect_monitors()

        # handle pv (if it exists)
        self.collect_pv_data()
        
        # handle storage (if it exists)
        self.found_storage = 0
        if 'storage' in self.monitors:
            skip_mode_7 = False

            for key, value in self.monitors['storage'].items():

                self.found_storage += 0.5
                if self.found_storage == 0.5:
                    # init data frame
                    init_columns = ['hour', 'second', 'dt']
                    system_storage = value.df[init_columns].copy()
                    # init other values to collect
                    system_storage['system_storage_p_kw'] = 0.0
                    system_storage['system_storage_q_kvar'] = 0.0
                    system_storage['system_storage_ave_soc'] = 0.0
                    system_storage['system_storage_available_kwh'] = 0.0

                # check for mode of monitor
                if 'mode7' in key and not skip_mode_7:
                    system_storage['system_storage_ave_soc'] += value.df['%kW Stored']
                    system_storage['system_storage_available_kwh'] += value.df['kW Stored']

                if 'mode1' in key:
                    # sum p and q for pv fleet
                    # NOTE: all powers in OpenDSS are normally
                    # defined as positive INTO a terminal, thus, the -
                    # will show generation (flow out of a terminal) as +
                    kw_cols = value.df.columns.str.contains('kW')
                    kw = value.df[value.df.columns[kw_cols]].sum(axis=1)
                    system_storage['system_storage_p_kw'] -= kw

                    kvar_cols = value.df.columns.str.contains('kvar')
                    kvar = value.df[value.df.columns[kvar_cols]].sum(axis=1)
                    system_storage['system_storage_q_kvar'] -= kvar

            system_storage['system_storage_s_kva'] = ((
                system_storage['system_storage_p_kw'] ** 2 +
                system_storage['system_storage_q_kvar'] ** 2) ** (1/2)
            )

            system_storage['system_storage_pf'] = (
                system_storage['system_storage_p_kw'] /
                system_storage['system_storage_s_kva']
            )
            # calculate average soc
            system_storage['system_storage_ave_soc'] = system_storage['system_storage_ave_soc'] / self.found_storage

            # remove duplicate columns pre-concat
            duplicate_columns = ['hour', 'second', 'dt']
            system_storage.drop(columns=duplicate_columns, inplace=True)

            # attach storage info to extremes
            self.extremes = pd.concat([self.extremes, system_storage], axis=1)

        # handle generator monitors
        self.found_generator = False
        if 'generator' in self.monitors:
            for key, value in self.monitors['generator'].items():

                if self.found_generator is False:
                    # init data frame
                    init_columns = ['hour', 'second', 'dt']
                    system_storage = value.df[init_columns].copy()
                    # init other values to collect
                    system_storage['system_generator_p_kw'] = 0.0
                    system_storage['system_generator_q_kvar'] = 0.0
                    self.found_generator = True

                # check for mode of monitor
                if 'mode1' in key:
                    # sum p and q for pv fleet
                    # NOTE: all powers in OpenDSS are normally
                    # defined as positive INTO a terminal, thus, the -
                    # will show generation (flow out of a terminal) as +
                    kw_cols = value.df.columns.str.contains('kW')
                    kw = value.df[value.df.columns[kw_cols]].sum(axis=1)
                    system_storage['system_generator_p_kw'] -= kw

                    kvar_cols = value.df.columns.str.contains('kvar')
                    kvar = value.df[value.df.columns[kvar_cols]].sum(axis=1)
                    system_storage['system_generator_q_kvar'] -= kvar

            system_storage['system_generator_s_kva'] = ((
                system_storage['system_generator_p_kw'] ** 2 +
                system_storage['system_generator_q_kvar'] ** 2) ** (1/2)
            )

            system_storage['system_generator_pf'] = (
                system_storage['system_generator_p_kw'] /
                system_storage['system_generator_s_kva']
            )

            # remove duplicate columns pre-concat
            duplicate_columns = ['hour', 'second', 'dt']
            system_storage.drop(columns=duplicate_columns, inplace=True)

            # attach storage info to extremes
            self.extremes = pd.concat([self.extremes, system_storage], axis=1)


        # TODO other monitors... etc...
        # collect current allocation from elements
        elements = {}
        for allocation in self.scenario.allocations:
            for element in allocation.rules['element'].values():
                # TODO handle other allocation element types
                if isinstance(element,
                              dreams.hc.LoadAllocationElement):
                    element_dict = self.collect_load_allocation(element)
                    elements.update(element_dict)

                elif isinstance(element,
                                dreams.hc.PhotovoltaicAllocationElement):
                    element_dict = self.collect_pv_allocation(element)
                    elements.update(element_dict)

                elif isinstance(element,
                                dreams.hc.StorageAllocationElement):
                    element_dict = self.collect_storage_allocation(element)
                    elements.update(element_dict)

                elif isinstance(element,
                                dreams.hc.WindAllocationElement):
                    element_dict = self.collect_wind_allocation(element)
                    elements.update(element_dict)

        element_allocations = pd.DataFrame.from_dict(elements, orient='index')

        self.element_allocations = element_allocations

        # step violation aggergate
        self.violation_aggregate = self.collect_violation_aggregate()

    def __repr__(self) -> str:
        repr_str = [
            f"Step Results from '{self.scenario.name}', Step: {self.step}\n"
            f"Useful methods: .export_results .plot\n"
            f"Useful attribtutes: .extremes .monitors .violation_counts\n"
            f"Possibly Useful attributes: .element_allocations "
            f".violation_dfs .violation_aggregate .feeder .scenario\n"
        ]
        return "".join(repr_str)

    def collect_pv_data(self):
        """
        Collect various datas from the pv monitors.
        save results to the self.extremes dataframe.
        """
        self.found_pv = 0
        if 'pvsystem' not in self.monitors:
            return

        n_pv = len(self.feeder.pv_systems)

        irradiance_collected = False
        for monitor_name, monitor in self.monitors['pvsystem'].items():

            self.found_pv += 1
            if self.found_pv == 1:
                # init data frame
                init_columns = ['hour', 'second', 'dt']
                system_pv = monitor.df[init_columns].copy()
                # init other values to collect
                system_pv['n_system_pv'] = n_pv
                system_pv['irradiance'] = 0.0
                system_pv['system_pv_p_kw'] = 0.0
                system_pv['system_pv_q_kvar'] = 0.0

                system_pv['active_vv'] = 0.0
                system_pv['active_vw'] = 0.0

                system_pv['system_pv_p_kw_ideal'] = 0.0
                system_pv['n_over_generating'] = 0.0
                system_pv['n_curtailed'] = 0.0

            # check for mode of monitor
            if 'mode3' in monitor_name:
                if not irradiance_collected:
                    system_pv['irradiance'] = monitor.df['Irradiance']
                    irradiance_collected = True

                # will be positive
                system_pv['system_pv_p_kw_ideal'] += monitor.df['kW_out_desired']

                # control counts
                active_vv = (monitor.df['volt-var'] == -1).astype(int)
                if sum(active_vv) > 1:
                    # 0 for non operation, 1 for operation, 9999 for invalid
                    #active_vv[0] = 0  # handle issue with first step always being 1..?
                    system_pv['active_vv'] += active_vv

                active_vw = (monitor.df['volt-watt'] == 1).astype(int)
                if sum(active_vw) > 1:
                    # 0 for non operation, 1 for operation, 9999 for invalid
                    #active_vw[0] = 0  # handle issue with first step always being 1..?
                    system_pv['active_vw'] += active_vw

            if 'mode1' in monitor_name:
                # sum p and q for pv fleet
                # NOTE: all powers in OpenDSS are normally
                # defined as positive INTO a terminal, thus, the -
                # will show generation (flow out of a terminal) as +
                kw_cols = monitor.df.columns.str.contains('kW')
                kw = monitor.df[monitor.df.columns[kw_cols]].sum(axis=1)
                system_pv['system_pv_p_kw'] -= kw

                kvar_cols = monitor.df.columns.str.contains('kvar')
                kvar = monitor.df[monitor.df.columns[kvar_cols]].sum(axis=1)
                system_pv['system_pv_q_kvar'] -= kvar

                # account fo over/under generation
                mode3_name = monitor_name.replace('mode1', 'mode3')
                mode3_monitor = self.monitors['pvsystem'][mode3_name]

                max_p = mode3_monitor.df['kW_out_desired'].copy()
                actual_p = kw * -1

                # NOTE: semi-arbitrary threshold of 10 W
                over_generating = (max_p - actual_p) < -0.01
                if over_generating.sum() > 0:
                    system_pv['n_over_generating'] += (over_generating).astype(int)

                curtailed = (max_p - actual_p) > 0.01
                if curtailed.sum() > 0:
                    system_pv['n_curtailed'] += (curtailed).astype(int)

        # calculated variables
        system_pv['system_pv_s'] = ((
            system_pv['system_pv_q_kvar'] ** 2 +
            system_pv['system_pv_p_kw'] ** 2) ** (1/2)
        )

        system_pv['system_pv_pf'] = (
            system_pv['system_pv_p_kw'] /
            system_pv['system_pv_s']
        )

        system_pv['system_pv_kw_mismatch'] = system_pv['system_pv_p_kw_ideal'] - system_pv['system_pv_p_kw']

        # remove duplicate columns pre-concat
        duplicate_columns = ['hour', 'second', 'dt']
        system_pv.drop(columns=duplicate_columns, inplace=True)

        # attach pv info to extremes
        self.extremes = pd.concat([self.extremes, system_pv], axis=1)

    def export_results(self):
        """
        collect qsts time index, extremes, violation counts, and return
        single data frame.
        """
        # collect data for easier merge
        extremes = self.extremes
        violations = self.violation_counts

        # collect time from vsource monitor
        vsource_cols = ['hour', 'second', 'dt']
        qsts_time = self.monitors['vsource'].df[vsource_cols].copy()

        # include power from substation..
        p_columns = ['P1_kW', 'P2_kW', 'P3_kW']
        q_columns = ['Q1_kVAR', 'Q2_kVAR', 'Q3_kVAR']

        qsts_time['substation_p_kw'] = self.monitors['vsource'].df[p_columns].sum(axis=1) * -1.0
        qsts_time['substation_q_kvar'] = self.monitors['vsource'].df[q_columns].sum(axis=1) * -1.0

        combined_res = pd.merge(
            extremes,
            violations,
            how='left',
            left_index=True,
            right_index=True)

        combined_res = pd.merge(
            qsts_time,
            combined_res,
            how='left',
            left_index=True,
            right_index=True)

        # name index
        combined_res.index.rename('qsts_step', inplace=True)

        return combined_res

    def collect_load_allocation(self, element):
        """
        Handle collection allocations from load elements
        TODO - account for duplicate named elements - probably earlier..
        Same process as snapshot? seems like it...
        """
        name = element.name
        element_dict = {}
        element_dict[name] = {}
        total_elements = element.total_allocated_elements
        element_dict[name]['additional_loads'] = total_elements
        element_dict[name]['total_kw'] = element.total_allocated_kw
        element_dict[name]['total_kvar'] = element.total_allocated_kvar

        return element_dict

    def collect_pv_allocation(self, element):
        """
        Handle collection allocations from pv elements
        """
        name = element.name
        element_dict = {}
        element_dict[name] = {}
        total_elements = element.total_allocated_elements
        element_dict[name]['additional_pv'] = total_elements
        element_dict[name]['total_kva'] = element.total_allocated_kva
        element_dict[name]['total_kvar'] = element.total_allocated_kvar

        return element_dict

    def collect_wind_allocation(self, element):
        """
        Handle collection allocations from wind elements
        """
        name = element.name
        element_dict = {}
        element_dict[name] = {}
        total_elements = element.total_allocated_elements
        element_dict[name]['additional_wind_generators'] = total_elements
        element_dict[name]['total_kw'] = element.total_allocated_kw

        return element_dict

    def collect_storage_allocation(self, element):
        """
        Handle collection allocations from storage elements
        """
        name = element.name
        element_dict = {}
        element_dict[name] = {}
        total_elements = element.total_allocated_elements
        element_dict[name]['additional_storages'] = total_elements
        element_dict[name]['total_kva'] = element.total_allocated_kva
        element_dict[name]['total_kwh'] = element.total_allocated_kwh

        return element_dict

    def collect_violation_aggregate(self):
        """
        Create dictionary of violation aggregations
        including:....
        """
        scenario = self.scenario
        monitors = self.monitors
        raw_violations = self.raw_violations

        violation_results = {}

        overloaded_lines = {}
        overloaded_xfmrs = {}

        max_over_voltage = 0
        max_under_voltage = 0

        max_lines_overloaded = 0
        max_xfmr_overloaded = 0

        n_buses = len(scenario.feeder.buses)
        n_lines = len(scenario.feeder.lines)
        n_xfmrs = len(scenario.feeder.transformers)

        # this might be a thing...
        for qsts_step, violations in raw_violations.items():
            if violations['n_over_voltage'] > max_over_voltage:
                max_over_voltage = violations['n_over_voltage'] 

            if violations['n_under_voltage'] > max_under_voltage:
                max_under_voltage = violations['n_under_voltage'] 

            if violations['n_over_capacity_lines'] > max_lines_overloaded:
                max_lines_overloaded = violations['n_over_capacity_lines']

            if violations['n_over_capacity_transformers'] > max_xfmr_overloaded:
                max_xfmr_overloaded = violations['n_over_capacity_transformers']

            if violations['n_over_capacity_lines'] > 0:
                # for each step, collect xfmr in violation
                overloaded_line_names = violations['over_capacity_lines']['short_name'].to_list()
                overloaded_line_capacity = violations['over_capacity_lines'][' %normal'].to_list()
                # collect maximum overload
                for line_name, max_overload in zip(overloaded_line_names, overloaded_line_capacity):
                    if line_name in overloaded_lines:
                        # check if new value is larger
                        if max_overload > overloaded_lines[line_name]['max_overload_percent']:
                            overloaded_lines[line_name]['max_overload_percent'] = max_overload
                    else:
                        # add new entry
                        overloaded_lines[line_name] = {}
                        overloaded_lines[line_name]['max_overload_percent'] = max_overload

            if violations['n_over_capacity_transformers'] > 0:
                # for each step, collect xfmr in violation
                overloaded_xfmr_names = violations['over_capacity_transformers']['short_name'].to_list()
                overloaded_xfmr_capacity = violations['over_capacity_transformers'][' %normal'].to_list()
                # collect maximum overload
                for xfmr_name, max_overload in zip(overloaded_xfmr_names, overloaded_xfmr_capacity):
                    if xfmr_name in overloaded_xfmrs:
                        # check if new value is larger
                        if max_overload > overloaded_xfmrs[xfmr_name]['max_overload_percent']:
                            overloaded_xfmrs[xfmr_name]['max_overload_percent'] = max_overload
                    else:
                        # add new entry
                        overloaded_xfmrs[xfmr_name] = {}
                        overloaded_xfmrs[xfmr_name]['max_overload_percent'] = max_overload

        overloaded_xfmr_df = pd.DataFrame.from_dict(overloaded_xfmrs, orient='index')
        overloaded_xfmr_df.index.rename('name', inplace=True)
        transformers_to_upgrade = pd.merge(
            scenario.feeder.transformers,
            overloaded_xfmr_df,
            how='right',
            left_index=True,
            right_index=True,
        )

        overloaded_line_df = pd.DataFrame.from_dict(overloaded_lines, orient='index')
        overloaded_line_df.index.rename('name', inplace=True)
        lines_to_upgrade = pd.merge(
            scenario.feeder.lines,
            overloaded_line_df,
            how='right',
            left_index=True,
            right_index=True,
        )

        vsrc_df = monitors['vsource'].df
        vsrc_df = vsrc_df.set_index('dt')

        p_cols = ['P1_kW', 'P2_kW', 'P3_kW']
        combined_p = (vsrc_df[p_cols] * -1).sum(axis=1)
        has_backfeed = sum(combined_p < 0) > 0

        max_demand = round(max(combined_p))
        if len(scenario.feeder.pv_systems) > 0:
            total_pv_kva = round(scenario.feeder.pv_systems['kva'].sum())
        else:
            total_pv_kva = 0

        if len(scenario.feeder.transformers) > 0:
            total_xfmr_kva = round(scenario.feeder.transformers['kva'].sum())
        else:
            total_xfmr_kva = 0

        if has_backfeed:
            max_backfeed_kw = min(combined_p) * -1
            max_backfeed_kw = round(max_backfeed_kw)
        else:
            max_backfeed_kw = 0

        daily_bf = []
        for date, day_res in combined_p.groupby(combined_p.index.date):
            bf_mask = day_res < 0
            date_bf = day_res[bf_mask].sum()
            daily_bf.append(date_bf)

        max_backfeed_kwh = min(daily_bf) * -1
        max_backfeed_kwh = round(max_backfeed_kwh)

        violation_results['max_over_voltages'] = max_over_voltage
        violation_results['max_under_voltages'] = max_under_voltage
        violation_results['n_buses'] = n_buses

        violation_results['max_lines_overloaded'] = max_lines_overloaded
        violation_results['n_lines'] = n_lines

        violation_results['max_transformers_overloaded'] = max_xfmr_overloaded
        violation_results['n_transformers'] = n_xfmrs
        violation_results['total_transformer_kva'] = total_xfmr_kva

        violation_results['system_pv_kva'] = total_pv_kva
        violation_results['max_demand_kw'] = max_demand

        violation_results['has_backfeed'] = has_backfeed
        violation_results['max_backfeed_kw'] = max_backfeed_kw
        violation_results['max_daily_backfeed_kwh'] = max_backfeed_kwh

        violation_results['lines_to_upgrade'] = lines_to_upgrade
        violation_results['transformers_to_upgrade'] = transformers_to_upgrade

        return violation_results

    def export_violation_aggregate(self, output_path):
        """
        export violation aggregate multi-tab excel
        """
        if output_path is None:
            output_path = self.output_path

        file_name = os.path.join(
                output_path,
                self.output_name + f'_violation_agg-seed_{self.seed}_step_{self.step}.xlsx')

        violation_aggregate = self.collect_violation_aggregate()

        line_df = violation_aggregate.pop('lines_to_upgrade')
        xfmr_df = violation_aggregate.pop('transformers_to_upgrade')
        violation_df = pd.DataFrame.from_dict(violation_aggregate, orient='index')

        df_dict = {
            'stats': violation_df,
            'lines': line_df,
            'xfmr': xfmr_df
        }

        # export multi-tab excel
        writer = pd.ExcelWriter(file_name, engine='xlsxwriter')

        for tab, df in df_dict.items():
            df.to_excel(writer, sheet_name=tab)

        writer.close()

        return file_name


    def plot(self, kind='power', **kwargs):
        """
        'simple' plots of step results.
        kwargs are passed to plotting.
        Valid plot calls return a tuple of (fig, ax)
        """
        if kind == 'power':
            return dreams.pyplt.qsts.plot_step_source_power(
                self,
                **kwargs)
        elif kind == 'voltage':
            return dreams.pyplt.qsts.plot_step_voltages(
                self,
                **kwargs)
        elif kind == 'line':
            return dreams.pyplt.qsts.plot_step_line_capacity(
                self,
                **kwargs)
        elif kind == 'transformer':
            return dreams.pyplt.qsts.plot_step_transformer_capacity(
                self,
                **kwargs)
        elif kind == 'pv':
            return dreams.pyplt.qsts.plot_step_pv_contribution(
                self,
                **kwargs)
        elif kind == 'violations':
            return dreams.pyplt.qsts.plot_step_violation(
                self,
                **kwargs)
        else:
            print(f"kind '{kind}' not valid.")
            return None


class QSTSSeedResult():
    """
    Class to aggregate, export, and plot seed results

    Since QSTS are time series, I don't know if aggregating them beyond steps
    is actually useful.

    Maybe xarray has functionality that would make this useful, but as is,
    I think this may just be a class that hold steps, and has plotting
    functions.
    """
    def __init__(
            self,
            scenario,
            seed,
            step_results
            ) -> None:
        self.scenario = scenario
        self.feeder = scenario.feeder
        self.seed = seed
        self.step_results = step_results

        # handle element allocations self.element_allocations
        # NOTE this will likely be the same for each Seed
        # unless allocation is affected by randomness.
        allocation_dict = {}
        allocation_dfs = {}
        # create dictionary of dataframe allocations
        # where each df has an index of step for each allocation
        for step, result in step_results.items():
            for index, row in result.element_allocations.iterrows():
                if index not in allocation_dict:
                    allocation_dict[index] = {}
                allocation_dict[index][step] = row

        for name, allocation in allocation_dict.items():
            allocation_dfs[name] = pd.DataFrame.from_dict(
                allocation, orient='index')

        self.allocation_dfs = allocation_dfs

    def __repr__(self) -> str:
        repr_str = [
            f"Seed Results from '{self.scenario.name}', Seed: {self.seed}\n"
            f"Useful methods: .export_results .plot\n"
            f"use .plot(plot(kind='help') for list\n"
            f"Useful attribtutes: .allocation_dfs .step_results .scenario\n"
        ]
        return "".join(repr_str)

    def export_results(self):
        """
        collect step results, allocations, and step lables to return a
        dictionary of dataframes that can then be exported as a multi-tab
        excel file.
        """
        step_labels = self.scenario.step_labels
        if step_labels is None:
            # collect standard step labels
            step_labels = list(self.step_results.keys())

        # create result dictionary
        result_dict = {}

        # collect step results
        step_names = []
        for step, step_result in self.step_results.items():
            step_name = f"step_{step}"
            result_dict[step_name] = step_result.export_results()
            step_names.append(step_name)

        # create step id dataframe:
        step_id_dict = {
            'step_label': step_labels,
            'step_data_name': step_names
        }
        step_id_df = pd.DataFrame.from_dict(step_id_dict, orient='index').T

        # name index
        step_id_df.index.rename('step', inplace=True)

        # add to result dictionary
        result_dict['step_id'] = step_id_df

        # add allocation information
        allocation_data_names = []
        allocation_names = []

        # TODO account for battery allocation - may be handled..
        allocation_n = -1

        for allocation_name, allocation in self.allocation_dfs.items():
            allocation_n += 1

            allocation.index.rename('step', inplace=True)
            allocaiton_data_name = 'allocation_' + str(allocation_n)
            result_dict[allocaiton_data_name] = allocation

            allocation_data_names.append(allocaiton_data_name)
            allocation_names.append(allocation_name)

        # allocation_id_dict
        allocation_id_dict = {
            'allocation_name': allocation_names,
            'allocation_data_name': allocation_data_names
        }
        allocation_id_df = pd.DataFrame.from_dict(
            allocation_id_dict,
            orient='index').T

        # name index
        allocation_id_df.index.rename('allocation', inplace=True)

        result_dict['allocation_id'] = allocation_id_df

        return result_dict

    def plot(self, kind='voltage', **kwargs):
        """
        Plot QSTS results based on kind.
        NOTE: some plots utilize the kind keyword again....
        Think of a work around...
        - check for kind_2, or sub_kind, then repack into kwargs?
        """
        if kind.lower() == 'voltage':
            return dreams.pyplt.qsts.plot_seed_voltages(
                self,
                **kwargs)

        if kind.lower() == 'line':
            return dreams.pyplt.qsts.plot_seed_capacity(
                self,
                lines=True,
                **kwargs)

        if kind.lower() == 'transformer':
            return dreams.pyplt.qsts.plot_seed_capacity(
                self,
                lines=False,
                **kwargs)

        if kind.lower() == 'p':
            return dreams.pyplt.qsts.plot_seed_power(
                self,
                kind=1,
                **kwargs)

        if kind.lower() == 'q':
            return dreams.pyplt.qsts.plot_seed_power(
                self,
                kind=2,
                **kwargs)

        if kind.lower() == 's':
            return dreams.pyplt.qsts.plot_seed_power(
                self,
                kind=3,
                **kwargs)

        if kind.lower() == 'pv_p':
            return dreams.pyplt.qsts.plot_seed_pv(
                self,
                pv_kind=7,
                **kwargs)

        if kind.lower() == 'pv_q':
            return dreams.pyplt.qsts.plot_seed_pv(
                self,
                pv_kind=8,
                **kwargs)

        if kind.lower() == 'pv_s':
            return dreams.pyplt.qsts.plot_seed_pv(
                self,
                pv_kind=10,
                **kwargs)

        if kind.lower() == 'pv_irradiance':
            return dreams.pyplt.qsts.plot_seed_pv(
                self,
                pv_kind=6,
                **kwargs)

        if kind.lower() == 'pv_pf':
            return dreams.pyplt.qsts.plot_seed_pv(
                self,
                pv_kind=9,
                **kwargs)

        if kind.lower() == 'storage_p':
            return dreams.pyplt.qsts.plot_seed_storage(
                self,
                storage_kind='storage_p',
                **kwargs)

        if kind.lower() == 'storage_q':
            return dreams.pyplt.qsts.plot_seed_storage(
                self,
                storage_kind='storage_q',
                **kwargs)

        if kind.lower() == 'storage_soc':
            return dreams.pyplt.qsts.plot_seed_storage(
                self,
                storage_kind='storage_soc',
                **kwargs)

        if kind.lower() == 'storage_kwh':
            return dreams.pyplt.qsts.plot_seed_storage(
                self,
                storage_kind='storage_kwh',
                **kwargs)

        # generator plots
        if kind.lower() == 'generator_p':
            return dreams.pyplt.qsts.plot_seed_generator(
                self,
                generator_kind='generator_p',
                **kwargs)

        if kind.lower() == 'generator_q':
            return dreams.pyplt.qsts.plot_seed_generator(
                self,
                generator_kind='generator_q',
                **kwargs)

        if kind.lower() == 'generator_s':
            return dreams.pyplt.qsts.plot_seed_generator(
                self,
                generator_kind='generator_s',
                **kwargs)

        if kind.lower() == 'generator_pf':
            return dreams.pyplt.qsts.plot_seed_generator(
                self,
                generator_kind='generator_pf',
                **kwargs)
        # end generator plots

        if kind.lower() == 'violations':
            return dreams.pyplt.qsts.plot_seed_violations(
                self,
                **kwargs)

        if kind.lower() == 'load_allocation':
            return dreams.pyplt.plot_seed_load_allocation(
                self,
                **kwargs)

        if kind.lower() == 'pv_allocation':
            return dreams.pyplt.plot_seed_pv_allocation(
                self,
                **kwargs)

        if kind.lower() == 'storage_allocation':
            return dreams.pyplt.plot_seed_storage_allocation(
                self,
                **kwargs)

        if kind.lower() == 'generator_allocation':
            return dreams.pyplt.plot_seed_generator_allocation(
                self,
                **kwargs)

        if kind.lower() == 'pv_to_load':
            return dreams.pyplt.plot_seed_pv_to_load(
                self,
                **kwargs)

        valid_kinds = (
            "'voltage' : Minumum and maximum voltage plot\n"
            "'line' : Maximum and average line capacity\n"
            "'transformer' : Maximum and average transformer capaicyt\n"
            "'p' : Substation real power\n"
            "'q' : Substation reactive power\n"
            "'s' : Substation apparent power\n"
            "'pv_p' : PV fleet real power\n"
            "'pv_q' : PV fleet reactive power\n"
            "'pv_s' : PV fleet apparent power\n"
            "'pv_pf' : PV fleet powerfactor\n"
            "'pv_to_load' : PV fleet ratio to Load\n"
            "'violations' : System Violations\n"
            "'load_allocation' : Load Allocations\n"
            "'pv_allocation' : PV allocations\n"
            "'storage_p' : Storage Fleet real power\n"
            "'storage_q' : Storage Fleet reactive power\n"
            "'storage_soc' : Storage Fleet state of charge\n"
            "'generator_p' : Generator Fleet real power\n"
            "'generator_q' : Generator Fleet reactive power\n"
            "'generator_s' : Generator Fleet apparent power\n"
            "'generator_pf' : Generator Fleet power factor\n"
        )
        print(
            f"'{kind}' is not a valid kind of plot. "
            f"Valid plot kinds are: \n{valid_kinds}"
            )
        return None


class QSTSScenarioResult():
    """
    Aggregates seed results for export.

    Still in progress

    Thinking:
    similar to snapshot results, find averages of all seeds...

    Only required for steps - allocations 'should' be the same for each
    voilations would be interesting to average aswell
    so we could say, on average, a violation occurs at step x

    later, the acual violation elements could be collected and analyzed
    (for the heatmap of violation image)
    """
    def __init__(self, scenario) -> None:
        self.scenario = scenario
        self.seed_results = scenario.seed_results
        self.aggregate_results = self.aggregate_seed_results()

        # handle output name
        output_name = scenario.name
        output_name = output_name.lower().replace(' ', '_')

        self.output_name = output_name

        # handle output path
        base_path = scenario.base_path
        output_path = os.path.join(base_path, 'results')

        if not os.path.exists(output_path):
            os.makedirs(output_path, exist_ok=True)

        self.output_path = output_path

    def __repr__(self) -> str:
        repr_str = [
            f"Scenario Results from '{self.scenario.name}', Seeds: {list(self.seed_results.keys())}\n"
            f"Useful methods: .export_results\n"
            f"Useful attribtutes: .aggregate_results .step_results .scenario\n"
        ]
        return "".join(repr_str)

    def aggregate_seed_results(self):
        """
        idea is to aggregate results into worst case scenario...

        may be worth creating average results too.

        seems like using xarrray, then putting things back into a dictionary
        similar to seed results may be best

        should work... 
        doesn't include all the same tables as a step result export...
        """
        temp_steps = {}

        for seed, seed_result in self.seed_results.items():
            seed_results = seed_result.export_results()

            for step, step_result in seed_results.items():
                # skip results not associated to a step
                if step == 'step_id':
                    continue
                if 'step' not in step:
                    continue

                if step not in temp_steps:
                    temp_steps[step] = []
                # turn step result into data array
                da = xr.DataArray(step_result)
                da.coords['seed'] = seed
                da = da.rename({'dim_1': 'qty'})

                temp_steps[step].append(da)

        # combine all step results by seed into da and put into dictionary
        # NOTE: this is appparently an issue...
        da_steps = {key: xr.concat(step, dim='seed')
                    for key, step in temp_steps.items()}

        max_qty_names = [
            'hour', 'second', 'dt',  # included for index
            'primary_voltage_max',
            'secondary_voltage_max',
            'primary_line_max_capacity',
            'secondary_line_max_capacity',
            'transformer_max_capacity',
            ]

        min_qty_names = [
            'primary_voltage_min',
            'secondary_voltage_min', ]

        ave_qty_names = [
            'primary_voltage_ave',
            'secondary_voltage_ave',
            'primary_line_ave_capacity',
            'secondary_line_ave_capacity',
            'transformer_ave_capacity',
        ]

        all_qty_names = [
            'n_over_capacity_transformers', 'n_over_capacity_lines',
            'n_over_capacity', 'n_over_voltage', 'n_under_voltage',
            'n_zero_voltage']

        aggregate_res = {}

        # for each aggreagate, collect statistics
        # NOTE: somehwere in here is a divide by zero...
        for step, da in da_steps.items():
            if step not in aggregate_res:
                aggregate_res[step] = {}

            # for each step
            temp_aggregate = []

            for qty_name in max_qty_names:
                if qty_name not in da.qty:
                    continue
                #print(f"1 qty_name {qty_name}")
                temp_da = da.sel(qty=qty_name).max(dim='seed')
                temp_aggregate.append(
                    temp_da.drop('qty').to_dataframe(name=qty_name))

            for qty_name in min_qty_names:
                if qty_name not in da.qty:
                    continue
                #print(f"2 qty_name {qty_name}")
                temp_da = da.sel(qty=qty_name).min(dim='seed')
                temp_aggregate.append(
                    temp_da.drop('qty').to_dataframe(name=qty_name))

            for qty_name in ave_qty_names:
                if qty_name not in da.qty:
                    continue
                #print(f"3 qty_name {qty_name}")
                temp_da = da.sel(qty=qty_name).mean(dim='seed')
                temp_aggregate.append(
                    temp_da.drop('qty').to_dataframe(name=qty_name))

            # violation data
            for qty_name in all_qty_names:
                if qty_name not in da.qty:
                    continue
                #print(f"4 qty_name {qty_name}")
                temp_da = da.sel(qty=qty_name).max(dim='seed')
                temp_aggregate.append(
                    temp_da.drop('qty').to_dataframe(name='max_'+qty_name))

                temp_da = da.sel(qty=qty_name).min(dim='seed')
                temp_aggregate.append(
                    temp_da.drop('qty').to_dataframe(name='min_'+qty_name))

                temp_da = da.sel(qty=qty_name).mean(dim='seed').round()
                # include roundingn...
                temp_aggregate.append(
                    temp_da.drop('qty').to_dataframe(name='ave_'+qty_name))

            aggregate_res[step] = pd.concat(temp_aggregate, axis=1)

        #print('end of aggreagate seed results.')
        return aggregate_res

    def export_results(self, output_path=None, kind='general'):
        """
        export results as multi-tab excel in output_path locaitn.

        If output_path is None (default action), files exported to results 
        folder of base path.

        returns list of written files.

        TODO add violations to kinds (detail of violation each step)
        TODO add meta data from scenario for recreation....

        """
        valid_kinds = ['general']

        if kind not in valid_kinds:
            print(f"'{kind}' not a valid kind. Valid kinds: {valid_kinds}")

        if output_path is None:
            output_path = self.output_path

        written_files = []

        # for each seed
        for seed, seed_result in self.seed_results.items():
            # create name
            file_name = os.path.join(
                output_path,
                self.output_name + f'_{kind}_results_seed_{seed}.xlsx')

            # export multi-tab excel
            writer = pd.ExcelWriter(file_name, engine='xlsxwriter')

            if kind == 'general':
                for tab, df in seed_result.export_results().items():
                    df.to_excel(writer, sheet_name=tab)

            # TODO elif kind == 'violaions':...
            writer.close()
            written_files.append(file_name)

        # write aggregate results.
        file_name = os.path.join(
                output_path,
                self.output_name + f'_{kind}_results_aggregate.xlsx')
        writer = pd.ExcelWriter(file_name, engine='xlsxwriter')
        for tab, df in self.aggregate_results.items():
            df.to_excel(writer, sheet_name=tab)
        writer.close()
        written_files.append(file_name)

        return written_files
