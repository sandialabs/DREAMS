"""
Class for defining Hosing capacity Scenarios
"""
import os
import sys
import dreams
import numpy as np
import pandas as pd


class Scenario():
    """
    for running snapshot or qsts simulaionts

    qsts will require profiles for sets of elements.
        pv, demand ev
        will requrie monitor creation for elements (Base redirects?)

    will also need to include controls of some kind - redirects?

    """

    def __init__(
            self,
            name,
            feeder,
            duration_seconds=0,  # NOTE: will be a time measurement for QSTS
            n_steps: int = 10,
            n_simulations: int = 1,
            max_iterations: int = 15,
            max_control_iterations: int = 15,
            qsts_profile='yearly',
            qsts_hour_offset=0,
            qsts_step_size_sec=300,
            qsts_origin='2026',
            control_mode='static',
            base_path=None,
            seed: int = 0,
            path_to_base_redirects=None,
            minimize_duplicates=True,  # for better handling of location
            step_labels=None,  # for plot lables
            step_title=None,  # for legend title
            collect_bus_v=False,
            ):
        self.name = name
        self.feeder = feeder

        self.max_iterations = max_iterations
        self.max_control_iterations = max_control_iterations

        self.duration_seconds = int(duration_seconds)  # 0 for Snapsot, else QSTS

        self.control_mode = control_mode
        self.qsts_profile = qsts_profile  # to chose mode
        self.qsts_hour_offset = qsts_hour_offset
        self.qsts_step_size_sec = qsts_step_size_sec
        if (qsts_step_size_sec > duration_seconds) and (duration_seconds > 0):
            # should be an error...
            print(f"Total QSTS duration {duration_seconds} less "
                  f"than single step size {qsts_step_size_sec}.")
            sys.exit()
        self.n_qsts_steps = int(duration_seconds / qsts_step_size_sec)
        self.qsts_origin = qsts_origin  # for start time of time series data

        self.n_steps = n_steps  # System states in each seed
        self.step_labels = step_labels
        self.step_title = step_title
        self.n_simulations = n_simulations  # equivalent to number of seeds

        self.initial_seed = seed
        self.all_seeds = []  # TODO: fix append
        self.seed = {}

        self.step_results = {}
        self.seed_results = {}
        self.results = None

        self.allocations = []
        self.minimize_duplicates = minimize_duplicates

        self.steps_created = False

        self.path_to_base_redirects = path_to_base_redirects
        self.base_redirects = []
        self.n_base_redirects = 0

        self.control_redirects = {}

        self.collect_bus_v = collect_bus_v

        # add any base redirects to scenario
        if path_to_base_redirects is not None:
            try:
                base_redirect_files = os.listdir(path_to_base_redirects)
                # for each dss file, append to base redirects.
                for file in base_redirect_files:
                    if '.dss' in file:
                        redirect_location = os.path.join(
                            path_to_base_redirects,
                            file
                        )
                        self.base_redirects.append(
                            dreams.Redirect(file_location=redirect_location,
                                            read_file=True))
                        self.n_base_redirects += 1

            except FileNotFoundError:
                print("Path to base redirects not found.")
            except NotADirectoryError:
                print("Path to base redirects is not a directory.")
        else:
            feeder_path = os.path.split(feeder.path)[0]
            base_redirect_path = os.path.join(feeder_path, 'base_redirects')
            if not os.path.isdir(base_redirect_path):
                os.makedirs(base_redirect_path, exist_ok=True)
            self.path_to_base_redirects = base_redirect_path

        # define base path for scenario
        if base_path is None:
            feeder_path = os.path.split(feeder.path)[0]
            scenarios_path = os.path.join(feeder_path, 'QSTS_scenarios')
            scenario_path = os.path.join(scenarios_path, name)
            control_path = os.path.join(feeder_path, 'control_redirects')

            paths_to_ensure = [scenarios_path, scenario_path, control_path]
            for path in paths_to_ensure:
                if not os.path.isdir(path):
                    os.makedirs(path, exist_ok=True)
            self.base_path = scenario_path
            self.control_redirect_path = control_path
        else:
            self.base_path = base_path
            self.control_redirect_path = os.path.join(
                base_path,
                'control_redirects',
                )

    def __repr__(self) -> str:
        repr_str = [
            f"Hosting Capacity Scenario '{self.name}'\n"
            f"Using feeder '{self.feeder.name}'\n"
            f"Useful attribtutes: .results .seed_results .step_results\n"
            f"Additional attributes: .feeder .allocations .base_redirects \n"
        ]
        return "".join(repr_str)

    def add_allocation(self, allocation):
        """add allocation to scenario"""
        # add allocation to self
        if isinstance(allocation, dreams.hc.Allocation):
            self.allocations.append(allocation)

    def execute_base_redirects(self):
        """
        Execute all base redirects attached to scenario
        """
        if len(self.base_redirects) != 0:
            for redirect in self.base_redirects:
                redirect.execute()

    def add_control_redirect(self, control_redirect, start_step=1):
        """ add control redirect to dictionary while accounting
        for optional start step that is not 1
        """
        name = control_redirect.name
        self.control_redirects[name] = {}
        self.control_redirects[name]['redirect'] = control_redirect
        self.control_redirects[name]['start_step'] = start_step

    def execute_control_redirects(self, step):
        """
        Execute all control redirects attached to scenario
        """
        if len(self.control_redirects) != 0:
            for redirect in self.control_redirects.values():
                if step >= redirect['start_step']:
                    redirect['redirect'].execute()

    def create_simulation_seeds(self):
        """create object dictionary of redirects for simulation seeds"""
        # set seed
        np.random.seed(self.initial_seed)

        # create all other simulation seeds
        self.all_seeds.append(self.initial_seed)

        # NOTE: limits number of unique monte carlo sims to 10k
        while len(self.all_seeds) < self.n_simulations:
            next_seed = np.random.randint(0, 9999)
            seeds = list(self.all_seeds)
            seeds.append(next_seed)
            self.all_seeds = list(set(seeds))

        # for each simulation seed
        for seed in self.all_seeds:
            self.seed[seed] = {}
            self.seed[seed] = {step: {} for step in range(self.n_steps+1)}

            # TODO: need to reset control der list each seed...

            # for each allocation
            for allocation in self.allocations:
                np.random.seed(seed)
                # for each element to allocate.
                element_items = allocation.rules['element'].items()
                for element_name, element_allocation in element_items:
                    allocation.update_viable_buses()

                    # get number of element lines per step
                    lines_per_step = element_allocation.get_lines_per_step(
                        self.n_steps)

                    # calculate how many total items to create
                    # total_elements = lines_per_step * self.n_steps
                    total_elements = int(sum(lines_per_step))

                    # collect all viable buses as a list
                    possible_buses = list(
                        allocation.viable_bus_size_limits.keys()
                        )

                    # create random list of all locations to use for allocation
                    if self.minimize_duplicates:
                        # use all possible locations before duplicates
                        random_indicies = list(range(0, len(possible_buses)))
                        # shuffle all possible bus index - inplace operation
                        np.random.shuffle(random_indicies)

                        # handle case where duplicates exist
                        while len(random_indicies) < total_elements:
                            additional_indicies = random_indicies.copy()
                            np.random.shuffle(additional_indicies)
                            random_indicies = (
                                random_indicies
                                + additional_indicies
                                )

                        random_indicies = random_indicies[0:total_elements]

                    else:
                        # more 'random' - will include more duplicates
                        random_indicies = [
                            np.random.randint(0, len(possible_buses)) for _
                            in range(total_elements)]

                    self.create_step_redirects(
                        allocation,
                        element_name,
                        lines_per_step,
                        possible_buses,
                        random_indicies,
                        seed
                    )

        self.steps_created = True

    def create_step_redirects(
            self,
            allocation,
            element_name,
            lines_per_step,
            possible_buses,
            random_indicies,
            seed
            ):
        """
        Create lines and redirects based on allocation, store in self

        TODO this should be refactored to allow easier addition
        of more elment types.
        """
        element_allocation = allocation.rules['element'][element_name]

        # handle optional shape rule
        if len(allocation.rules['shape']) > 0:
            kind = allocation.rules['shape']['kind']
            name = allocation.rules['shape']['name']
            shape = f" {kind}={name}"
        else:
            shape = ""

        # TODO handle optional control rule?
        valid_control = False
        if len(allocation.rules['control']) > 0:
            control_dict = {}
            # init control dictionary - thinking is [rule] = derlist
            for control_rule in allocation.rules['control']:
                control_dict[control_rule] = None

            # connect to control redirects...
            for control_redirect_name in self.control_redirects:
                # check if allocation control name is in
                # scenario control redirects
                if control_redirect_name in control_dict:
                    control_dict[control_redirect_name] = self.control_redirects[control_redirect_name]['redirect']
                    valid_control = True
                    if hasattr(control_dict[control_rule], 'der_list'):
                        control_dict[control_rule].der_list = []

        # use allocation rules to generate standard dss 'line'
        # TODO: write lines for each element allocation class
        if isinstance(element_allocation, dreams.hc.LoadAllocationElement):
            # handle load allocations
            element_allocation.reset_allocation_tracking()

            kw_per_line = element_allocation.get_kw_per_line()
            kvar_per_line = element_allocation.get_kvar_per_line()
            pre_name = element_allocation.element_prepend

            lines_per_step_list = lines_per_step
            lps_index = 0  # line per step
            written_lines = 0
            lines = []

            # this is a little weird - fix for zero allocation in first step
            if lines_per_step_list[0] == 0:
                first_non_zero_lps = next(
                    (i for i, x in enumerate(lines_per_step_list) if x), None)
                next_write = lines_per_step_list[first_non_zero_lps]
            else:
                first_non_zero_lps = 0
                next_write = lines_per_step_list[0]

            for random_index in random_indicies:
                long_bus = possible_buses[random_index]
                short_bus = dreams.dss.get_short_bus_name(long_bus)
                bus_df = self.feeder.buses.loc[short_bus]
                bus_kv = bus_df.kv_base
                # TODO handle equal phase split
                line = f"New load.{pre_name}{written_lines+1}_{short_bus} "\
                       f"bus1={long_bus} kV={bus_kv} phases=1 "\
                       f"Vmaxpu=2 Vminpu=0.7 conn=wye "\
                       f"kW={kw_per_line} kvar={kvar_per_line}" + shape

                lines.append(line)
                written_lines += 1

                # TODO: handle capacity tracking... method?
                # send bus name and energy allocation

                # create redirect every lines_per_step
                if written_lines % next_write == 0:

                    lps_index += 1
                    step = lps_index

                    next_write = int(sum(lines_per_step_list[0:(
                        lps_index+1+first_non_zero_lps)]))

                    # update allocations for redirect info line
                    element_allocation.update_allocation_tracking(step)
                    allocation_info = f"{element_allocation}"
                    allocation_info = '! ' + allocation_info

                    lines_to_write = lines.copy()
                    lines_to_write.append(allocation_info)

                    # create step redirect
                    if first_non_zero_lps > 0:
                        step_offset = first_non_zero_lps - 1
                    else:
                        step_offset = 0

                    self.seed[seed][step+step_offset][element_name] = dreams.Redirect(
                        element_name,
                        lines=lines_to_write
                    )

        if isinstance(
            element_allocation,
            dreams.hc.PhotovoltaicAllocationElement):

            # reset between seeds...
            element_allocation.reset_allocation_tracking()
            #if valid_control:
            #    for control_rule in control_dict:
            #        if hasattr(control_dict[control_rule], 'der_list'):
            #            control_dict[control_rule].der_list = []

            kva_per_line = element_allocation.get_kva_per_line()
            kvar_per_line = element_allocation.get_kvar_per_line()
            pre_name = element_allocation.element_prepend
            allocation_kv = element_allocation.element_kv
            irradiance = element_allocation.irradiance
            element_pf = element_allocation.element_pf

            lines_per_step_list = lines_per_step
            lps_index = 0  # line per step
            written_lines = 0
            lines = []

            # this is a little weird - fix for zero allocation in first step
            if lines_per_step_list[0] == 0:
                first_non_zero_lps = next(
                    (i for i, x in enumerate(lines_per_step_list) if x), None)
                next_write = lines_per_step_list[first_non_zero_lps]
            else:
                first_non_zero_lps = 0
                next_write = lines_per_step_list[0]

            for random_index in random_indicies:
                long_bus = possible_buses[random_index]
                short_bus = dreams.dss.get_short_bus_name(long_bus)
                bus_df = self.feeder.buses.loc[short_bus]

                if element_allocation.match_bus_phase:
                    # match bus phase for system
                    phase_to_use = long_bus.replace(short_bus, '')
                    phase_to_use = phase_to_use[1:]  # remove first period
                    n_phases_to_use = bus_df['n_phases']
                    # print(f"{short_bus}.{phase_to_use} phases={n_phases_to_use}")
                else:
                    n_phases_to_use = 1
                    # select random phase if more than one
                    n_phases = bus_df['n_phases']
                    if n_phases > 1:
                        phases = bus_df['phases']
                        # pick random available phase for allocation
                        phase_to_use = np.random.choice(list(phases))
                    else:
                        phase_to_use = bus_df['phases']

                if allocation_kv is None:
                    bus_kv = bus_df.kv_base
                else:
                    bus_kv = allocation_kv

                # TODO handle kvar
                # TODO handle cutin/cutout differently...
                # TODO handle equal phase split
                # approach now puts a single phase system on a random phase
                line = f"New pvsystem." \
                    f"{pre_name}{written_lines+1}_{short_bus} "\
                    f"bus1={short_bus}.{phase_to_use} kV={bus_kv} phases={n_phases_to_use} " \
                    f"kva={kva_per_line} pmpp={kva_per_line} " \
                    f"irradiance={irradiance} " \
                    "varfollowinverter=True balanced=False " \
                    "%Cutin=0.1 %Cutout=0.1 " + shape

                # handle optional power factor
                if element_pf is not None:
                    line += f' PF={element_pf}'

                # handle control
                if valid_control:
                    for control_rule in control_dict:
                        if not hasattr(control_dict[control_rule], 'der_list'):
                            control_dict[control_rule].der_list = []
                        control_dict[control_rule].der_list.append(
                            f"{pre_name}{written_lines+1}_{short_bus}"
                        )

                lines.append(line)
                written_lines += 1

                # create redirect every lines_per_step
                if written_lines % next_write == 0:

                    if first_non_zero_lps > 0:
                        step_offset = first_non_zero_lps - 1
                    else:
                        step_offset = 0

                    previous_write = next_write

                    step = lps_index + 1
                    while previous_write == next_write and (step + step_offset <= self.n_steps):
                        # to fix steps with 0 new lines to write
                        lps_index += 1
                        step = lps_index
                        next_write = int(sum(lines_per_step_list[0:(
                            lps_index+1+first_non_zero_lps)]))

                        # update allocations for redirect info line
                        element_allocation.update_allocation_tracking(step + step_offset)
                        allocation_info = f"{element_allocation}"
                        allocation_info = '! ' + allocation_info

                        lines_to_write = lines.copy()
                        lines_to_write.append(allocation_info)

                        if valid_control:
                            # handle pv systems....
                            # TODO reset der list... should happen before ehere...
                            lines_to_write.append("! Inverter Control Update")
                            for control_rule in control_dict:
                                name_string = ''
                                for der in control_dict[control_rule].der_list:
                                    name_string += f"pvsystem.{der} "
                                # append and edit of controlled inverters
                                lines_to_write.append(
                                    f'edit invcontrol.{control_rule} derlist = [{name_string}]')

                        # create step redirect
                        try:
                            self.seed[seed][step+step_offset][element_name] = dreams.Redirect(
                                element_name,
                                lines=lines_to_write
                            )
                        except KeyError:
                            # TODO figure out this issue better.
                            # has to do with zeros at the end of the scenario
                            continue


        if isinstance(element_allocation,
                      dreams.hc.StorageAllocationElement):
            # handle storage allocations
            element_allocation.reset_allocation_tracking()

            kva_per_line = element_allocation.get_kva_per_line()
            kwh_per_line = element_allocation.get_kwh_per_line()
            pre_name = element_allocation.element_prepend
            allocation_kv = element_allocation.element_kv
            dispmode = element_allocation.dispmode

            if dispmode != '':
                dispmode = f" dispmode={dispmode}"

            reserve = element_allocation.element_reserve
            stored = element_allocation.element_stored

            lines_per_step_list = lines_per_step 
            lps_index = 0  # line per step
            written_lines = 0
            lines = []

            # this is a little weird - fix for zero allocation in first step
            if lines_per_step_list[0] == 0:
                first_non_zero_lps = next(
                    (i for i, x in enumerate(lines_per_step_list) if x), None)
                next_write = lines_per_step_list[first_non_zero_lps]
            else:
                first_non_zero_lps = 0
                next_write = lines_per_step_list[0]

            for random_index in random_indicies:
                long_bus = possible_buses[random_index]
                short_bus = dreams.dss.get_short_bus_name(long_bus)
                bus_df = self.feeder.buses.loc[short_bus]

                if allocation_kv is None:
                    bus_kv = bus_df.kv_base
                else:
                    bus_kv = allocation_kv

                # put storage on single phase
                # select random phase if more than one
                n_phases = bus_df['n_phases']
                if n_phases > 1:
                    phases = bus_df['phases']
                    # pick random available phase for allocation
                    phase_to_use = np.random.choice(list(phases))
                else:
                    phase_to_use = bus_df['phases']

                # approach now puts a single phase system on a random phase
                line = f"New storage." \
                    f"{pre_name}{written_lines+1}_{short_bus} "\
                    f"bus1={short_bus}.{phase_to_use} kV={bus_kv} phases=1 " \
                    f"kva={kva_per_line} kwrated={kva_per_line} kwhrated={kwh_per_line} " \
                    f"%reserve={reserve} %stored={stored} " \
                    f"kvarmax={kva_per_line*0} kvarmaxabs={kva_per_line*0} " \
                    f"%idlingkw=0 state=idling model=1 balanced=yes " \
                    "chargeTrigger=0.0 dischargeTrigger=0.0 " + shape + dispmode

                # "varfollowinverter=True " \ left out for now...
                # also removed
                # f"dispmode=external wattpriority=true " \
                # set %idlingkw to 0 - lossless.. easier to think about...

                # handle control
                if valid_control:
                    for control_rule in control_dict:
                        if not hasattr(control_dict[control_rule], 'element_list'):
                            control_dict[control_rule].element_list = []
                        control_dict[control_rule].element_list.append(
                            f"{pre_name}{written_lines+1}_{short_bus}"
                        )

                lines.append(line)
                written_lines += 1

                # create redirect every lines_per_step
                if written_lines % next_write == 0:

                    if first_non_zero_lps > 0:
                        step_offset = first_non_zero_lps - 1
                    else:
                        step_offset = 0

                    previous_write = next_write

                    step = lps_index + 1
                    while previous_write == next_write and (step + step_offset <= self.n_steps):
                        lps_index += 1
                        step = lps_index
                        next_write = int(sum(lines_per_step_list[0:(
                            lps_index+1+first_non_zero_lps)]))
                        # update allocations for redirect info line
                        element_allocation.update_allocation_tracking(step + step_offset)
                        allocation_info = f"{element_allocation}"
                        allocation_info = '! ' + allocation_info

                        lines_to_write = lines.copy()
                        lines_to_write.append(allocation_info)

                        if valid_control:
                            # handle storage systems....
                            lines_to_write.append("! Storage Control Update")
                            for control_rule in control_dict:
                                name_string = ''
                                for der in control_dict[control_rule].element_list:
                                    name_string += f"{der} "
                                # append and edit of controlled inverters
                                lines_to_write.append(
                                    f'edit storageController.{control_rule} elementlist = [{name_string}]')

                        # create step redirect
                        try:
                            self.seed[seed][step+step_offset][element_name] = dreams.Redirect(
                                element_name,
                                lines=lines_to_write
                            )
                        except KeyError:
                            # TODO figure out this issue better.
                            # has to do with zeros at the end of the scenario
                            continue

        if isinstance(element_allocation,
                      dreams.hc.WindAllocationElement):
            # handle storage allocations
            element_allocation.reset_allocation_tracking()

            kw_per_line = element_allocation.get_kw_per_line()
            pre_name = element_allocation.element_prepend
            allocation_kv = element_allocation.element_kv
            pf = element_allocation.element_pf

            lines_per_step_list = lines_per_step
            lps_index = 0  # line per step
            written_lines = 0
            lines = []

            # this is a little weird - fix for zero allocation in first step
            if lines_per_step_list[0] == 0:
                first_non_zero_lps = next(
                    (i for i, x in enumerate(lines_per_step_list) if x), None)
                next_write = lines_per_step_list[first_non_zero_lps]
            else:
                first_non_zero_lps = 0
                next_write = lines_per_step_list[0]

            for random_index in random_indicies:
                long_bus = possible_buses[random_index]
                short_bus = dreams.dss.get_short_bus_name(long_bus)
                bus_df = self.feeder.buses.loc[short_bus]

                if element_allocation.match_bus_phase:
                    # match bus phase for system
                    phase_to_use = long_bus.replace(short_bus, '')
                    phase_to_use = phase_to_use[1:]  # remove first period
                    n_phases_to_use = bus_df['n_phases']
                    # print(f"{short_bus}.{phase_to_use} phases={n_phases_to_use}")
                else:
                    n_phases_to_use = 1
                    # select random phase if more than one
                    n_phases = bus_df['n_phases']
                    if n_phases > 1:
                        phases = bus_df['phases']
                        # pick random available phase for allocation
                        phase_to_use = np.random.choice(list(phases))
                    else:
                        phase_to_use = bus_df['phases']

                if allocation_kv is None:
                    bus_kv = bus_df.kv_base
                else:
                    bus_kv = allocation_kv

                # approach now puts a single phase system on a random phase
                # NOTE: windgen not available in most recent dss version...
                # using generator for now
                line = f"New generator."\
                    f"{pre_name}{written_lines+1}_{short_bus} "\
                    f"bus1={short_bus}.{phase_to_use} "\
                    f"phases={n_phases_to_use} " \
                    f"kV={bus_kv} "\
                    f"kw={kw_per_line} " \
                    f"pf={pf} " \
                    "balanced=True " \
                    "model=1 " + shape  # TODO update as required

                # handle control... # TODO remove - control not possible?
                if valid_control:
                    for control_rule in control_dict:
                        if not hasattr(control_dict[control_rule], 'element_list'):
                            control_dict[control_rule].element_list = []
                        control_dict[control_rule].element_list.append(
                            f"{pre_name}{written_lines+1}_{short_bus}"
                        )

                lines.append(line)
                written_lines += 1

                # create redirect every lines_per_step
                if written_lines % next_write == 0:

                    if first_non_zero_lps > 0:
                        step_offset = first_non_zero_lps - 1
                    else:
                        step_offset = 0

                    previous_write = next_write

                    step = lps_index + 1
                    while previous_write == next_write and (step + step_offset <= self.n_steps):
                        lps_index += 1
                        step = lps_index
                        next_write = int(sum(lines_per_step_list[0:(
                            lps_index+1+first_non_zero_lps)]))
                        # update allocations for redirect info line
                        element_allocation.update_allocation_tracking(step + step_offset)
                        allocation_info = f"{element_allocation}"
                        allocation_info = '! ' + allocation_info

                        lines_to_write = lines.copy()
                        lines_to_write.append(allocation_info)

                        if valid_control:
                            # do wtg have control?
                            # handle storage systems....
                            print('Control of WindAllocation Ignored...')

                        # create step redirect
                        try:
                            self.seed[seed][step+step_offset][element_name] = dreams.Redirect(
                                element_name,
                                lines=lines_to_write
                            )
                        except KeyError:
                            # TODO figure out this issue better.
                            # has to do with zeros at the end of the scenario
                            continue

    def write_steps(
            self,
            output_folder=None
            ):
        """write all scenario seed step redirects (etc) as dss files"""
        if self.steps_created is False:
            self.create_simulation_seeds()

        if output_folder is None:
            output_folder = self.base_path

        # for base redirects:
        for base_redirect in self.base_redirects:
            output_location = os.path.join(
                self.path_to_base_redirects,
                self.name)
            if not os.path.isdir(output_location):
                os.makedirs(
                    output_location,
                    exist_ok=True,
                    )
            base_redirect.write(output_location=output_location)

        # for control redirects
        # NOTE: this will require update when control redirects are different
        # for each step (i.e. der list defined)
        for control_redirect_name in self.control_redirects:
            output_location = os.path.join(
                self.control_redirect_path,
                self.name)

            if not os.path.isdir(output_location):
                os.makedirs(
                    output_location,
                    exist_ok=True,
                    )
            item = self.control_redirects[control_redirect_name]
            item['redirect'].write(output_location=output_location)

        # for each seed
        for seed, steps in self.seed.items():
            # for each step
            for step, redirects in steps.items():
                # for each redirect
                for _, redirect in redirects.items():
                    # create path for redirect based on id
                    export_path = os.path.join(
                        output_folder,
                        str(seed).zfill(5),
                        str(step).zfill(3))

                    # ensure output path exists
                    if not os.path.isdir(export_path):
                        os.makedirs(
                            export_path,
                            exist_ok=True,
                            )
                    redirect_location = os.path.join(export_path)
                    # export redirect
                    redirect.write(output_location=redirect_location)

        # collect and write meta data
        df = self.collect_meta_data()
        meta_fp = os.path.join(output_folder, 'scenario_meta_data.csv')
        df.to_csv(meta_fp)

    def run(
            self,
            export_results=None
            ):
        """
        Run all steps for all scenario seeds and steps
        Optionally export results based on export_results value

        Will automatically select proper simulation routine based on scenario
        definition of duration
        """
        if not self.steps_created:
            # required pre-simulation run
            self.create_simulation_seeds()

        # select correct simulation mode
        if self.duration_seconds == 0:
            self._run_snapshot(export_results)
        else:
            self._run_qsts(export_results)

    def _run_snapshot(self, export_results):
        """
        Simulation routine for running snapshot simulations
        """
        print('Started Snapshot Simulation')
        # progress though each simulation seed
        for seed, steps in self.seed.items():
            # create dictionary for results
            self.step_results[seed] = {}
            self.seed_results[seed] = {}

            self.reset_allocations()

            # progress through each step
            for step, redirects in steps.items():
                # restart feeder
                self.feeder.restart()
                # run base redirects
                self.execute_base_redirects()
                # run step redirects
                for _, redirect in redirects.items():
                    redirect.execute()

                # handle control redirects
                self.execute_control_redirects(step)

                # solve system
                # TODO: Handle non convergence
                self.feeder.solve()  # different solve for HC?

                # update python object system
                self.update_allocations(step)
                self.feeder.update_capacity()
                self.feeder.update_bus_voltages()

                # Collect step results
                self.step_results[seed][step] = dreams.hc.SnapshotStepResult(
                    self,
                    seed,
                    step,
                    detail_level=1  # TODO handle with scenario paramerter?
                )

            print(f'Completed seed: {seed}')
            # aggregate seed results
            self.seed_results[seed] = dreams.hc.SnapshotSeedResult(
                self,
                seed,
                self.step_results[seed]
            )

        print('Finished all Seeds')
        # aggregate scenario results
        self.results = dreams.hc.SnapshotScenarioResult(self)

        # TODO condsider result export

    def _run_qsts(self, export_results):
        """
        Simulation routine for running quasi-static time series simulations
        """
        print('Started QSTS Simulation')
        # function aliase due to long name.
        collect_extremes = dreams.dss.gen_min_max_ave_voltages_and_capacity

        # variables for better non-convergence reporting
        qsts_solution_report = {
            'total_qsts_steps': 0,
            'nc_qsts_steps': 0,
            'steps_with_nc': []
        }

        # progress though each simulation seed
        for seed, steps in self.seed.items():
            print(f"\rStarted Simulation Seed {seed}")
            # create dictionary for results
            self.step_results[seed] = {}
            self.seed_results[seed] = {}

            self.reset_allocations()

            # progress through each step
            for step, redirects in steps.items():
                print(f"\rStarted Simulation Step {step}")
                # restart feeder
                self.feeder.restart()

                # run redirects
                self.execute_control_redirects(step)
                self.execute_base_redirects()
                # run step redirects
                for _, redirect in redirects.items():
                    redirect.execute()

                # originally before control redirects.
                # execute QSTS initialize commands.
                self.init_qsts()

                # add monitors to system
                dreams.monitor.add_monitors_to_feeder(self.feeder)

                # solve system - use loop approach
                system_statistics = {}
                violations = {}
                if self.collect_bus_v:
                    bus_voltages = {}
                else:
                    bus_voltages = None

                step_append = ''
                for qsts_step in list(range(0, self.n_qsts_steps + 1, 1)):
                    print(f"\rQSTS Step {qsts_step}/{self.n_qsts_steps + 1}  ({qsts_step/(self.n_qsts_steps + 1) * 100:.2f}% complete)  ", end='', flush=True)
                    dreams.dss.reset_relays()
                    converged = self.feeder.solve()

                    qsts_solution_report['total_qsts_steps'] += 1

                    if not converged:
                        qsts_solution_report['nc_qsts_steps'] += 1
                        if step not in qsts_solution_report['steps_with_nc']:
                            qsts_solution_report['steps_with_nc'].append(step)
                            step_append = '*'
                            print('Warning: Solution did not converge!')

                    system_statistics[qsts_step] = collect_extremes()
                    system_statistics[qsts_step]['converged'] = converged
                    violations[qsts_step] = self.feeder.id_violations()

                    if self.collect_bus_v:
                        bus_voltages[qsts_step] = dreams.dss.get_bus_voltage_df()

                print(f"\rQSTS Step {qsts_step+1}/{self.n_qsts_steps + 1}  ({(qsts_step+1)/(self.n_qsts_steps + 1) * 100:.2f}% complete)  ")

                # update python object system
                self.update_allocations(step)

                # Collect step results
                self.step_results[seed][step] = dreams.hc.QSTSStepResult(
                    self,
                    seed,
                    step,
                    system_statistics=system_statistics,
                    violations=violations,
                    bus_voltages=bus_voltages
                    )

                # if step == 0:
                # print(f'Completed Step: {step}{step_append}', end='')
                # else:
                #     print(f', {step}{step_append}', end='')

            print(f'\nCompleted Seed: {seed}')
            # aggregate seed results
            self.seed_results[seed] = dreams.hc.QSTSSeedResult(
                self,
                seed,
                self.step_results[seed]
            )
            # print non convegence
            if qsts_solution_report['nc_qsts_steps'] > 0:
                print(
                    f"{qsts_solution_report['nc_qsts_steps']}/"
                    f"{qsts_solution_report['total_qsts_steps']} "
                    f"total qsts steps did not converge.\n"
                    f"Non-convergence in steps {qsts_solution_report['steps_with_nc']}")

        print('Finished all Seeds')
        # aggregate scenario results
        self.results = dreams.hc.QSTSScenarioResult(self)

        # TODO consider result export

    def init_qsts(self, qsts_step=0):
        """
        Execute commands required for QSTS initialzation
        Allows for going to a specific qsts step via input
        """
        self.feeder.solve(set_mode=True)

        hour_minus_step = 3600 - self.qsts_step_size_sec

        qsts_step = qsts_step * self.qsts_step_size_sec
        total_step_offset = hour_minus_step + qsts_step

        initialize_commnads = [
            'set miniterations = 1',  # QSTS Speed up
            f'set maxiterations = {self.max_iterations}',
            f'set maxcontroliter = {self.max_control_iterations}',  # added 12/14/23
            'set sampleenergymeters=no',  # QSTS Speed up - maybe.
            f'set mode={self.qsts_profile}',
            f'set stepsize={self.qsts_step_size_sec}s',
            'set number=1',  # for running as a loop
            f'set controlmode={self.control_mode}',
            f'set time=({self.qsts_hour_offset-1},{total_step_offset})',
            # above line to fix offset
            ]

        for cmd in initialize_commnads:
            dreams.dss.cmd(cmd)

    def reset_allocations(self):
        """
        reset tracking of element allocations
        """
        for allocation in self.allocations:
            for _, element_allocation in allocation.rules['element'].items():
                element_allocation.reset_allocation_tracking()

    def update_allocations(self, step):
        """
        update tracking of element allocations
        """
        for allocation in self.allocations:
            for _, element_allocation in allocation.rules['element'].items():
                element_allocation.update_allocation_tracking(step)

    def collect_meta_data(self):
        """
        Return dataframe of scenario meta data
        """
        params = [
            'name',
            'duration_seconds',
            'n_steps',
            'n_simulations',
            'max_iterations',
            'max_control_iterations',
            'qsts_profile',
            'qsts_hour_offset',
            'qsts_step_size_sec',
            'qsts_origin',
            'control_mode',
            'seed',
            'minimize_duplicates',
            'step_labels',
            'step_title',
            'base_path',
            'path_to_base_redirects',
            'feeder'
        ]

        param_dict = {}
        for param in params:
            param_dict[param] = getattr(self, param)
            if param == 'seed':
                param_dict[param] = list(param_dict[param])[0]
            if param == 'feeder':
                param_dict[param] = param_dict[param].path

        param_df = pd.DataFrame.from_dict(param_dict, orient='index')
        param_df.index.rename('parameter_name', inplace=True)
        param_df.rename(columns={0: 'parameter_value'}, inplace=True)

        return param_df

    def go_to_step(
            self,
            seed=None,
            step: int = None,
            qsts_step: int = None,
            account_for_storage: bool = False,
            update_feeder: bool = True) -> None:
        """
        Load feeder state associated with given seed, step, and qsts step.
        Update feeder to reflect new step by default.

        If any seed, step, or qsts_step are not provided, first is assumed.

        qsts_step advances qsts time by multiples of defined scenario
        qsts_step_size_sec.
        """
        # check for created steps
        if not self.steps_created:
            # write steps
            print('making seeds.')
            self.create_simulation_seeds()

        # check if seed exists
        if seed is None:
            seed = self.all_seeds[0]
        else:
            if seed not in self.all_seeds:
                return f"Seed '{seed}' invalid"

        # check if step exists
        if step is None:
            # choose first step
            step = list(self.seed[seed].keys())[0]
        else:
            if step not in list(self.seed[seed].keys()):
                return f"Step '{step}' invalid"

        # restart feeder and allocations
        self.reset_allocations()
        self.feeder.restart()

        # run redirects
        self.execute_control_redirects(step)
        self.execute_base_redirects()

        # run step redirects
        for _, redirect in self.seed[seed][step].items():
            redirect.execute()

        # if qsts
        if qsts_step is None and self.qsts_step_size_sec > 0:
            self.init_qsts()
        elif isinstance(qsts_step, int) and self.qsts_step_size_sec > 0:
            # account for storage
            if not account_for_storage:
                self.init_qsts(qsts_step=qsts_step)
            else:
                self.init_qsts()
                current_step = 0
                while current_step < qsts_step:
                    self.feeder.solve()
                    print(f"solved qsts step {current_step}")
                    current_step += 1

        # add monitors to system
        dreams.monitor.add_monitors_to_feeder(self.feeder)
        # newly added 20231128 as test
        system_statistics = {}
        violations = {}
        self.step_results[seed] = {}
        self.seed_results[seed] = {}

        # solve system
        # TODO: Handle non convergence
        converged = self.feeder.solve()  # different solve for HC?
        collect_extremes = dreams.dss.gen_min_max_ave_voltages_and_capacity
        system_statistics[qsts_step] = collect_extremes()
        system_statistics[qsts_step]['converged'] = converged

        violations[qsts_step] = self.feeder.id_violations()

        self.update_allocations(step)  # Collect step results
        self.step_results[seed][step] = dreams.hc.QSTSStepResult(
            self,
            seed,
            step,
            system_statistics=system_statistics,
            violations=violations
            )
        # update python object system
        if update_feeder:
            self.feeder.update()
