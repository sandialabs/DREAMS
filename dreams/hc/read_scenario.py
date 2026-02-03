"""
Function to read written scenarios.
"""

import os
from pathlib import Path
import pandas as pd
import dreams


def read_qsts_scenario(feeder, base_folder, scenario_name):
    """
    Collect qsts scenario data from base_folder location related to
    scenario named scenario_name. Returns fully parameterized QSTS scenario.

    NOTE: Works as is - could be simplier as more can be read from the
    meta csv file.

    Parameters
    ----------
    feeder : dreams.Feeder
        Feeder to use for QSTS scenario
    base_folder : pathlib.Path
        Path to base folder of feeder. Should contain the QSTS_scenarios 
        folder and other redirects folder.  Typically contains Main.dss
        file.
    scenario_name : str
        String matching name of QSTS scenario to load.  Must match exactly.

    Returns
    -------
    dreams.hc.Scenario
        Fully intialized scenario - should be ready to run.
    """
    # ensure Path
    if not isinstance(base_folder, Path):
        base_folder = Path(base_folder)

    # check for meta data
    scenario_path = base_folder / 'QSTS_scenarios' / scenario_name
    meta_fp = scenario_path / 'scenario_meta_data.csv'
    if os.path.exists(meta_fp):
        meta_df = pd.read_csv(meta_fp, index_col='parameter_name')
    else:
        # no meta data
        print('BREAK - no meta data for scenario found!')
        return

    base_folder_contents = os.listdir(base_folder)

    # search for base redirects
    if 'base_redirects' in base_folder_contents:
        redirect_paths = base_folder / 'base_redirects'
        scenario_redirects = os.listdir(redirect_paths)
        if scenario_name in scenario_redirects:
            path_to_base_redirects = redirect_paths / scenario_name
    else:
        print('no base redirects')

    # search for control redirects
    path_to_control_redirects = None
    if 'control_redirects' in base_folder_contents:
        redirect_paths = base_folder / 'control_redirects'
        scenario_redirects = os.listdir(redirect_paths)
        if scenario_name in scenario_redirects:
            path_to_control_redirects = redirect_paths / scenario_name
    else:
        print('no base redirects')

    # search for QSTS_scenarios
    if 'QSTS_scenarios' in base_folder_contents:
        redirect_paths = base_folder / 'QSTS_scenarios'
        scenario_redirects = os.listdir(redirect_paths)
        if scenario_name in scenario_redirects:
            path_to_seeds = redirect_paths / scenario_name
    else:
        print('no existing QSTS redirects')  # this is more of an issue...

    # if no qsts redirects, break - scenario not written
    # collect seeds
    seed_folders = os.listdir(path_to_seeds)
    seeds = {}
    for seed in seed_folders:
        if 'results' == seed:
            # skip results folder
            continue
        elif '.csv' in seed:
            # skip meta data csv
            continue
        else:
            seeds[int(seed)] = {}
            seeds[int(seed)]['path'] = path_to_seeds / seed
            steps = os.listdir(seeds[0]['path'])
            n_steps = len(steps)

    # create scenario with read info
    scenario = dreams.hc.Scenario(
        scenario_name,
        feeder,
        n_simulations=len(seeds),
        n_steps=n_steps,
        qsts_step_size_sec=int(meta_df.loc['qsts_step_size_sec'][0]),
        duration_seconds=int(meta_df.loc['duration_seconds'][0]),
        max_iterations=int(meta_df.loc['max_iterations'][0]),
        qsts_profile=meta_df.loc['qsts_profile'][0],
        qsts_hour_offset=int(meta_df.loc['qsts_hour_offset'][0]),
        qsts_origin=meta_df.loc['qsts_origin'][0],
        control_mode=meta_df.loc['control_mode'][0],
        base_path=base_folder,
        seed=list(seeds.keys())[0],
        path_to_base_redirects=path_to_base_redirects,
        minimize_duplicates=bool(meta_df.loc['minimize_duplicates'][0]),
        step_labels=eval(meta_df.loc['step_labels'][0]),
        step_title=meta_df.loc['step_title'][0],
    )
    # create function to write these parameters into a csv or similar (json?)
    # it will facilitate loading previously created scenarios
    # def read_steps(scenario, path_to_control_redirects, seeds)
    # read/add redirects to scenario based on written redirects
    # base redirects already read...
    # handle control redirects

    if path_to_control_redirects is not None:
        for file in os.listdir(path_to_control_redirects):
            if '.dss' in file:
                redirect_location = path_to_control_redirects / file
                redirect_name = file[:-4]
                control_redirect = dreams.Redirect(
                    name=redirect_name,
                    file_location=redirect_location,
                    read_file=True
                    )
                scenario.add_control_redirect(control_redirect)

    # handle seeds and steps
    for seed, _ in seeds.items():
        scenario.seed[seed] = {}
        step_paths = seeds[seed]['path']
        scenario.all_seeds.append(int(seed))

        scenario.seed[seed][0] = {}

        for step in os.listdir(step_paths):
            scenario.seed[seed][int(step)] = {}
            step_path = step_paths / step
            redirects = os.listdir(step_path)
            for redirect in redirects:
                if '.dss' in redirect:
                    redirect_location = step_path / redirect
                    redirect_name = redirect[:-4]
                    step_redirect = dreams.Redirect(
                        name=redirect_name,
                        file_location=redirect_location,
                        read_file=True
                        )
                    scenario.seed[seed][int(step)][redirect_name] = step_redirect

    scenario.steps_created = True

    return scenario
