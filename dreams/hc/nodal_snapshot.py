"""
functions to perform nodal hosting capacity in a snapshot fasion
"""
import dreams
import pandas as pd
import matplotlib.pyplot as plt
import opendssdirect as dss
import time


class NodalSnapshot():
    """
    class to perform nodal hosting capacity
    designed specifically for medium voltage select buses.

    """

    def __init__(
            self,
            feeder,
            effective_max_kw=100e3,  # 100 MW max
            run=True,
            bus_names=None,
            constraint=None,
            threshold=1,  # kw for convergence
            hc_kind='load',
            name="",
            capacity_limit=100,
            over_voltage_limit=1.05,
            under_voltage_limit=0.95,
            adaptive_violations=False,
            voltage_buffer=0.03, # VPU
            thermal_buffer=5, # capacity percent
            mode=None,
            at_sec=None,
            save_violations=False,
            ):

        self.feeder = feeder
        self.effective_max_kw = effective_max_kw
        self.bus_names = bus_names
        self.constraint = constraint
        self.execution_time = 0.0
        self.threshold = threshold

        # ensure one or the other always
        if hc_kind != 'load':
            hc_kind = 'gen'

        self.hc_kind = hc_kind
        self.name = name

        self.capacity_limit = capacity_limit
        self.over_voltage_limit = over_voltage_limit
        self.under_voltage_limit = under_voltage_limit

        self.mode = mode
        self.at_sec = at_sec
        self.save_violations=save_violations

        # adaptive violation paramaters
        self.adaptive_violations = adaptive_violations
        self.voltage_buffer = voltage_buffer
        self.thermal_buffer = thermal_buffer
        self.violating_buses = None
        self.violating_thermal_elements = None

        if save_violations:
            self.violations = {}

        if run:
            self.result_df = self.run()
        else:
            self.result_df = None

    def solve(self):
        if self.mode is not None:
            # handle setting of mode
            dreams.dss.cmd(f'set mode={self.mode}')

        if self.at_sec is not None:
            # handle setting of time
            dreams.dss.cmd('set number=1')
            dreams.dss.cmd('set stepsize=1')
            dreams.dss.cmd('set hour=0')
            dreams.dss.cmd('set min=0')
            dreams.dss.cmd(f'set sec={int(self.at_sec)}')

        dreams.dss.cmd('solve')

    def id_existing_bus_violations(self):
        """
        Identify existing bus voltage violations for adaptive violations

        creates dataframe of violating buses and attaches to self
        """
        # identify violations
        voltage_cols = ['v1', 'v2', 'v3']
        vdf = dreams.dss.get_bus_voltage_df()

        # check for under voltage
        uv_mask = vdf[voltage_cols] < self.under_voltage_limit
        uv_mask = uv_mask.sum(axis=1) > 0

        # generation hc - check for over voltage
        ov_mask = vdf[voltage_cols] > self.over_voltage_limit
        ov_mask = ov_mask.sum(axis=1) > 0

        violating_buses = {}

        # create look up for later checks with old and new voltages
        if sum(ov_mask) > 0:
            # has over voltages
            for bus_name, bus_row in vdf[ov_mask].iterrows():
                violating_buses[bus_name] = {}
                violating_buses[bus_name]['original_v'] = bus_row[voltage_cols].max()
                violating_buses[bus_name]['new_threshold'] = bus_row[voltage_cols].max() + self.voltage_buffer
                violating_buses[bus_name]['v_kind'] = 'over_voltage'

        if sum(uv_mask) > 0:
            # has under voltages
            for bus_name, bus_row in vdf[uv_mask].iterrows():
                violating_buses[bus_name] = {}
                violating_buses[bus_name]['original_v'] = bus_row[voltage_cols].min()
                violating_buses[bus_name]['new_threshold'] = bus_row[voltage_cols].min() - self.voltage_buffer
                violating_buses[bus_name]['v_kind'] = 'under_voltage'

        violating_buses_df = pd.DataFrame.from_dict(violating_buses, orient='index')
        self.violating_buses = violating_buses_df


    def id_existing_thermal_violations(self):
        # identify existing thermal violations
        capacity = dreams.dss.get_capacity_df()
        capacity.set_index('longname', inplace=True)
        oc_mask = capacity[r'%normal'] > self.capacity_limit

        # creat look up for later checks
        violating_elements = {}
        for long_name, cap_row in capacity[oc_mask].iterrows():
            violating_elements[long_name] = {}
            violating_elements[long_name]['original_capacity'] = cap_row['%normal']
            violating_elements[long_name]['new_threshold'] = cap_row['%normal'] + self.thermal_buffer

        violating_elements_df = pd.DataFrame.from_dict(violating_elements, orient='index')
        self.violating_thermal_elements = violating_elements_df


    def check_adaptive_bus_violations(self):
        # check bus voltages excluding known violation
        voltage_cols = ['v1', 'v2', 'v3']
        vdf = dreams.dss.get_bus_voltage_df()

        # NOTE: this could lead to a situation where a previously violating
        # bus could be missed in the 'opposite' type of violation...
        known_v_mask = vdf.index.isin(self.violating_buses.index)      
        std_v_mask = ~known_v_mask

        over_voltages = vdf[std_v_mask][voltage_cols] > self.over_voltage_limit
        under_voltages = vdf[std_v_mask][voltage_cols] < self.under_voltage_limit

        has_ov = over_voltages.sum().sum() > 0
        has_uv = under_voltages.sum().sum() > 0

        if has_ov or has_uv:
            # valid violations identified
            # probably return true or something
            return True

        # check known violating buses
        has_vio = False
        for bus_name, bus_row in self.violating_buses.iterrows():
            v_row = vdf.loc[[bus_name]]

            # check known violating buses
            if bus_row['v_kind'] == 'over_voltage':
                has_vio = (v_row[voltage_cols] > bus_row['new_threshold']).sum().sum() > 0
            else:
                # under voltage
                has_vio = (v_row[voltage_cols] < bus_row['new_threshold']).sum().sum() > 0

            if has_vio:
                return has_vio

        return has_vio


    def check_adapative_thermal_violations(self):
        # check normally non-violating system
        capacity = dreams.dss.get_capacity_df()
        capacity.set_index('longname', inplace=True)

        known_v_mask = capacity.index.isin(self.violating_thermal_elements.index)      
        std_v_mask = ~known_v_mask

        over_capacity_mask = capacity[std_v_mask][r'%normal'] > self.capacity_limit
        if sum(over_capacity_mask) > 0:
            return True

        # check adaptive violation elements
        has_vio = False
        for long_name, element_row in self.violating_thermal_elements.iterrows():
            cap_row = capacity.loc[[long_name]]

            if sum(cap_row[r'%normal'] > element_row['new_threshold']) > 0:
                return True

        return has_vio


    def has_voltage_violation(self):
        if self.adaptive_violations and (self.violating_buses is not None):
            return self.check_adaptive_bus_violations()

        else:
            violations = dreams.dss.check_violations(
                self.capacity_limit,
                self.over_voltage_limit,
                self.under_voltage_limit
                )
            over_voltage = violations['over_voltage']
            under_voltage = violations['under_voltage']
            return over_voltage or under_voltage

    def has_thermal_violation(self):
        if self.adaptive_violations and (self.violating_thermal_elements is not None):
            return self.check_adapative_thermal_violations()

        else:
            violations = dreams.dss.check_violations(
                self.capacity_limit,
                self.over_voltage_limit,
                self.under_voltage_limit
                )
            line_overload = violations['line_overload']
            # accomodate for no xfmr model
            if 'xfmr_overload' in violations:
                xfmr_overload = violations['xfmr_overload']
            else:
                xfmr_overload = False
            return line_overload or xfmr_overload

    def run(self):
        """"
        execute nodal hosting capacity, return results and store to self.
        """
        start_time = time.process_time()
        scale_increase = 2

        # handle select or no buses...
        if self.bus_names is None:
            buses_to_test = self.feeder.buses.copy()
        else:
            buses_to_test = self.feeder.buses.loc[self.bus_names].copy()

        # handle constraints.
        if self.constraint is None:
            self.constraint = 'voltage'

        constraint = self.constraint

        valid_constraints = ['voltage', 'thermal']
        if constraint not in valid_constraints:
            print(f"ERROR: constraint '{constraint}' not valid")

        total_buses = len(buses_to_test)
        print(f"Started {constraint} constrained {self.hc_kind} hosting capacity")

        effective_max_kw = self.effective_max_kw
        res = {}
        bus_n = 0
        for bus_name, bus_row in buses_to_test.iterrows():
            print(f"\rBus {bus_n}/{total_buses}  ({bus_n/(total_buses) * 100:.2f}% complete)  ", end='', flush=True)

            self.feeder.restart()
            long_bus = bus_name + "." + ".".join(bus_row['phases'])
            n_phases = bus_row['n_phases']
            # handle line kv
            if n_phases > 1:
                scaled_kv = bus_row['kv_base'] * 3**(1/2)
            else:
                scaled_kv = bus_row['kv_base']

            # add small asset for lower bound
            if self.hc_kind == 'load':
                non_vhc_kw = 0.06
                load_line = f"New load.hc_{bus_name} " \
                    f"bus1={long_bus} kV={scaled_kv} phases={n_phases} "\
                    f"Vmaxpu=2 Vminpu=0.7 conn=wye "\
                    f"kW={non_vhc_kw} kvar=0"
                dreams.dss.cmd(load_line)
            else:
                non_vhc_kw = 0.1
                pv_line = f"new pvsystem.hc_{bus_name} " \
                    f"bus1={long_bus} kv={scaled_kv} phases={n_phases} "\
                    f"kva={non_vhc_kw} pmpp={non_vhc_kw} conn=wye model=1 "\
                    f"irradiance=1 vmaxpu=2 vminpu=0.1 %r=0.0 balanced=yes"
                dreams.dss.cmd(pv_line)

            self.solve()

            # get bus distance
            dss.Circuit.SetActiveBus(bus_name)
            bus_dist = dss.Bus.Distance()

            last_violations = dreams.dss.check_violations()

            if constraint == 'voltage':
                violation_flag = self.has_voltage_violation()
            else:
                violation_flag = self.has_thermal_violation()

            # handle case of small load causing violations
            if violation_flag and (not self.adaptive_violations):
                non_vhc_kw = 0
                vhc_kw = 0
                if self.save_violations:
                    last_id_violations = self.feeder.id_violations()

            elif violation_flag and self.adaptive_violations:
                # identify violating element(s) on first run.
                if self.constraint == 'voltage':
                    self.id_existing_bus_violations()
                else:
                    self.id_existing_thermal_violations()

                # reset flag and set first violating hc value
                violation_flag = False
                vhc_kw = effective_max_kw / scale_increase

            else:
                # set first expected violation value
                vhc_kw = effective_max_kw / scale_increase

            n = 1  # to account for first solution
            # find upper limit
            while (not violation_flag) and (vhc_kw > 0):
                # handle limit
                if non_vhc_kw >= effective_max_kw:
                    non_vhc_kw = effective_max_kw
                    last_violations = dreams.dss.check_violations()
                    break

                # modify asset
                if self.hc_kind == 'load':
                    load_line = f"edit load.hc_{bus_name} kW={vhc_kw}"
                    dreams.dss.cmd(load_line)
                else:
                    pv_line = f"edit pvsystem.hc_{bus_name} kva={vhc_kw}"
                    dreams.dss.cmd(pv_line)
                    pv_line = f"edit pvsystem.hc_{bus_name} pmpp={vhc_kw}"
                    dreams.dss.cmd(pv_line)
                    break

                self.solve()

                n += 1

                last_violations = dreams.dss.check_violations()
                if self.save_violations:
                    last_id_violations = self.feeder.id_violations()

                if constraint == 'voltage':
                    violation_flag = self.has_voltage_violation()
                else:
                    violation_flag = self.has_thermal_violation()

                if not violation_flag:
                    # found no violations hc
                    # non_vhc_kw update
                    # increase demand, update lower bound
                    non_vhc_kw = vhc_kw
                    vhc_kw *= scale_increase

            # oscillate until threshold met
            while abs(non_vhc_kw - vhc_kw) > self.threshold:
                if non_vhc_kw >= effective_max_kw:
                    non_vhc_kw = effective_max_kw
                    last_violations = dreams.dss.check_violations()
                    break

                mid_point = (non_vhc_kw + vhc_kw) / 2

                # set asset to mid point value
                if self.hc_kind == 'load':
                    load_line = f"edit load.hc_{bus_name} kW={mid_point}"
                    dreams.dss.cmd(load_line)
                else:
                    pv_line = f"edit pvsystem.hc_{bus_name} kva={mid_point}"
                    dreams.dss.cmd(pv_line)
                    pv_line = f"edit pvsystem.hc_{bus_name} pmpp={mid_point}"
                    dreams.dss.cmd(pv_line)

                self.solve()
                n += 1

                violations = dreams.dss.check_violations()

                if constraint == 'voltage':
                    violation_flag = self.has_voltage_violation()
                else:
                    violation_flag = self.has_thermal_violation()

                if violation_flag:
                    vhc_kw = mid_point
                    last_violations = violations
                    if self.save_violations:
                        last_id_violations = self.feeder.id_violations()
                else:
                    non_vhc_kw = mid_point

            res[bus_name] = {}
            res[bus_name][f'{constraint}_hc_kw'] = round(non_vhc_kw)
            res[bus_name]['iterations'] = n
            res[bus_name].update(last_violations)
            res[bus_name]['bus_dist_km'] = bus_dist
            bus_n += 1

            if self.save_violations:
                try:
                    self.violations[bus_name] = last_id_violations
                except UnboundLocalError:
                    # to handle case of max limit
                    self.violations[bus_name] = None

        nodal_results = pd.DataFrame.from_dict(res, orient='index')

        end_time = time.process_time()
        self.execution_time = end_time - start_time
        print(f"\rBus {bus_n}/{total_buses}  ({bus_n/(total_buses) * 100:.2f}% complete in {self.execution_time:.2f} seconds)  ")

        return nodal_results

    def plot(self, kind='hc', **kwargs):
        """
        plot redirect function for basic plots
        """
        if kind == 'hc':
            return self._plot_hc(**kwargs)
        elif kind == 'iter':
            return self._plot_iterations(**kwargs)
        elif kind == 'violation':
            return self._plot_violations(**kwargs)
        else:
            print("Valid kind: 'hc', 'iter', 'violation' ")

    def _plot_hc(
        self,
        ax=None,
        sort=False,
        y_min=None,
        **kwargs
        ):
        """
        Plot hosting capacity values, optionally sort by value
        """
        if ax is None:
            fig = plt.figure()
            ax = plt.gca()

        results = self.result_df

        hc_kind = self.hc_kind
        constraint = self.constraint

        col = f'{constraint}_hc_kw'
        
        if sort:
            results.sort_values(col, ascending=False)[col].reset_index().plot(
                grid=True,
                ax=ax,
                linestyle='',
                marker='o',
                )
            ax.set_xlabel('Bus Count')
        else:
            ax.scatter(
                x=results['bus_dist_km'],
                y=results[col],
                # linestyle='',
                marker='o',
                label=col,
                )
            ax.set_xlabel('Distance from Substation [km]')

        ax.set_ylabel('Hosting Capacity [kW]')
        ax.set_title(f'{constraint.capitalize()} Hosting Capacity\n{hc_kind.upper()} ')

        ax.grid(True)
        ax.set_axisbelow(True)
        ax.legend()

        if y_min is not None:
            ylims = ax.get_ylim()
            ax.set_ylim([y_min, ylims[1]])

        return ax

    def _plot_iterations(
        self,
        ax=None,
        **kwargs
        ):
        if ax is None:
            fig = plt.figure()
            ax = plt.gca()

        results = self.result_df
        col = 'iterations'
        result_ax = results.sort_values(col)[col].reset_index().plot(
            grid=True,
            ax=ax,
            )
        result_ax.set_ylabel('Required Solution Iterations')
        result_ax.set_xlabel('Bus Count')
        result_ax.set_title('Nodal Hosting Capacity Iterations')
        return result_ax

    def _plot_violations(
            self,
            ax=None,
            y_min=None,
            **kwargs,
        ):
        """
        plot hosting capacity sorted by distance with violation color coding
        """
        if ax is None:
            fig = plt.figure()
            ax = plt.gca()

        res = self.result_df
        constraint = self.constraint

        if constraint[0] == 't':
            full_type = 'thermal'
            xfmr_mask = res['xfmr_overload'] & ~res['line_overload']
            line_mask = ~res['xfmr_overload'] & res['line_overload']
            both_mask = res['xfmr_overload'] & res['line_overload']

            # handle line / xfmr
            # handle over/under voltage
            if sum(xfmr_mask) > 0:
                ax.scatter(
                    x=res[xfmr_mask]['bus_dist_km'],
                    y=res[xfmr_mask][f'{full_type}_hc_kw'],
                    color='green',
                    alpha=0.666,
                    label=f"{constraint.capitalize()} Constrained - Transformer",
                )
            if sum(line_mask) > 0:
                ax.scatter(
                    x=res[line_mask]['bus_dist_km'],
                    y=res[line_mask][f'{full_type}_hc_kw'],
                    color='grey',
                    alpha=0.666,
                    label=f"{constraint.capitalize()} Constrained - Line",
                )
            if sum(both_mask) > 0:
                ax.scatter(
                    x=res[both_mask]['bus_dist_km'],
                    y=res[both_mask][f'{full_type}_hc_kw'],
                    color='red',
                    alpha=0.666,
                    label=f"{constraint.capitalize()} Constrained - Both",
                )
        else:
            full_type = 'voltage'
            ov_mask = res['over_voltage']
            uv_mask = res['under_voltage']

            # handle over/under voltage
            if sum(ov_mask) > 0:
                ax.scatter(
                    x=res[ov_mask]['bus_dist_km'],
                    y=res[ov_mask][f'{full_type}_hc_kw'],
                    color='magenta',
                    alpha=0.666,
                    label=f"{constraint.capitalize()} Constrained - Over Voltage",
                )
            if sum(uv_mask) > 0:
                ax.scatter(
                    x=res[uv_mask]['bus_dist_km'],
                    y=res[uv_mask][f'{full_type}_hc_kw'],
                    color='cyan',
                    alpha=0.666,
                    label=f"{constraint.capitalize()} Constrained - Under Voltage",
                )

        ax.set_ylabel("Hosting Capacity [kw]")
        ax.set_xlabel("Distance from Substation [km]")
        ax.grid(True)
        ax.set_axisbelow(True)
        ax.legend()

        if y_min is not None:
            ylims = ax.get_ylim()
            ax.set_ylim([y_min, ylims[1]])

        return ax
