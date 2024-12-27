"""
This example file runs a very basic grid and EV control co-simulation
The grid model is the IEEE 34 bus feeder with three EVSE connected.
The loads are taken from
The EVSE controller turns the load on at 00:00, off at 15:00, on again at 21:00
"""
from datetime import datetime, timedelta, time
import os
import sys
sys.path.append(os.getcwd())
from pathinit import EVIDIST_ROOT_PATH
import subprocess
import multiprocessing
from multiprocessing import Process, Pool
import logging
import helics as h
import asyncio
import pandas as pd
import pickle
import math

from dashboard.actions import DataOperatorPlus
from modules.GridSim import GridSim
from modules.EVChargeSim import EVChargeSim
from modules.Controller import Controller


class SimPlus():

    def __init__(self, sim_name: str, feeder_name: str, main_dss_file: str,
                 ev_adoption_file: str, premise_data_file: str, controller_name:str,
                 month: int, day_of_week: int, sim_start_time: int, sim_end_time: int) -> None:
        self.sim_name: str = sim_name
        self.feeder_name: str = feeder_name
        self.main_dss_file: str = main_dss_file
        self.ev_adoption_file: str = ev_adoption_file
        self.premise_data_file: str = premise_data_file
        self.controller_name: str = controller_name
        self.sim_timestep: str = str(300)
        self.month = month
        self.day_of_week = day_of_week
        self.sim_start_time: int = sim_start_time
        self.sim_end_time: int = sim_end_time
        self.day_of_week_start = self.day_of_week + math.floor(self.sim_start_time/3600/24)
        self.day_of_week_end = self.day_of_week + math.floor(self.sim_end_time/3600/24)
        self.time_of_day_start = (datetime.combine(datetime.today(), time(0,0))  + timedelta(seconds=self.sim_start_time)).time()
        self.time_of_day_end =  (datetime.combine(datetime.today(), time(0,0))  + timedelta(seconds=self.sim_end_time%(24*3600))).time()

    def _gen_load_profiles(self):
        pass

    def process_charging_events(self):
        CEs = pd.read_csv(self.ev_adoption_file)
        CEs_feeder = CEs[CEs['Feeder'] == self.feeder_name]
        CEs_feeder_month_day = CEs_feeder[CEs_feeder['month'] == self.month]
        CEs_feeder_month_day = CEs_feeder_month_day[self.day_of_week_start <= CEs_feeder_month_day['dow']]
        CEs_feeder_month_day = CEs_feeder_month_day[(CEs_feeder_month_day['dow'] < self.day_of_week_end) | ((CEs_feeder_month_day['dow'] == self.day_of_week_end) & (CEs_feeder_month_day['park_start_timestamp'].map(lambda x: datetime.strptime(x, '%H:%M:%S').time()) < self.time_of_day_end))]
        self.ev_adoption_file = EVIDIST_ROOT_PATH + "/data/temp_sim_plus/sim_plus_charge_event_data.csv" #overwrite adoption file to the filtered version.
        CEs_feeder_month_day.to_csv(self.ev_adoption_file) #save just this specific simulation day.

        premise_df = pd.read_csv(self.premise_data_file)
        premise_df = premise_df[premise_df['Feeder'] == self.feeder_name]

        trns_premise_ev_mapping: dict[str,dict[str,list[str]]] = dict()
        for _, row in premise_df.iterrows():
            trns = str(row["Transformer ID"])
            premise = str(row["Premise Number"])
            if not trns in trns_premise_ev_mapping.keys():
                trns_premise_ev_mapping[trns] = dict()
            if not premise in trns_premise_ev_mapping[trns].keys():
                trns_premise_ev_mapping[trns][premise] = list()

            for _, ce_row in CEs_feeder_month_day[CEs_feeder_month_day["Premise Number"] == int(premise)].iterrows():
                ev = str(ce_row["Veh_ID_Num"])
                if not ev in trns_premise_ev_mapping[trns][premise]:
                    trns_premise_ev_mapping[trns][premise].append(ev)

        with open(EVIDIST_ROOT_PATH + "/data/temp_sim_plus/sim_plus_trns_premise_ev_mapping.pkl", 'wb') as file:
            pickle.dump(trns_premise_ev_mapping, file)

    async def run(self, progress, progress_queue):
        # self._gen_load_profiles()
        """

        Execution

        """
        progress[0] = 0
        await progress_queue.put(progress[0])
        await asyncio.sleep(0.01)

        print("Initializing simulation...")
        self.process_charging_events()

        # create a helics broker in the command prompt
        process_broker = subprocess.Popen(['helics_broker', '-f3', '-tzmq'])
        print('broker started')

        process_grid = subprocess.Popen(['python', EVIDIST_ROOT_PATH + '/modules/GridSim.py', self.sim_timestep, self.main_dss_file, self.sim_name, self.feeder_name, self.premise_data_file, str(self.sim_start_time), str(self.sim_end_time)])
        print(f'{self.sim_name} grid sim started')

        process_cont = subprocess.Popen(['python', EVIDIST_ROOT_PATH + '/modules/Controller.py', self.sim_timestep, self.sim_name, self.feeder_name, self.ev_adoption_file, self.controller_name, str(self.month), str(self.day_of_week), str(self.sim_start_time), str(self.sim_end_time)])
        print('controller started')

        process_ev = subprocess.Popen(['python', EVIDIST_ROOT_PATH + '/modules/EVChargeSim.py', self.sim_timestep, str(self.sim_start_time), str(self.sim_end_time)])
        print('charging simulation started')

        print("")
        progress[0] += 7.5
        await progress_queue.put(progress[0])
        await asyncio.sleep(0.01)

        flag_grid = False
        flag_ev = False
        flag_cont = False
        while True:
            if (process_grid.poll() is not None) and not flag_grid:
                flag_grid = True
                print(f'{self.sim_name} grid sim finished')
                progress[0] += 15
                await progress_queue.put(progress[0])
                await asyncio.sleep(0.01)

            elif (process_ev.poll() is not None) and not flag_ev:
                flag_ev = True
                print('charging simulation finished')
                progress[0] += 15
                await progress_queue.put(progress[0])
                await asyncio.sleep(0.01)

            elif (process_cont.poll() is not None) and not flag_cont:
                flag_cont = True
                print('controller finished')
                progress[0] += 15
                await progress_queue.put(progress[0])
                await asyncio.sleep(0.01)

            elif flag_grid and flag_ev and flag_cont:
                process_broker.terminate()
                print('broker closed.')
                progress[0] += 7.5
                await progress_queue.put(progress[0])
                await asyncio.sleep(0.01)
                break

        print("")
        await asyncio.sleep(0.02)
        self._save()

    def _save(self):
        pass
