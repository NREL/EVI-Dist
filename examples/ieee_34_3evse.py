"""
This example file runs a very basic grid and EV control co-simulation
The grid model is the IEEE 34 bus feeder with three EVSE connected.
The loads are taken from 
The EVSE controller turns the load on at 00:00, off at 15:00, on again at 21:00
"""
import sys
import os
import subprocess
import multiprocessing
from multiprocessing import Process, Pool
sys.path.append('../')
import helics as h

# the below classes are in the ../block_classes directory
sys.path.insert(1, '../block_classes')
from GridSim import GridSim
from EVChargeSim import EVChargeSim
from Controller import Controller

# create a helics broker in the command prompt
#hbroker = h.helicsCreateBroker(type='zmq')
subprocess.Popen(['helics_broker', '-f2', '-tzmq'])
#os.spawnv(os.P_NOWAIT, 'helics_broker', ['-f3', '-tzmq', '--logging=debug'])
print('broker started')

subprocess.Popen(['python', 'GridSim.py'])
#os.spawnv(os.P_NOWAIT, 'python', ['GridSim.py'])
print('ieee34bus grid sim started')

subprocess.Popen(['python', 'EVChargeSim.py'])
#os.spawnv(os.P_NOWAIT, 'python', ['EVChargeSim.py'])
print('charging simulation started')

subprocess.Popen(['python', 'Controller.py'])
#os.spawnv(os.P_NOWAIT, 'python', ['Controller.py'])
print('controller started')
"""
# initialize the module classes
ieee_34_feeder = GridSim(opendss_path='../inputs/opendss_model/ieee34.dss') #, helics_config_path='../inputs/helics_configs/opendss_helics_config.json', cosim=True)
print('ieee_34 object created')
charge_sim = EVChargeSim(cosim=True) #helics_config_path='../inputs/helics_configs/ev_charge_sim_helics_config.json', cosim=True)
print('charge sim object created')
scm = Controller(cosim=True)
print('scm object initialized')

# start them as federates on independent processes so they don't hang waiting for each other
#pool = Pool(processes=2)
#p_feeder = Process(ieee_34_feeder.setup_opendss_model()) #pool.apply_async(ieee_34_feeder.setup_opendss_model())

print('ieee_34 federate setup')
#p_feeder.start()
print('running feeder model federate')

#p_scm = Process(scm.setup_charge_sim()) #pool.apply_async(scm.setup_charge_sim())
#print('scm federate setup')
#p_scm.start()
#print('running scm federate')
# set up loop for whole day

day = 24*3600
delta_t = 3600
for timestep in range(1,day,delta_t):
    # publish and subscribe to values
    scm.output_control_setpoints()
    ieee_34_feeder.output_grid_values()

    # update simulation based on subscriptions
    ev_load_limits = scm.run_charge_sim()
    ieee_34_feeder.update_ev_loads()
    
    # advance time:
    ieee_34_feeder.advance_sim_time(timestep)
    scm.advance_scm_time(timestep)
    print(f'timestep {timestep} completed')
# close out the broker
#hbroker.close()
#pool.close()
#pool.join()

"""