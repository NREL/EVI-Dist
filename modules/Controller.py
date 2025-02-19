import os
import sys
sys.path.append(os.getcwd())
from pathinit import EVIDIST_ROOT_PATH
import math
import pandas as pd
import helics as h
import json
import numpy as np
from datetime import datetime, timedelta, time
import logging
logger = logging.getLogger(__name__)
# sys.path.append('..')
import pickle
#parent_directory = os.getcwd()
#sys.path.append(parent_directory + "/modules")
import modules.lite.ev_profile_generation as epg
from modules.scm.controls import EV, ChargingStation, ChargingManagementSystem


"""
This class is to hold the controller
It gets inputs on grid status from the grid sim
It is initialized with info on electricity pricing and forecasting
It takes inputs on plug-in time, departure time, energy needs from the mobility analysis module
It then does some SCM control and sends those EV control setpoints to the EV Sim
"""

class Controller:
    def __init__(self, sim_name, controller_name, cosim, helics_config_path, timestep_sec, feeder_name, charge_event_file, horizon_sec, month, day_of_week, sim_start_time, sim_end_time):
        # controller name options: default_controller: all off during peak, all on during offpeak
        #   TOU_random, TOU_ASAP, TOU_ALAP
        # feeder_name directs to which opendss file to use
        # charge_event_file should have park start and end times, vehicle id with month and day value, transformer number, and premise number, max ac power, energy_kwh
        # day of week starts on monday
        # add important params here
        self.sim_name: str = sim_name
        self.controller_name: str = controller_name.upper()
        self.feeder_name = feeder_name
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(filename=EVIDIST_ROOT_PATH + f'/logs/sim_plus/{controller_name}.log', encoding='utf-8', level=logging.DEBUG, filemode='w')
        self.pricing = []
        self.baseload_forecast = []
        self.charge_event_file = charge_event_file
        self.charge_events = [] # later pd.read_csv(charge_event_file)
        self.control_setpoints = {}#{'evse0':0, 'evse1':0, 'evse2':0}
        self.voltages = []
        # these are for if you want time-step based sim
        self.timestep_sec = timestep_sec
        self.horizon_sec = horizon_sec
        self.co_simulation = cosim
        self.sim_start_time = sim_start_time
        self.sim_end_time = sim_end_time
        self.time = sim_start_time
        self.helics_config_path = helics_config_path
        self.fed = None
        self.publications = []
        self.subscriptions = []
        self.year=2024
        self.month = month
        self.day_of_week = day_of_week

        with open(EVIDIST_ROOT_PATH + f'/data/temp_sim_plus/sim_plus_trns_premise_ev_mapping.pkl', 'rb') as file:
            self.trns_premise_ev_mapping: dict[str,dict[str,list[str]]] = pickle.load(file)
        self.trns_scm: dict[str,ChargingManagementSystem] = dict()
        self.scm_evs: list[EV] = list()

    def setup_controller(self):
        # this function loads the pricing, forecast,
        # loads plug-in time, departure time, and energy needs


        ##### insert data loading here #####
        charge_events_input = pd.read_csv(self.charge_event_file)
        start_datetime = datetime(year=self.year, month=self.month, day=self.day_of_week, hour=0, minute=0, second=0) + timedelta(seconds=self.sim_start_time)
        self.start_datetime = start_datetime
        end_datetime = datetime(year=self.year, month=self.month, day=self.day_of_week, hour=0, minute=0, second=0) + timedelta(seconds=self.sim_end_time)
        self.end_datetime = end_datetime


        # if it is a co_simulation this sets up the helics federate
        if self.co_simulation:
            if self.helics_config_path == '':
                fedinfo = h.helicsCreateFederateInfo()
                # h.helicsFederateInfoSetCoreName(fedinfo, 'controller')#self.name)
                h.helicsFederateInfoSetCoreInitString(fedinfo, "--federates=1")
                self.fed = h.helicsCreateValueFederate('controller', fedinfo)
                self.publications.append(h.helicsFederateRegisterPublication(self.fed, 'control_setpoints', h.HelicsDataType.STRING)) # this is published as a json string of a dictionary
                self.subscriptions.append(h.helicsFederateRegisterSubscription(self.fed, f'{self.sim_name}/voltages', ""))
                self.subscriptions.append(h.helicsFederateRegisterSubscription(self.fed, f'{self.sim_name}/currents', ""))
                self.subscriptions.append(h.helicsFederateRegisterSubscription(self.fed, f'{self.sim_name}/trns_kW', ""))
                self.subscriptions.append(h.helicsFederateRegisterSubscription(self.fed, f'{self.sim_name}/trns_kvar', ""))
                self.subscriptions.append(h.helicsFederateRegisterSubscription(self.fed, f'{self.sim_name}/trns_rating', ""))
            else:
                self.fed = h.helicsCreateValueFederateFromConfig(self.helics_config_path)
            h.helicsFederateSetTimeProperty(self.fed, h.helics_property_time_delta, 0.001) # #this is the minimum detectable time difference, not the timestep
            h.helicsFederateEnterExecutingMode(self.fed)

            updated_time = -10 + self.sim_start_time
            self.time = -20 + self.sim_start_time
            while self.time < updated_time:
                self.time = h.helicsFederateRequestTime(self.fed, updated_time)
            self.time = self.sim_start_time

        # for the TOU heuristic controls, they don't require grid feedback, so
        # pre-calculate power profiles
        if self.controller_name.startswith('TOU') or self.controller_name.startswith('UNCONTROLLED'):
            # print(f'TOU heuristic controls do not get grid feedback. Precalculating all charge sessions')

            charge_start = []
            charge_end = []
            charge_events_input['charge_power'] = [min(cvi, 11.5) for cvi in charge_events_input['Max AC Power kW']] #TODO: should a max charging power be configurable
            n_charge_events = len(charge_events_input['charge_power'])
            # calculate the minimum charge time in minutes to feed to the TOU heuristics
            # if 'total_charging_time' not in charge_events_input.keys():
            charge_events_input['total_charging_time'] = [cvi_energy/cvi_power*60 for cvi_power, cvi_energy  in zip(charge_events_input['charge_power'], charge_events_input['energy_kwh'])]
            # get timestamps for start and end times of the low price periods for each evse
            # if 'low_price_period' not in charge_events_input.keys():
                #TODO: date and day of week are not the same

            low_price_period_count, low_timestamps = get_low_tou_timestamps_for_TOU_alg(start_datetime.time(), (end_datetime - timedelta(seconds=1)).time(), self.day_of_week)
            charge_events_input['low_price_period'] = [low_price_period_count]*n_charge_events
            charge_events_input['low_price_timestamps'] = [low_timestamps]*n_charge_events
            # for each charge event, determine the starting charging time
            for _, ce_row in charge_events_input.iterrows():
                park_end_time = datetime.combine(datetime.today().date(),datetime.strptime(ce_row['park_end_timestamp'], '%H:%M:%S').time()) + timedelta(days=ce_row["dow"]-self.day_of_week)
                park_start_time = datetime.combine(datetime.today().date(),datetime.strptime(ce_row['park_start_timestamp'], '%H:%M:%S').time()) + timedelta(days=ce_row["dow"]-self.day_of_week)
                #l2power = min(9.6, ce_row['Max AC Power kW'])
                energy_needed = ce_row['energy_kwh']

                if park_end_time < park_start_time:
                    park_end_time = park_end_time + timedelta(hours = 24)

                if self.controller_name== 'TOU ALAP':
                    charge_start_time = epg.calculate_charge_start_time_TOU_ALAP(ce_row, selected_mode='plus')
                elif self.controller_name== 'TOU ASAP':
                    charge_start_time = epg.calculate_charge_start_time_TOU_ASAP(ce_row, selected_mode='plus')
                elif self.controller_name== 'TOU RANDOM':
                    charge_start_time_TOU_ASAP = epg.calculate_charge_start_time_TOU_ASAP(ce_row, selected_mode='plus')
                    charge_start_time_TOU_ALAP = epg.calculate_charge_start_time_TOU_ALAP(ce_row, selected_mode='plus')
                    charge_start_time = datetime.strptime(epg.calculate_charge_start_time_TOU_random(charge_start_time_TOU_ASAP, charge_start_time_TOU_ALAP), '%H:%M:%S').time()
                elif self.controller_name== 'UNCONTROLLED':
                    charge_start_time = datetime.strptime(ce_row['park_start_timestamp'], '%H:%M:%S').time()
                else:
                    # print(f'WARNING: {self.controller_name} charging control method not recognized, using uncontrolled')
                    charge_start_time = datetime.strptime(ce_row['park_start_timestamp'], '%H:%M:%S').time()
                charge_start_time = datetime.combine(start_datetime.date(),charge_start_time) + timedelta(days=ce_row["dow"]-self.day_of_week)
                energy_end_time = charge_start_time + timedelta(minutes = ce_row['total_charging_time'])
                charge_end_time = min(park_end_time, energy_end_time)
                charge_start.append(charge_start_time)
                charge_end.append(charge_end_time)
            charge_events_input['charge_start'] = charge_start
            charge_events_input['charge_end'] = charge_end
            self.charge_events = charge_events_input
            # setup the helics message with 0 power for all
            for evse_id in charge_events_input['Veh_ID_Num'].unique():
                self.control_setpoints[str(evse_id)] = 0

        elif self.controller_name in ['FCFS', 'FCFS + SM50', 'EQUAL SHARING']:
            #in the setup, create the EV and ChargingManagementSystem objects.
            #Save the plug in times for each vehicle. Along with associated xfmr number, premise number, energy need, etc.

            trnsfmr_ratings: dict = json.loads(h.helicsInputGetString(self.subscriptions[4]))

            for trns_id in trnsfmr_ratings.keys():
                if trns_id in self.trns_premise_ev_mapping:
                    self.trns_scm[trns_id] = ChargingManagementSystem(allocation_method=self.controller_name, time_step_sec=self.timestep_sec)
                    self.trns_scm[trns_id].trns_id = trns_id
                    self.trns_scm[trns_id].current_time = start_datetime
                    self.trns_scm[trns_id].capacity_rated = trnsfmr_ratings[trns_id]
                    for premise_id in self.trns_premise_ev_mapping[trns_id]:
                        for ev_id in self.trns_premise_ev_mapping[trns_id][premise_id]:
                            # Extract charging event details from CEs_feeder_day
                            ev_events = charge_events_input[charge_events_input['Veh_ID_Num'] == ev_id]

                            for event_row_index, event in ev_events.iterrows():
                                premise_id = event['Premise Number']
                                park_start_time = pd.to_datetime(event['park_start_timestamp']).floor('T').time()
                                park_start_timestamp = datetime.combine(start_datetime,park_start_time) + timedelta(days=event["dow"]-self.day_of_week)
                                duration = round(event['park_time_seconds'] / 60)  # Total connection time in minutes

                                energy_need = event['energy_kwh']
                                energy_capacity = event["Battery Capacity"]
                                start_soc = event['start_soc']
                                max_charge_rate = min(event['Max AC Power kW'], 11.5) #TODO: should a max charging power be configurable

                                # Create EV object with event_row_index
                                ev = EV(
                                    transformer_id=trns_id,
                                    ev_id=ev_id,
                                    premise_id=premise_id,
                                    plug_in_time=park_start_timestamp,
                                    duration=duration,
                                    start_SOC=start_soc,
                                    energy_need=energy_need,
                                    energy_capacity=energy_capacity,
                                    max_charge_rate=max_charge_rate,
                                    event_index=event_row_index)  # Add this line
                                self.trns_scm[trns_id].add_ev(ev)
                                self.scm_evs.append(ev)
                                self.logger.debug(f"EV {ev.ev_id} added to the CMS list, Charge Event Index: {ev.event_index}, Transformer ID: {ev.transformer_id}, Plug-in Time: {ev.plug_in_time}, Duration: {ev.duration}, Start SOC: {ev.start_SOC}, Energy Need: {ev.energy_need}, Max Charge Rate: {ev.max_charge_rate} ")


        return

    def run_control_opt(self):
        # this function solves the control parameters
        ev_control_setpoints = {}
        cosim_hours = int(np.floor(self.time/3600))
        cosim_minutes = int(np.floor((self.time-cosim_hours*3600)/60))
        cosim_seconds = int(self.time-cosim_hours*3600-cosim_minutes*60)
        cosim_datetime = self.start_datetime.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(hours=cosim_hours,minutes=cosim_minutes, seconds=cosim_seconds)

        # first get the updated grid status
        kW: dict[str,float] = json.loads(h.helicsInputGetString(self.subscriptions[2]))
        kvar: dict[str,float] = json.loads(h.helicsInputGetString(self.subscriptions[3]))

        ##### insert opt here #####
        if self.controller_name== 'DEFAULT_CONTROLLER':
            peak_hour_start = 3600*13
            peak_hour_end = 3600*20
            if self.time>peak_hour_start and self.time<peak_hour_end:
                ev_control_setpoints = {'evse0':0, 'evse1':0, 'evse2':0}
            else:
                ev_control_setpoints = {'evse0':10000000, 'evse1':10000000, 'evse2':10000000}

            self.control_setpoints = ev_control_setpoints

        # if TOU method, then the charging time and power has already been calculated
        # TODO: figure out ev to evse to load point mapping better. Right now all at transformer are added
        if self.controller_name.startswith('TOU') or self.controller_name.startswith('UNCONTROLLED'):
            # premises = self.charge_events['Premise Number'].unique()
            for k in self.control_setpoints.keys(): self.control_setpoints[k] = 0 #reset setpoints to zero before setting new values
            charge_events = self.charge_events.loc[(self.charge_events['charge_start'] <= cosim_datetime) & (self.charge_events['charge_end'] > cosim_datetime)]
            evs_now_charging = charge_events['Veh_ID_Num'].unique()
            for evse_id in evs_now_charging:
                self.control_setpoints[evse_id] = self.control_setpoints[evse_id] + sum(charge_events[charge_events['Veh_ID_Num'] == evse_id]['charge_power']) #TODO: I think this can be simplified now that we are using vehicle IDs instead of premise numbers..

            ev_control_setpoints = self.control_setpoints
            # print(f'total power ev_control_setpoints {sum(ev_control_setpoints.values())} at time {cosim_datetime}')

        elif self.controller_name in ['FCFS', 'FCFS + SM50', 'EQUAL SHARING']:
            for k in self.control_setpoints:
                self.control_setpoints[k] = 0 #reset setpoints to zero before setting new values
            time_step = timedelta(seconds=self.timestep_sec)
            for trns_id, scm in self.trns_scm.items():
                scm.previous_time_step_base_load_kW = kW[trns_id]
                scm.previous_time_step_base_load_kvar = kvar[trns_id]
                ev_allocated_powers = scm.simulate_step(time_step=time_step)
                for ev, power in ev_allocated_powers.items():
                    self.control_setpoints[ev] = power #if not ev in self.control_setpoints.keys() else (self.control_setpoints[ev] + power)
                scm.current_time += time_step

            # print("Controller sent {} total ev setpoint power for t={}".format(sum(v for v in self.control_setpoints.values()), self.time))

        return ev_control_setpoints

    def advance_time(self, updated_time):
        while self.time < updated_time:
            self.time = h.helicsFederateRequestTime(self.fed, updated_time)

    def output_control_setpoints(self):
        # this function either records setpoints or
        # for co-simulation sends them as a helics publication
        #pd.DataFrame(self.control_setpoints).to_csv(f'{self.name}_setpoints.csv')
        if self.co_simulation:
            h.helicsPublicationPublishString(self.publications[0], json.dumps(self.control_setpoints))
        return

    def export_ev_stats(self):
        ev_stats_df = pd.DataFrame(columns=["ev_id","park_start_timestamp","park_end_timestamp","target_energy_reached","energy_need","energy_charged","energy_capacity"])
        if self.controller_name in ['FCFS', 'FCFS + SM50', 'EQUAL SHARING']:
            for ev in self.scm_evs:
                ev_stats_df = pd.concat([ev_stats_df, pd.DataFrame({"ev_id": [ev.ev_id],"park_start_timestamp": [ev.plug_in_time],"park_end_timestamp": [ev.plug_in_time + timedelta(minutes=ev.duration)], "park_end_after_sim_end": [(ev.plug_in_time + timedelta(minutes=ev.duration)) > self.end_datetime],"target_energy_reached": [ev.energy_charged >= ev.energy_need],"energy_need": [ev.energy_need],"energy_charged": [ev.energy_charged],"energy_capacity": [ev.energy_capacity]})], ignore_index=True)
        else:
            for _, row in self.charge_events.iterrows():
                ev_stats_df = pd.concat([ev_stats_df, pd.DataFrame({"ev_id": [row["Veh_ID_Num"]],"park_start_timestamp": [row["charge_start"]],"park_end_timestamp": [row["charge_end"]], "park_end_after_sim_end": [row["charge_end"] > self.end_datetime],"target_energy_reached": [True],"energy_need": [row["energy_kwh"]],"energy_charged": [row["energy_kwh"]],"energy_capacity": [row["Battery Capacity"]]})], ignore_index=True)

        print("{}/{} unique charging events (not unique EVs) reached their target energy".format(sum(ev_stats_df["target_energy_reached"]),len(ev_stats_df["target_energy_reached"])))
        ev_stats_df.to_csv(EVIDIST_ROOT_PATH + f"/data/temp_sim_plus/sim_plus_ev_charge_stats.csv", index=False)

def get_low_tou_timestamps_for_TOU_alg(start_time, end_time, dow):
    # this function is only needed to get low tou periods for the TOU based controls
    # these functions all assume minute timesteps
    prices = epg.lookup_prices_optimized(start_time=start_time, end_time=end_time, dow=dow)
    #print(f'prices: {prices}')
    periods = epg.periods_based_on_price(prices)
    low_price_period_count = epg.count_lowest_price_periods(prices)
    low_inds = epg.find_low_price_periods_indices(periods) # this outputs a list of tuples
    # turn these into time and add to start of day
    low_timestamps = []
    for ind_pair in low_inds:
        start_ind = ind_pair[0]
        end_ind = ind_pair[1]
        start_minute = int(np.remainder(start_ind,60))
        start_hour = int(np.floor(start_ind/60))
        end_minute = int(np.remainder(end_ind,60))
        end_hour = int(np.floor(end_ind/60))
        start_timestamp = time(hour=start_hour, minute=start_minute)
        end_timestamp = time(hour=end_hour, minute=end_minute)
        low_timestamps.append((start_timestamp, end_timestamp))
    return low_price_period_count, low_timestamps

if __name__ == "__main__":
    # TODO: make these input variables instead of based on order
    # timestep_sec = 300
    # feeder_name = 'ieee_34'
    # charge_event_file = 'data/adoptions/2030/medium.csv' #''
    # controller_name='TOU ALAP' #'default_config' TOU_ALAP #TODO: make this name be an input from simulation_plus.py
    if len(sys.argv)>1:
        timestep_sec = int(sys.argv[1])
    if len(sys.argv)>2:
        sim_name = sys.argv[2]
    if len(sys.argv)>3: # needs to match both directory name and feeder name in charge events file
        feeder_name = sys.argv[3]
    if len(sys.argv)>4: # input charge events csv
        charge_event_file = sys.argv[4]
    if len(sys.argv)>5: # controller type
        controller_name = sys.argv[5]
    if len(sys.argv)>6: # month
        month = int(sys.argv[6])
    if len(sys.argv)>7: # day of week
        dow = int(sys.argv[7])
    sim_start_time = int(sys.argv[8])
    sim_end_time = int(sys.argv[9])
    scm = Controller(sim_name=sim_name, controller_name=controller_name, cosim=True, helics_config_path='',
                    timestep_sec=timestep_sec, feeder_name=feeder_name, charge_event_file=charge_event_file,
                    horizon_sec=24*60*60, month=month, day_of_week=dow,
                    sim_start_time=sim_start_time, sim_end_time=sim_end_time)
    logger.debug('scm object created')
    scm.setup_controller()
    for timestep in np.arange(sim_start_time + timestep_sec/4, sim_end_time + timestep_sec/4, timestep_sec):
        ev_load_limits = scm.run_control_opt()
        scm.output_control_setpoints()
        scm.advance_time(timestep)
        scm.logger.info(f'scm sim federate advanced to {timestep}')
        # print(f"Controller just completed time: {timestep}")

    scm.export_ev_stats()
    # release all
    h.helicsFederateDisconnect(scm.fed)
    h.helicsFederateFree(scm.fed)
    h.helicsCloseLibrary()
