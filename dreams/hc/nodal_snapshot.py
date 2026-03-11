"""
functions to perform nodal hosting capacity in a snapshot fasion
"""
import dreams
import pandas as pd
import matplotlib.pyplot as plt
import time

class NodalSnapshot():
    """
    class to perform nodal hosting capacity and save/plot results

    TODO:  option for pf, load or gen, qsts run, voltage, thermal, any,
    """

    def __init__(
            self,
            feeder,
            effective_max_kw=100e3,  # 100 MW max
            run=True,
            selection=None
            ):

        self.feeder = feeder
        self.effective_max_kw = effective_max_kw
        self.selection = selection
        self.execution_time = 0.0

        if run:
            self.result_df = self.run()
        else:
            self.result_df = None

    def run(self):
        """"
        execute nodal hosting capacity, return results and store to self.
        does sort of a mix between certain scaling and midpoint reductions.
        """
        start_time = time.process_time()
        scale_increase = 2

        graph = dreams.Graph(self.feeder)
        upstream_xfmr = graph.get_upstream_xfmr_kva()

        if self.selection is not None:
            upstream_xfmr = upstream_xfmr[:self.selection]

        effective_max = self.effective_max_kw
        res = {}

        for bus_name, bus_row in upstream_xfmr.iterrows():

            self.feeder.restart()
            upstream_xfmr_kva = bus_row['upstream_xfmr_kva']

            long_bus = bus_name + "." + ".".join(bus_row['phases'])

            # handle line kv
            if bus_row['n_phases'] > 1:
                scaled_kv = bus_row['kv_base'] * 3**(1/2)
            else:
                scaled_kv = bus_row['kv_base']

            # add small load for lower bound
            non_vhc_kw = 0.05
            load_line = f"New load.hc_{bus_name} " \
                f"bus1={long_bus} kV={scaled_kv} phases={bus_row['n_phases']} "\
                f"Vmaxpu=2 Vminpu=0.7 conn=wye "\
                f"kW={non_vhc_kw} kvar=0"

            dreams.dss.cmd(load_line)
            dreams.dss.cmd('solve')
            last_violations = dreams.dss.check_violations()
            n_violations = last_violations['n_violation_types']

            # handle case of small load causing violations
            if n_violations > 0:
                non_vhc_kw = 0
                vhc_kw = 0
            else:
                # set first expected violation value
                vhc_kw = upstream_xfmr_kva / scale_increase
                #non_vhc_kw = non_vhc_kw

            n = 1  # to account for first solution
            # find upper limit
            while n_violations == 0 and vhc_kw > 0:
                # handle limit
                if non_vhc_kw >= effective_max:
                    non_vhc_kw = effective_max
                    last_violations = dreams.dss.check_violations()
                    break

                # modify load
                load_line = f"edit load.hc_{bus_name} kW={vhc_kw}"
                dreams.dss.cmd(load_line)
                dreams.dss.cmd('solve')
                n += 1

                last_violations = dreams.dss.check_violations()
                n_violations = last_violations['n_violation_types']

                if n_violations == 0:
                    # found no violations hc
                    # non_vhc_kw update
                    # increase demand, update lower bound
                    non_vhc_kw = vhc_kw
                    vhc_kw *= scale_increase

            # oscillate until threshold met
            while abs(non_vhc_kw - vhc_kw) > 1.0:
                if non_vhc_kw >= effective_max:
                    non_vhc_kw = effective_max
                    last_violations = dreams.dss.check_violations()
                    break

                mid_point = (non_vhc_kw + vhc_kw) / 2
                load_line = f"edit load.hc_{bus_name} kW={mid_point}"

                dreams.dss.cmd(load_line)
                dreams.dss.cmd('solve')
                n += 1

                violations = dreams.dss.check_violations()
                n_violations = violations['n_violation_types']

                if n_violations > 0:
                    vhc_kw = mid_point
                    last_violations = violations
                else:
                    non_vhc_kw = mid_point

            res[bus_name] = {}
            res[bus_name]['hc_kw'] = non_vhc_kw
            res[bus_name]['iterations'] = n
            res[bus_name]['upstream_xfmr_kva'] = upstream_xfmr_kva
            res[bus_name].update(last_violations)

        nodal_results = pd.DataFrame.from_dict(res, orient='index')

        end_time = time.process_time()
        self.execution_time = end_time - start_time

        return nodal_results

    def run_OLD(self):
        """
        Execute nodal hosting capacity, return results.

        NOTE: after corrections, this is no longer the fastest algorithm...
        """
        start_time = time.process_time()

        graph = dreams.Graph(self.feeder)
        upstream_xfmr = graph.get_upstream_xfmr_kva()

        if self.selection is not None:
            upstream_xfmr = upstream_xfmr[:self.selection]

        res = {}
        for bus_name, bus_row in upstream_xfmr.iterrows():
            self.feeder.restart()

            starting_value = int(bus_row['upstream_xfmr_kva'])
            hc_kw_max = starting_value

            increment = max([10, 10**(len(str(starting_value))-1)])
            initial_increment = increment

            effective_max = self.effective_max_kw

            long_bus = bus_name + "." + ".".join(bus_row['phases'])

            # handle line kv conversion
            if bus_row['n_phases'] > 1:
                scaled_kv = bus_row['kv_base'] * 3**(1/2)
            else:
                scaled_kv = bus_row['kv_base']

            n = 0
            while abs(increment) >= 1.0:
                # check for over effective max
                if hc_kw_max > effective_max:
                    hc_kw_max = effective_max
                    last_violations = dreams.dss.check_violations()
                    break

                # create load line, or updated, with expected max hc kw
                if n == 1:
                    load_line = f"New load.hc_{bus_name} " \
                        f"bus1={long_bus} kV={scaled_kv} " \
                        f"phases={bus_row['n_phases']} " \
                        f"Vmaxpu=2 Vminpu=0.7 conn=wye " \
                        f"kW={hc_kw_max} kvar=0"
                else:
                    load_line = f"edit load.hc_{bus_name} kW={hc_kw_max}"

                dreams.dss.cmd(load_line)
                dreams.dss.cmd('solve')
                n += 1

                # after hc load has been updated
                violations = dreams.dss.check_violations()

                if increment > 0:
                    # increasing to achieve violations
                    if violations['n_violation_types'] == 0:
                        # no violations, modify hc kw by increment
                        hc_kw_max += increment
                    else:
                        # has violations, positive increment
                        # change direction and scale of increment
                        increment *= -0.1
                        last_violations = violations
                        continue

                else:
                    # increment is negative
                    # reducing to eliminate violations
                    if violations['n_violation_types'] > 0:
                        # has violations, continue to reduce kw
                        hc_kw_max += increment
                        last_violations = violations
                    else:
                        # increment has reduced past point of violation,
                        # change direction and scale of increment
                        increment *= -0.1
                        continue

            res[bus_name] = {}
            res[bus_name]['hc_kw'] = hc_kw_max
            res[bus_name]['iterations'] = n
            res[bus_name]['first_guess'] = starting_value
            res[bus_name]['starting_increment'] = initial_increment
            res[bus_name].update(last_violations)

        nodal_results = pd.DataFrame.from_dict(res, orient='index')

        end_time = time.process_time()
        self.execution_time = end_time - start_time

        return nodal_results

    def plot(self, kind='hc', **kwargs):
        """
        plot redirect function for basic plots
        """

        if kind == 'hc':
            return self._plot_hc(**kwargs)
        if kind == 'iter':
            return self._plot_iterations(**kwargs)

    def _plot_hc(
        self,
        ax=None,
        **kwargs
        ):
        fig = plt.figure()
        if ax is None:
            ax = plt.gca()

        results = self.result_df
        col = 'hc_kw'
        result_ax = results.sort_values(col)[col].reset_index().plot(
            grid=True,
            ax=ax,
            )
        result_ax.set_ylabel('Hosting Capacity [kW]')
        result_ax.set_xlabel('Bus Count')
        result_ax.set_title('Nodal Hosting Capacity')
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


class NodalSnapshot2():
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
            hc_kind='load'
            ):

        self.feeder = feeder
        self.effective_max_kw = effective_max_kw
        self.bus_names = bus_names
        self.constraint = constraint
        self.execution_time = 0.0
        self.threshold = threshold
        self.hc_kind = hc_kind

        if run:
            self.result_df = self.run()
        else:
            self.result_df = None

    def has_voltage_violation(self):
        violations = dreams.dss.check_violations()
        over_voltage = violations['over_voltage']
        under_voltage = violations['under_voltage']
        return over_voltage or under_voltage

    def has_thermal_violation(self):
        violations = dreams.dss.check_violations()
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
            constraint = 'voltage'
        else:
            constraint = self.constraint

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
            bus_n += 1

        nodal_results = pd.DataFrame.from_dict(res, orient='index')

        end_time = time.process_time()
        self.execution_time = end_time - start_time
        print(f"\rBus {bus_n}/{total_buses}  ({bus_n/(total_buses) * 100:.2f}% complete in {self.execution_time:.2f} seconds)  ")

        return nodal_results
