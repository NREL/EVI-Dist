"""
This example file runs a very basic grid and EV control co-simulation
The grid model is the IEEE 34 bus feeder with three EVSE connected.
The loads are taken from 
The EVSE controller turns the load on at 00:00, off at 15:00, on again at 21:00
"""
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

from block_classes.GridSim import GridSim
from block_classes.EVChargeSim import EVChargeSim
from block_classes.Controller import Controller




# Example simulation class for Lite version
class SimPlus():

    def __init__(self, sim_name: str, main_dss_file: str, ev_adoption_file: str = "/Users/djackson/Documents/Xcel_Energy_Project/Data/medium.csv", premise_data_file: str = "/Users/djackson/Documents/Xcel_Energy_Project/Data/10_feeders_premise_report.csv") -> None:
        self.sim_name: str = sim_name
        self.main_dss_file: str = main_dss_file
        self.ev_adoption_file: str = ev_adoption_file
        self.premise_data_file: str = premise_data_file
        self.sim_timestep: str = str(60)

    def _gen_load_profiles(self):
        pass
        
    async def run(self, progress, progress_queue):
        # self._gen_load_profiles()
        """
        
        Execution
        
        """
        progress[0] = 0
        await progress_queue.put(progress[0]) 
        await asyncio.sleep(0.01)
        
        # create a helics broker in the command prompt
        process_broker = subprocess.Popen(['helics_broker', '-f3', '-tzmq'])
        print('broker started')

        process_grid = subprocess.Popen(['python', EVIDIST_ROOT_PATH + '/block_classes/GridSim.py', self.sim_timestep, self.main_dss_file, self.sim_name, self.premise_data_file])
        print(f'{self.sim_name} grid sim started')

        process_cont = subprocess.Popen(['python', EVIDIST_ROOT_PATH + '/block_classes/Controller.py', self.sim_timestep, self.sim_name, self.ev_adoption_file])
        print('controller started')
        
        process_ev = subprocess.Popen(['python', EVIDIST_ROOT_PATH + '/block_classes/EVChargeSim.py', self.sim_timestep])
        print('charging simulation started')
        
        print("")
        progress[0] += 5
        await progress_queue.put(progress[0]) 
        await asyncio.sleep(0.01)
        
        flag_grid = False
        flag_ev = False
        flag_cont = False
        while True:
            if (process_grid.poll() is not None) and not flag_grid:
                flag_grid = True
                print(f'{self.sim_name} grid sim finished')
                progress[0] += 30
                await progress_queue.put(progress[0]) 
                await asyncio.sleep(0.01)
                
            if (process_ev.poll() is not None) and not flag_ev:
                flag_ev = True
                print('charging simulation finished')
                progress[0] += 30
                await progress_queue.put(progress[0]) 
                await asyncio.sleep(0.01)
                
            if (process_cont.poll() is not None) and not flag_cont:
                flag_cont = True
                print('controller finished')
                progress[0] += 30
                await progress_queue.put(progress[0]) 
                await asyncio.sleep(0.01)
                
            if flag_grid and flag_ev and flag_cont:
                process_broker.terminate()
                print('broker closed.')
                progress[0] += 5
                await progress_queue.put(progress[0]) 
                await asyncio.sleep(0.01)
                break

        await asyncio.sleep(0.02)
        self._save()

    def _save(self):
        pass
        