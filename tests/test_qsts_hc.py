"""
tests for interpolated qsts hosting capacity process
"""

import unittest
from pathlib import Path
import pandas as pd
import networkx as nx
import numpy as np
import os
import time

import dreams

PARENT_DIR = Path(__file__).parent.resolve()
MODEL_DIR = Path(PARENT_DIR.parent, "demos", 'models')
TEMP_DIR = Path(PARENT_DIR.parent, "demos", 'temp_data')

class TestGraph(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        super(TestGraph, self).__init__(*args, **kwargs)
        # Default attributes
        self.model_fp = MODEL_DIR / "sfo_p1udt1469" / "Main.dss"
        self.buses_to_test = [
            'p1udt847',
            'p1udt16',
            'p1udt440'
        ]
        self.output_dir = TEMP_DIR

    def test_qsts_class_creation(self):
        feeder = dreams.Feeder(self.model_fp)
        # default creation of QSTS hc object
        res = dreams.hc.interp.QSTS_HC(
            feeder,
            self.buses_to_test,
            self.output_dir,
            step_size_seconds=60*15,  # 15 minute profile
            total_time_steps=24*4,  # run for one day 
        )
        self.assertIsInstance(res,  dreams.hc.interp.QSTS_HC)
        self.assertIsInstance(res.monitor_redirect, dreams.Redirect)
        self.assertIsInstance(res.first_step_monitors, dict)
        self.assertIsInstance(res.single_run_time, float)
        self.assertIsInstance(res.asset_range, type(np.array(1)))

        self.assertIsInstance(res.hc_interp_res, dict)
        self.assertEqual(len(res.hc_interp_res), 3)


    def test_custom_asset_range(self):
        # ensure dataset is being exported at expected location
        test_bus = ['p1udt242']
        test_asset_range = [10, 100, 1000, 10000]

        feeder = dreams.Feeder(self.model_fp)

        res = dreams.hc.interp.QSTS_HC(
            feeder,
            test_bus,
            self.output_dir,
            asset_range=test_asset_range,
            step_size_seconds=60*15,  # 15 minute profile
            total_time_steps=24*4,  # run for one day
            debug=True,
        )

        # check aseet range
        self.assertEqual(res.asset_range, test_asset_range)

    def test_demand_hc(self):
        # ensure dataset is being exported at expected location
        test_bus = ['p1udt242']

        feeder = dreams.Feeder(self.model_fp)

        res = dreams.hc.interp.QSTS_HC(
            feeder,
            test_bus,
            self.output_dir,
            kind='load',
            step_size_seconds=60*15,  # 15 minute profile
            total_time_steps=24*4,  # run for one day
        )

        # check that result exists
        self.assertIsInstance(res.result_df, pd.DataFrame)

    def test_dataset_export(self):
        # ensure dataset is being exported at expected location
        sim_name = 'output_test'
        test_bus = ['p1udt242']
        res_name = f"{sim_name}-gen_hc-{test_bus[0]}.nc"
        res_fp = self.output_dir / res_name

        # check if file exists...
        if os.path.exists(res_fp):
            for attempt in range(5):
                try:
                    # delete if so
                    os.remove(res_fp)
                    break
                except PermissionError:
                    time.sleep(0.01)
            else:
                raise PermissionError(
                    f"Unable to delete {res_fp} after several attempts. "
                )

        feeder = dreams.Feeder(self.model_fp)

        res = dreams.hc.interp.QSTS_HC(
            feeder,
            test_bus,
            self.output_dir,
            compute=False,
            step_size_seconds=60*15,  # 15 minute profile
            total_time_steps=24*4,  # run for one day
            name=sim_name,
        )
        # check if file exists
        self.assertTrue(os.path.exists(res_fp))

if __name__ == "__main__":
    unittest.main()
