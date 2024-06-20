import pandas as pd
import helics as h
import json

import logging
logger = logging.getLogger(__name__)

"""
This class is to hold the EV Sim 
It gets inputs on ev control setpoint from the controller
It is initialized with info on EV demand from the mobility analysis
It is also intialized with data on charge profiles for specific ev types from lab testing
It then figures out how the vehicles charge within setpoint parameters and
outputs ev loads
"""

class EVChargeSim:
    def __init__(self, name='ev_charge_sim', cosim=False, helics_config_path='', timestep_sec=60*5):
        # add important params here
        self.name = name
        logging.basicConfig(filename=f'{name}.log', encoding='utf-8', level=logging.DEBUG)
        self.ev_demand = {}
        self.charge_profile_library = {}
        self.ev_loads = {'evse0':10, 'evse1':10, 'evse2':10}
        self.control_setpoints = {}
        # these are for if you want time-step based sim
        self.timestep_sec = timestep_sec
        self.co_simulation = cosim
        self.time = -1
        self.helics_config_path = helics_config_path
        self.fed = None
        self.publications = []
        self.subscriptions = []

    def setup_charge_sim(self):
        # this function loads ev demand and charge profiles into a library

        ##### insert data loading here #####

        # if it is a co_simulation this sets up the helics federate
        if self.co_simulation:
            if self.helics_config_path == '':
                fedinfo = h.helicsCreateFederateInfo()
                h.helicsFederateInfoSetCoreName(fedinfo, self.name)
                h.helicsFederateInfoSetCoreInitString(fedinfo, "--federates=1")
                self.fed = h.helicsCreateValueFederate(self.name, fedinfo)
                self.publications.append(h.helicsFederateRegisterPublication(self.fed, 'ev_loads', h.HelicsDataType.STRING)) # this is published as a json string of a dictionary
                self.subscriptions.append(h.helicsFederateRegisterSubscription(self.fed, 'default_controller/control_setpoints', ""))
            else:
                self.fed = h.helicsCreateValueFederateFromConfig(self.helics_config_path)
            h.helicsFederateSetTimeProperty(self.fed, h.helics_property_time_delta, self.timestep_sec)

            h.helicsFederateEnterExecutingMode(self.fed)
        return

    def run_charge_sim(self, timestep=0):
        # this function uses the profile library and setpoints to determin the actual ev loads
        ev_loads = {'evse0':10, 'evse1':10, 'evse2':10}

        ##### insert load solver here #####

        # rules based all on or all off based on time
        for evse, limit in self.control_setpoints.items():
            self.ev_loads[evse] = min(ev_loads[evse], limit)

        return ev_loads

    def advance_time(self, updated_time):
        while self.time < updated_time:
            self.time = h.helicsFederateRequestTime(self.fed, updated_time)

    def output_charger_load(self):
        # this function either records setpoints or 
        # for co-simulation sends them as a helics publication
        #pd.DataFrame(self.ev_loads).to_csv(f'{self.name}_evloads.csv')
        if self.co_simulation:
            h.helicsPublicationPublishString(self.publications[0], json.dumps(self.ev_loads))
            control_setpoints = json.loads(h.helicsInputGetString(self.subscriptions[0]))
            if not isinstance(control_setpoints, float):
                logger.info(f'ev setpoints: {control_setpoints}')
                self.control_setpoints = control_setpoints
            else:
                logger.warning(f'recieved float for control_setpoints, continuing without updating')
        return 


if __name__ == "__main__":
    evse = EVChargeSim(helics_config_path='', cosim=True)
    logger.debug('charge sim object created')
    evse.setup_charge_sim()
    for timestep in range(1, 24*3600, 3600):
        evse.output_charger_load()
        ev_load_limits = evse.run_charge_sim()
        evse.advance_time(timestep)
        logger.info(f'charge sim federate advanced to {timestep}')