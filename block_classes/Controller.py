import os
import sys
sys.path.append(os.getcwd())
from pathinit import EVIDIST_ROOT_PATH
import pandas as pd
import helics as h
import json
import numpy as np
import datetime
import logging
logger = logging.getLogger(__name__)
import sys
sys.path.append('..')
import os
#parent_directory = os.getcwd()
#sys.path.append(parent_directory + "/modules")
import modules.lite.ev_profile_generation as epg


"""
This class is to hold the controller 
It gets inputs on grid status from the grid sim 
It is initialized with info on electricity pricing and forecasting
It takes inputs on plug-in time, departure time, energy needs from the mobility analysis module
It then does some SCM control and sends those EV control setpoints to the EV Sim
"""

class Controller:
    def __init__(self, name, cosim, helics_config_path, timestep_sec, feeder_name, charge_event_file, horizon_sec, month, day_of_week):
        # controller name options: default_controller: all off during peak, all on during offpeak
        #   TOU_random, TOU_ASAP, TOU_ALAP
        # feeder_name directs to which opendss file to use
        # charge_event_file should have park start and end times, vehicle id with month and day value, transformer number, and premise number, max ac power, energy_kwh
        # day of week starts on monday
        # add important params here
        self.name = name.upper()
        self.feeder_name = feeder_name
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(filename=EVIDIST_ROOT_PATH + f'/logs/sim_plus/{name}.log', encoding='utf-8', level=logging.DEBUG)
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
        self.time = 0
        self.helics_config_path = helics_config_path
        self.fed = None
        self.publications = []
        self.subscriptions = []
        self.year=2024
        self.month = month
        self.day_of_week = day_of_week

    def setup_controller(self):
        # this function loads the pricing, forecast, 
        # loads plug-in time, departure time, and energy needs

        
        ##### insert data loading here #####



        # if it is a co_simulation this sets up the helics federate
        if self.co_simulation:
            if self.helics_config_path == '':
                fedinfo = h.helicsCreateFederateInfo()
                # h.helicsFederateInfoSetCoreName(fedinfo, 'controller')#self.name)
                h.helicsFederateInfoSetCoreInitString(fedinfo, "--federates=1")
                self.fed = h.helicsCreateValueFederate('controller', fedinfo)
                self.publications.append(h.helicsFederateRegisterPublication(self.fed, 'control_setpoints', h.HelicsDataType.STRING)) # this is published as a json string of a dictionary
                self.subscriptions.append(h.helicsFederateRegisterSubscription(self.fed, f'{self.feeder_name}/voltages', ""))
                self.subscriptions.append(h.helicsFederateRegisterSubscription(self.fed, f'{self.feeder_name}/currents', ""))
            else:
                self.fed = h.helicsCreateValueFederateFromConfig(self.helics_config_path)
            h.helicsFederateSetTimeProperty(self.fed, h.helics_property_time_delta, self.timestep_sec)

        # for the TOU heuristic controls, they don't require grid feedback, so 
        # pre-calculate power profiles 
        if self.name.startswith('TOU') or self.name.startswith('UNCONTROLLED'):
            print(f'TOU heuristic controls do not get grid feedback. Precalculating all charge sessions')
            charge_events_input = pd.read_csv(self.charge_event_file)
            charge_events_input = charge_events_input[charge_events_input['month'] == self.month]
            charge_events_input = charge_events_input[charge_events_input['dow'] == self.day_of_week]
            charge_events_input = charge_events_input[charge_events_input['Feeder'] == feeder_name]
            # get pricing from hard coded values

            charge_start = []
            charge_end = []
            charge_events_input['charge_power'] = [min(cvi, 9.6) for cvi in charge_events_input['Max AC Power kW']]
            n_charge_events = len(charge_events_input['charge_power'])
            # calculate the minimum charge time in minutes to feed to the TOU heuristics
            if 'total_charging_time' not in charge_events_input.keys():
                charge_events_input['total_charging_time'] = [cvi_energy/cvi_power*60 for cvi_energy, cvi_power in zip(charge_events_input['charge_power'], charge_events_input['energy_kwh'])]
            # get timestamps for start and end times of the low price periods for each evse
            if 'low_price_period' not in charge_events_input.keys():
                #TODO: date and day of week are not the same
                start_datetime = datetime.datetime(year=self.year, month=self.month, day=self.day_of_week, hour=0,minute=0,second=0)
                low_price_period_count, low_timestamps = get_low_tou_timestamps_for_TOU_alg(start_datetime, self.day_of_week, self.horizon_sec)
                charge_events_input['low_price_period'] = [low_price_period_count]*n_charge_events
                charge_events_input['low_price_timestamps'] = [low_timestamps]*n_charge_events
            # for each charge event, determine the starting charging time
            for _, ce_row in charge_events_input.iterrows():
                park_end_time = datetime.datetime.combine(datetime.datetime.today().replace(hour=0, minute=0, second=0, microsecond=0),datetime.datetime.strptime(ce_row['park_end_timestamp'], '%H:%M:%S').time())
                park_start_time = datetime.datetime.combine(datetime.datetime.today().replace(hour=0, minute=0, second=0, microsecond=0),datetime.datetime.strptime(ce_row['park_start_timestamp'], '%H:%M:%S').time())
                #l2power = min(9.6, ce_row['Max AC Power kW'])
                energy_needed = ce_row['energy_kwh']
                
                if park_end_time < park_start_time:
                    park_end_time = park_end_time + datetime.timedelta(hours = 24)
                    
                if self.name == 'TOU_ALAP':
                    charge_start_time = epg.calculate_charge_start_time_TOU_ALAP(ce_row)
                elif self.name == 'TOU_ASAP':
                    charge_start_time = epg.calculate_charge_start_time_TOU_ASAP(ce_row)
                elif self.name == 'TOU_RANDOM':
                    charge_start_time = epg.calculate_charge_start_time_TOU_random(ce_row)
                else:
                    print(f'WARNING: {self.name} charging control method not recognized, using uncontrolled')
                    charge_start_time = datetime.datetime.strptime(ce_row['park_start_timestamp'], '%H:%M:%S').time()
                charge_start_time = datetime.datetime.combine(datetime.datetime.today().replace(hour=0, minute=0, second=0, microsecond=0),charge_start_time)
                energy_end_time = charge_start_time + datetime.timedelta(minutes = ce_row['total_charging_time'])
                charge_end_time = min(park_end_time, energy_end_time)
                charge_start.append(charge_start_time)
                charge_end.append(charge_end_time)
            charge_events_input['charge_start'] = charge_start
            charge_events_input['charge_end'] = charge_end
            self.charge_events = charge_events_input
            # setup the helics message with 0 power for all
            for evse_id in charge_events_input['Premise Number'].unique():
                self.control_setpoints[int(evse_id)] = 0
        return

    def run_control_opt(self):
        # this function solves the control parameters
        ev_control_setpoints = {}
        cosim_hours = int(np.floor(self.time/3600))
        cosim_minutes = int(np.floor((self.time-cosim_hours*3600)/60))
        cosim_seconds = int(self.time-cosim_hours*3600-cosim_minutes*60)
        cosim_datetime = datetime.datetime.today().replace(hour=0, minute=0, second=0, microsecond=0) + datetime.timedelta(hours=cosim_hours,minutes=cosim_minutes, seconds=cosim_seconds)

        # first get the updated grid status
        voltages = json.loads(h.helicsInputGetString(self.subscriptions[0]))
        currents = json.loads(h.helicsInputGetString(self.subscriptions[1]))

        # TODO: add market control here

        ##### insert opt here #####
        if self.name == 'DEFAULT_CONTROLLER':
            peak_hour_start = 3600*13
            peak_hour_end = 3600*20
            if self.time>peak_hour_start and self.time<peak_hour_end:
                ev_control_setpoints = {'evse0':0, 'evse1':0, 'evse2':0}
            else:
                ev_control_setpoints = {'evse0':10000000, 'evse1':10000000, 'evse2':10000000}

            self.control_setpoints = ev_control_setpoints

        # if TOU method, then the charging time and power has already been calculated
        # TODO: figure out ev to evse to load point mapping better. Right now all at transformer are added
        if self.name.startswith('TOU') or self.name.startswith('UNCONTROLLED'):
            premises = self.charge_events['Premise Number'].unique()
            self.control_setpoints = dict(zip(premises, [0]*len(premises)))
            charge_events = self.charge_events.loc[(self.charge_events['charge_start'] <= cosim_datetime) & (self.charge_events['charge_end'] > cosim_datetime)]
            premises_now_charging = charge_events['Premise Number'].unique()
            for evse_id in premises_now_charging:
                self.control_setpoints[evse_id] = self.control_setpoints[evse_id] + sum(charge_events[charge_events['Premise Number'] == evse_id]['charge_power'])

            ev_control_setpoints = self.control_setpoints
            print(f'total power ev_control_setpoints {sum(ev_control_setpoints.values())} at time {cosim_datetime}')        

        return ev_control_setpoints

    def advance_time(self, updated_time):
        while self.time < updated_time:
            self.time = h.helicsFederateRequestTime(self.fed, updated_time)

    def output_control_setpoints(self):
        # this function either records setpoints or 
        # for co-simulation sends them as a helics publication
        #pd.DataFrame(self.control_setpoints).to_csv(f'{self.name}_setpoints.csv')
        if self.co_simulation:
            if self.time <=0:
                h.helicsFederateEnterExecutingMode(self.fed)
            h.helicsPublicationPublishString(self.publications[0], json.dumps(self.control_setpoints))
        return 
    
    

def get_low_tou_timestamps_for_TOU_alg(datetime_zero, dow, horizon_sec):
    # this function is only needed to get low tou periods for the TOU based controls
    # these functions all assume minute timesteps
    prices = epg.lookup_prices_optimized(start_time=datetime.time(hour=0,minute=0,second=0), end_time=datetime.time(hour=23,minute=59,second=0), dow=dow)
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
        start_timestamp = datetime.time(hour=start_hour, minute=start_minute)
        end_timestamp = datetime.time(hour=end_hour, minute=end_minute)
        low_timestamps.append((start_timestamp, end_timestamp))
    return low_price_period_count, low_timestamps

if __name__ == "__main__":
    # TODO: make these input variables instead of based on order
    timestep_sec = 300
    feeder_name = 'ieee_34'
    charge_event_file = 'data/adoptions/2030/medium.csv' #''
    name='TOU_ALAP' #'default_config' TOU_ALAP #TODO: make this name be an input from simulation_plus.py
    if len(sys.argv)>1:
        timestep_sec = int(sys.argv[1])
    if len(sys.argv)>2: # needs to match both directory name and feeder name in charge events file
        feeder_name = sys.argv[2]
    if len(sys.argv)>3: # input charge events csv
        charge_event_file = sys.argv[3]
    if len(sys.argv)>4: # controller type
        name = sys.argv[4]
    scm = Controller(name=name, cosim=True, helics_config_path='', timestep_sec=timestep_sec, feeder_name=feeder_name, charge_event_file=charge_event_file, horizon_sec=24*60*60, month=1, day_of_week=1)
    logger.debug('scm object created')
    scm.setup_controller()
    for timestep in range(0, 24*3600, 300):
        scm.output_control_setpoints()
        ev_load_limits = scm.run_control_opt()
        scm.advance_time(timestep)
        scm.logger.info(f'scm sim federate advanced to {timestep}')

    # release all
    h.helicsFederateDisconnect(scm.fed)
    h.helicsFederateFree(scm.fed)
    h.helicsCloseLibrary()
