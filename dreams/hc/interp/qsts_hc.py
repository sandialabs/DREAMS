"""
class definition for qsts generation object
"""
import dreams
import os
import time

from pathlib import Path
import pandas as pd

from . import sim
from . import dataset as interp_dataset
from . import monitor as interp_monitors
from . import calc as interp_calc
from . import monitor_selector as ms

class QSTS_HC():
    def __init__(
            self,
            feeder,
            buses_to_test:list,
            output_dir:Path,
            kind='gen',
            mode='duty',
            asset_shape:dreams.Shape=None,
            step_size_seconds:int=60*60,
            total_time_steps:int=8760,
            auto_adjust_thresholds=False,  # for different thresholds automatically created
            default_high_voltage=1.05,
            default_low_voltage=0.95,
            default_thermal_threshold=1.0,
            default_backfeed_limit=0.0,
            asset_range=None,
            save_dataset=True,
            compute:bool=True,
            debug:bool=False,
            name:str='unnamed'
            ):
        
        self.name = name
        if debug:
            print(f'* Starting QSTS_HC of {self.name}')

        # store inputs to object
        self.feeder = feeder
        self.buses_to_test = buses_to_test
        self.output_dir = output_dir

        # ensure one or the other
        if kind != 'gen':
            kind = 'load'

        self.kind = kind

        self.step_size_sec = step_size_seconds
        self.total_time_steps = total_time_steps
        self.mode = mode

        self.compute = compute
        self.debug = debug
        self.save_dataset = save_dataset

        self.monitor_redirect = None
        self.asset_range = asset_range

        self.asset_shape = asset_shape
        self.result_df = None

        self.max_demand_step = 0
        self.min_demand_step = 0

        self.auto_adjust_thresholds = auto_adjust_thresholds
        self.thresholds = {
            'high_voltage': default_high_voltage,
            'low_voltage': default_low_voltage,
            'thermal': default_thermal_threshold,
            'backfeed': default_backfeed_limit
        }
        if self.debug:
            print('* initializing monitor selector...')
        self.monitor_selector = ms.MonitorSelector(
            self.feeder,
            hc_type=self.kind,
            )

        # ensure output directory exists for dataset saving
        if not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        if self.debug:
            print('* initializing feeder...')

        sim.init_feeder(
            self,
            create_monitors=True,
            step_size_s=self.step_size_sec,
            )

        # to ensure monitors and system performs as expected
        self._perform_first_run()

        # identify asset range to test based on first run
        if self.asset_range is None:
            self._set_asset_range()

        # update monitor selector capacities based on max demand step
        self._update_max_capacities()

        # initialize variables for each bus
        self.hc_interp_res = {}

        self.n_total_test_buses = len(self.buses_to_test)
        self.current_bus = 0

        # for each bus:
        for bus_name in buses_to_test:
            if debug:
                print()
            bus_start_time = time.time()
            self.hc_interp_res[bus_name] = {}
            self.hc_interp_res[bus_name]['distance_from_sub'] = self.feeder.buses.loc[bus_name].distance

            self.current_bus += 1
            if self.debug:
                print(f"** Bus {self.current_bus}/{self.n_total_test_buses}")
            else:
                print(f"** Bus {self.current_bus}/{self.n_total_test_buses} ", end="\r")

            ## run sim with  all asset sizes (this involves re-init of feeder and editing the asset value)
            qsts_mons = sim.run_asset_range(self, bus_name)  #  was previously hc_bus_res
            end_bus_sim_time = time.time()
            self.hc_interp_res[bus_name]['qsts_sim_time'] = end_bus_sim_time - bus_start_time
            self.hc_interp_res[bus_name]['n_asset_size_tested'] = len(qsts_mons)  # place where non-convergence will be recorded
            # create dataset
            if self.debug:
                print('*creating dataset...')
            ds_combined = interp_dataset.get_combined_ds(qsts_mons)

            # save dataset # NOTE: may want to make optional?
            if self.save_dataset:
                output_fp = self.output_dir / f"{self.name}-{self.kind}_hc-{bus_name}.nc"
                ds_combined.to_netcdf(output_fp, mode='w')
                self.hc_interp_res[bus_name]['out_path'] = str(output_fp.absolute())

                if self.debug:
                    print('*saving dataset to disk...')
            else:
                self.hc_interp_res[bus_name]['out_path'] = 'dataset not saved'

            end_data_handling_time = time.time()
            self.hc_interp_res[bus_name]['dataset_creation_time'] = end_data_handling_time - end_bus_sim_time

            if not self.compute:
                continue

            ## interpolate all hc constraints from datases
            #  ============================================================
            # voltage constrained hosting capaicity
            if self.debug:
                print('* interpolating voltage constrained hc...')

            if self.kind == 'gen':
                # if gen, check high voltage
                voltage_threshold = self.thresholds['high_voltage']
                vchc_threshold_kind = 'higher'
            else:
                voltage_threshold = self.thresholds['low_voltage']
                vchc_threshold_kind = 'lower'

            vchc_res = interp_calc.get_vchc(
                ds_combined,
                voltage_threshold=voltage_threshold,
                auto_adjust_threshold=self.auto_adjust_thresholds,
                threshold_kind=vchc_threshold_kind,
                debug=self.debug,
                )
            self.hc_interp_res[bus_name].update(vchc_res)

            #  ============================================================
            # thermal constrained hosting capaicity
            if self.debug:
                print('* interpolating thermal constrained hc...')

            if self.kind == 'gen':
                # NOTE: may be cause issues with auto-adjust...
                thermal_threshold = -1*self.thresholds['thermal']
            else:
                thermal_threshold = self.thresholds['thermal']

            tchc_res = interp_calc.get_tchc(
                ds_combined,
                thermal_threshold=thermal_threshold,
                auto_adjust_threshold=self.auto_adjust_thresholds,
                debug=self.debug,
                )
            self.hc_interp_res[bus_name].update(tchc_res)

            #  ============================================================
            # NOTE: substation constraint only on generation runs
            # a different approach could be used to more accurately identify
            # schc for load - like thermal limits of first element
            if self.kind == 'load':
                continue

            if self.debug:
                print('* interpolating substation constrained hc...')

            # TODO: handle auto adjusted threshold...
            backfeeding_limit = self.thresholds['backfeed']

            schc_res = interp_calc.get_schc(ds_combined, backfeeding_limit)
            self.hc_interp_res[bus_name].update(schc_res)

            # interpolation timing
            end_interp_time = time.time()
            self.hc_interp_res[bus_name]['interp_time'] = end_interp_time - end_data_handling_time

            # total bus processing time
            self.hc_interp_res[bus_name]['total_bus_calc_time'] = end_interp_time - bus_start_time

        # aggregate calcualted results to dataframe
        if self.debug:
            print('* creating result dataframe...')
            
        df = pd.DataFrame.from_dict(self.hc_interp_res, orient='index')
        df.index.rename('bus_name', inplace=True)
        self.result_df = df

        if self.debug:
            print('* complete.')
        print()

    def _perform_first_run(self):
        """
        execute first run to initialize and collect basic system info
        """
        first_run_start = time.time()
        sim.run_qsts(n_total_steps=self.total_time_steps, debug=self.debug)
        self.first_step_monitors = interp_monitors.collect_monitors()
        first_run_end = time.time()
        self.single_run_time = first_run_end - first_run_start


    def _set_asset_range(self):
        """
        based on first run, identify reasonable asset range to test.
        Assumption is that max demand times 1.1 will cause violations
        or enough difference between runs to generate results.
        """
        end_value = self.first_step_monitors['vsource']['source'].get_max_kw_delivered() * 1.1
        start_value = end_value / 100
        iterations = 4

        self.asset_range = sim.collect_asset_range(start_value, end_value, iterations)

    def _update_max_capacities(self):
        """
        after first run, go to max or min demand step and
        update monitor selector capacities

        use max demand for load, use min demand for generation
        """
        p_series = self.first_step_monitors['vsource']['source'].df[['P_total_kW']]

        # collect minimum step before absolute
        self.min_demand_step = p_series.idxmax().iloc[0]

        # collect maximum step
        p_series = p_series.abs()
        max_step = p_series.idxmax().iloc[0]
        self.max_demand_step = max_step

        # handle case where first step is maximum...
        if max_step == 0:
            max_step = 1

        # run sim to max flow state
        if self.kind == 'load':
            sim_step = self.max_demand_step
        else:
            sim_step = self.min_demand_step
        dreams.hc.interp.sim.run_qsts(n_total_steps=sim_step)
        self.monitor_selector.collect_capacities()
        