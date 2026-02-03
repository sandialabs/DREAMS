"""
Classes for results

Will need to be slightly different for step/snapshot or QSTS -
probably another file...

Violations only - only things over violation are stored
All - all voltages, powers, capacities are stored

NOTE: Thinkings:
Result class for each level of aggregation
* step
* seed
* scenario
And for QSTS and Snapshot

can use class for plotting!

"""
import pandas as pd
import dreams


class SnapshotStepResult():
    """
    Class to collect and export step results from snapshot simulation
    """
    def __init__(
            self,
            scenario,
            seed,
            step,
            detail_level=1
            ):
        """
        Handle updating feeder and collecting capacity and violation data.
        Use the detail parameter to define the level.
        0 for extremes and violations
        1 for all capacity and voltage information (in addition to 0)

        Created after the completion of a simulation step
        """
        self.scenario = scenario
        self.feeder = scenario.feeder
        self.seed = seed
        self.step = step
        self.detail_level = detail_level

        self.extremes = self.feeder.get_extremes(update_system=False)

        if detail_level == 1:
            # store full system data values
            self.voltage = self.feeder.bus_voltages.copy()
            self.capacity = self.feeder.capacity.copy()

        # violation information
        self.violations = self.feeder.id_violations()

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

    def __repr__(self) -> str:
        total_violations = (self.violations['n_over_capacity'] +
                            self.violations['n_over_voltage'] +
                            self.violations['n_under_voltage'])
        return f"Scenario: {self.scenario.name}, Seed: {self.seed}, " \
            f"Step:{self.step} , Total Violations: {total_violations}"

    def export_results(self):
        """
        Export results ... will use same base feeder process
        multiple csv outs... probalby better than multi tabbed excel?
        netCDF? Network Common Data Format...
        """

    def collect_load_allocation(self, element):
        """
        Handle collection allocations from load elements
        TODO - account for duplicate named elements - probably earlier..
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


class SnapshotSeedResult():
    """
    Class to aggregate and display all step results from a Seed.
    Input in expected to be the step result ditionary containing just
    the step results.

    eg SnapshotSeedResult(scenario.step_results[0])
    """

    def __init__(
            self,
            scenario,
            seed,
            step_results) -> None:
        self.scenario = scenario
        self.feeder = scenario.feeder
        self.seed = seed

        # handle extremes self.extremes
        extremes_dict = {step: result.extremes for step, result
                         in step_results.items()}
        self.extremes_df = pd.DataFrame.from_dict(
            extremes_dict,
            orient='index')

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

        # Handle Violations - count occurance and type of violation
        violation_types = ['over_capacity', 'over_voltage', 'under_voltage']
        violation_id = ['Name', 'Bus_Name', 'Bus_Name']
        violation_elements = {}
        violation_count = {}
        for step, result in step_results.items():
            violation_count[step] = {}
            violation_count[step]['over_capacity'] = result.violations[
                'n_over_capacity']
            violation_count[step]['over_voltage'] = result.violations[
                'n_over_voltage']
            violation_count[step]['under_voltage'] = result.violations[
                'n_under_voltage']

            for violation, id_field in zip(violation_types, violation_id):
                # check for existance...
                if result.violations[f"n_{violation}"] == 0:
                    continue

                # check for violations, if found, add to violation_elements
                names = result.violations[violation][id_field].values
                for name in names:
                    if name not in violation_elements:
                        violation_elements[name] = {}
                        violation_elements[name]['over_capacity'] = 0
                        violation_elements[name]['over_voltage'] = 0
                        violation_elements[name]['under_voltage'] = 0
                    violation_elements[name][violation] += 1

        self.violation_elements = pd.DataFrame.from_dict(
            violation_elements,
            orient='index'
            )
        self.violation_count = pd.DataFrame.from_dict(
            violation_count,
            orient='index'
        )
        # TODO further divide capacity violations into type
        # this will allow for a percent in violation figure
        # note - this is done in qsts results...
        # TODO handle optional voltage and capacity data

    def plot(self, kind='voltage', **kwargs):
        """
        Plot Seed results based on kind.
        TODO all combo?  other allocations as they arise
        TODO violation plot - total count, percent of system...
            would require counting type of element for capacity
        """
        if kind.lower() == 'voltage':
            return dreams.pyplt.plot_seed_voltage(
                self,
                step_labels=self.scenario.step_labels,
                step_title=self.scenario.step_title,
                **kwargs)

        elif kind.lower() == 'line':
            return dreams.pyplt.plot_seed_line_capacity(
                self,
                step_labels=self.scenario.step_labels,
                step_title=self.scenario.step_title,
                **kwargs)

        elif kind.lower() == 'transformer':
            return dreams.pyplt.plot_seed_transformer_capacity(
                self,
                step_labels=self.scenario.step_labels,
                step_title=self.scenario.step_title,
                **kwargs)

        elif kind.lower() == 'load_allocation':
            return dreams.pyplt.plot_seed_load_allocation(
                self,
                **kwargs)

        elif kind.lower() == 'pv_allocation':
            return dreams.pyplt.plot_seed_pv_allocation(
                self,
                **kwargs)

        elif kind.lower() == 'generator_allocation':
            return dreams.pyplt.plot_seed_generator_allocation(
                self,
                **kwargs)

        elif kind.lower() == 'pv_to_load':
            return dreams.pyplt.plot_seed_pv_to_load(
                self,
                **kwargs)

        elif kind.lower() == 'powers':
            return dreams.pyplt.plot_seed_substation_powers(
                self,
                step_labels=self.scenario.step_labels,
                step_title=self.scenario.step_title,
                **kwargs)
        else:
            print(f"'{kind}' is not a valid kind of plot.")

        return None


class SnapshotScenarioResult():
    """
    Class to combine all seed results and provide plotting
    """

    def __init__(self, scenario) -> None:
        """
        store various things, combine various things
        called at end of simulation
        """
        self.scenario = scenario

        # collect all step results into dataframes and store in object
        scenario_dict = {}
        scenario_dfs = {}

        for seed, seed_result in scenario.seed_results.items():
            df = seed_result.extremes_df
            for field in df.columns:

                if field not in scenario_dict:
                    scenario_dict[field] = []

                series = df[field]
                series.name = seed

                scenario_dict[field].append(series)

        for index, result_list in scenario_dict.items():
            df = pd.concat(result_list, axis=1)
            # only calculate average of all scenarios
            df['ave'] = df.mean(axis=1)

            scenario_dfs[index] = df

        self.dfs = scenario_dfs

    def plot(self, kind='voltage', **kwargs):
        """
        Plot scenario results - essentially all steps in one plot
        """
        if kind.lower() == 'voltage':
            return dreams.pyplt.plot_scenario_voltage(
                self,
                step_labels=self.scenario.step_labels,
                step_title=self.scenario.step_title,
                **kwargs)

        elif kind.lower() == 'line':
            return dreams.pyplt.plot_scenario_line_capacity(
                self,
                step_labels=self.scenario.step_labels,
                step_title=self.scenario.step_title,
                **kwargs)

        elif kind.lower() == 'transformer':
            return dreams.pyplt.plot_scenario_transformer_capacity(
                self,
                step_labels=self.scenario.step_labels,
                step_title=self.scenario.step_title,
                **kwargs)
        else:
            print(f"'{kind}' is not a valid kind of plot.")
