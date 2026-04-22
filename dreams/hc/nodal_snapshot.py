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
            ):

        self.feeder = feeder
        self.effective_max_kw = effective_max_kw
        self.bus_names = bus_names
        self.constraint = constraint
        self.execution_time = 0.0
        self.threshold = threshold
        self.hc_kind = hc_kind
        self.name = name

        self.capacity_limit = capacity_limit
        self.over_voltage_limit = over_voltage_limit
        self.under_voltage_limit = under_voltage_limit

        if run:
            self.result_df = self.run()
        else:
            self.result_df = None

    def has_voltage_violation(self):
        violations = dreams.dss.check_violations(
            self.capacity_limit,
            self.over_voltage_limit,
            self.under_voltage_limit
            )
        over_voltage = violations['over_voltage']
        under_voltage = violations['under_voltage']
        return over_voltage or under_voltage

    def has_thermal_violation(self):
        violations = dreams.dss.check_violations(
            self.capacity_limit,
            self.over_voltage_limit,
            self.under_voltage_limit
            )
        line_overload = violations['line_overload']
        xfmr_overload = violations['xfmr_overload']
        return line_overload or xfmr_overload

    def run(self):
        """"
        execute nodal hosting capacity, return results and store to self.
        does sort of a mix between certain scaling and midpoint reductions.
        """
        start_time = time.process_time()
        scale_increase = 2

        # handle select or no buses...
        if self.bus_names is None:
            buses_to_test = self.feeder.buses.copy()
        else:
            buses_to_test = self.feeder.buses.loc[self.bus_names].copy()

        # handle constraints...
        if self.constraint is None:
            self.constraint = 'voltage'

        constraint = self.constraint

        valid_constraints = ['voltage', 'thermal']
        if constraint not in valid_constraints:
            print(f"ERROR: constraint '{constraint}' not valid")

        total_buses = len(buses_to_test)
        print(f"Started {constraint} constrained hosting capacity")

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

            dreams.dss.cmd('solve')

            # get bus distance
            dss.Circuit.SetActiveBus(bus_name)
            bus_dist = dss.Bus.Distance()

            last_violations = dreams.dss.check_violations()

            if constraint == 'voltage':
                violation_flag = self.has_voltage_violation()
            else:
                violation_flag = self.has_thermal_violation()

            # handle case of small load causing violations
            if violation_flag:
                non_vhc_kw = 0
                vhc_kw = 0
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

                dreams.dss.cmd('solve')
                n += 1

                last_violations = dreams.dss.check_violations()

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

                dreams.dss.cmd('solve')
                n += 1

                violations = dreams.dss.check_violations()

                if constraint == 'voltage':
                    violation_flag = self.has_voltage_violation()
                else:
                    violation_flag = self.has_thermal_violation()

                if violation_flag:
                    vhc_kw = mid_point
                    last_violations = violations
                else:
                    non_vhc_kw = mid_point

            res[bus_name] = {}
            res[bus_name][f'{constraint}_hc_kw'] = round(non_vhc_kw)
            res[bus_name]['iterations'] = n
            res[bus_name].update(last_violations)
            res[bus_name]['bus_dist_km'] = bus_dist
            bus_n += 1

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
        else:
            print("Valid kind: 'hc', 'iter' ")

    def _plot_hc(
        self,
        ax=None,
        sortby='dist',
        **kwargs
        ):

        fig = plt.figure()
        if ax is None:
            ax = plt.gca()

        results = self.result_df

        hc_kind = self.hc_kind
        constraint = self.constraint

        col = f'{constraint}_hc_kw'
        
        # by value
        if sortby == 'dist':
            result_ax = results.sort_values(['bus_dist_km'])[col].reset_index().plot(
                grid=True,
                ax=ax,
                linestyle='',
                marker='o'
                )
            result_ax.set_xlabel('Distance from Substation [km]')

        else:
            result_ax = results.sort_values(col)[col].reset_index().plot(
                grid=True,
                ax=ax,
                linestyle='',
                marker='o'
                )
            result_ax.set_xlabel('Bus Count')

        result_ax.set_ylabel('Hosting Capacity [kW]')
        result_ax.set_title(f'{constraint.capitalize()} Hosting Capacity\n{hc_kind.upper()} ')
        return result_ax

    def _plot_iterations(
        self,
        ax=None,
        **kwargs
        ):
        fig = plt.figure()
        if ax is None:
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
