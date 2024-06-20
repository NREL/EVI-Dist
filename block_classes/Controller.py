import pandas as pd
import helics as h
import json
import numpy as np
import logging
logger = logging.getLogger(__name__)

"""
This class is to hold the controller 
It gets inputs on grid status from the grid sim 
It is initialized with info on electricity pricing and forecasting
It takes inputs on plug-in time, departure time, energy needs from the mobility analysis module
It then does some SCM control and sends those EV control setpoints to the EV Sim
"""

class Controller:
    def __init__(self, name='default_controller', cosim=False, helics_config_path='', timestep_sec=60*5):
        # add important params here
        self.name = name
        logging.basicConfig(filename=f'{name}.log', encoding='utf-8', level=logging.DEBUG)
        self.pricing = []
        self.baseload_forecast = []
        self.charge_events = []
        self.control_setpoints = {'evse0':0, 'evse1':0, 'evse2':0}
        self.voltages = []
        # these are for if you want time-step based sim
        self.timestep_sec = timestep_sec
        self.co_simulation = cosim
        self.time = -1
        self.helics_config_path = helics_config_path
        self.fed = None
        self.publications = []
        self.subscriptions = []

    def setup_controller(self):
        # this function loads the pricing, forecast, 
        # loads plug-in time, departure time, and energy needs

        
        ##### insert data loading here #####



        # if it is a co_simulation this sets up the helics federate
        if self.co_simulation:
            if self.helics_config_path == '':
                fedinfo = h.helicsCreateFederateInfo()
                h.helicsFederateInfoSetCoreName(fedinfo, self.name)
                h.helicsFederateInfoSetCoreInitString(fedinfo, "--federates=1")
                self.fed = h.helicsCreateValueFederate(self.name, fedinfo)
                self.publications.append(h.helicsFederateRegisterPublication(self.fed, 'control_setpoints', h.HelicsDataType.STRING)) # this is published as a json string of a dictionary
                self.subscriptions.append(h.helicsFederateRegisterSubscription(self.fed, 'ieee_34/voltages', ""))
                self.subscriptions.append(h.helicsFederateRegisterSubscription(self.fed, 'ieee_34/currents', ""))
            else:
                self.fed = h.helicsCreateValueFederateFromConfig(self.helics_config_path)
            h.helicsFederateSetTimeProperty(self.fed, h.helics_property_time_delta, self.timestep_sec)

            h.helicsFederateEnterExecutingMode(self.fed)
        return

    def run_control_opt(self):
        # this function solves the control parameters
        ev_control_setpoints = {}

        # first get the updated grid status
        voltages = json.loads(h.helicsInputGetString(self.subscriptions[0]))
        currents = json.loads(h.helicsInputGetString(self.subscriptions[1]))

        ##### insert opt here #####
        peak_hour_start = 3600*13
        peak_hour_end = 3600*20
        if self.time>peak_hour_start and self.time<peak_hour_end:
            ev_control_setpoints = {'evse0':0, 'evse1':0, 'evse2':0}
        else:
            ev_control_setpoints = {'evse0':10000000, 'evse1':10000000, 'evse2':10000000}

        self.control_setpoints = ev_control_setpoints
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


if __name__ == "__main__":
    scm = Controller(helics_config_path='', cosim=True)
    logger.debug('scm object created')
    scm.setup_controller()
    for timestep in range(1, 24*3600, 3600):
        scm.output_control_setpoints()
        ev_load_limits = scm.run_control_opt()
        scm.advance_time(timestep)
        logger.info(f'scm sim federate advanced to {timestep}')