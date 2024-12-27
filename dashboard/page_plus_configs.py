import panel as pn
import param
import asyncio
from styles import custom_style
import pickle
from dataclasses import dataclass
import pandas as pd
import os
import json
from tkinter import Tk, filedialog


class pgPlusConfig(param.Parameterized):

    input_file_names = param.Dict()
    months = param.List()
    days_of_week = param.Dict()
    configs = param.Dict()

    @param.output('input_file_names','configs')
    def output(self):
        input_file_names = {'dss_main' : self.input_file_names['dss_main']}
        input_file_names['premise_report'] = self.input_file_names['premise_report']
        input_file_names['adoption_data'] = self.input_file_names['adoption_data']
        
        configs = {}
        configs['sim_name'] = self.txt_simname.value
        configs['feeder'] = self.select_feeder.value
        configs['controller'] = self.select_control.value
        configs['adoption'] = self.adoption_name
        # self.configs_out['load_profile'] = self.select_profile_gen.value
        configs['month'] = self.select_month.value
        configs['day_of_week'] = self.select_day_of_week.value
        # self.configs['display_res'] = self.select_display_res.value

        return input_file_names, configs
    
    def __init__(self, **params):
        super().__init__(**params)

        # print(self.file_names)
        # print(self.months)

        with open(os.getcwd() + "/data/mappings/mappings_plus.pkl", "rb") as pickle_file:
            self.mappings = pickle.load(pickle_file)

        with open(os.getcwd() + "/data/inputs/adoption_scenarios.json", "rb") as json_file:
            self.json_adoption_scenarios = json.load(json_file) 

        with open(os.getcwd() + "/data/inputs/ev_controllers.json", "rb") as json_file:
            self.json_controllers = json.load(json_file) 

        # with open(os.getcwd() + "/data/inputs/load_profiles.json", "rb") as json_file:
        #     self.json_load_profiles = json.load(json_file) 
       
        feeders = [feeder for feeder in self.mappings['xf_mappings']]
        self.adoption_scenarios = [i for i in self.json_adoption_scenarios]   
        self.controllers = [i for i in self.json_controllers]  
        # self.load_profiles = [i for i in self.json_load_profiles]  
        
        self.feed = feeders[0]
        self.reg = str()
        self.num_xf = int()
        self.num_prem = int()
        self.num_of_ev = int() 
        self.sim_name = self.configs['sim_name']
        self.adoption_name = self.configs['adoption']
        self.display_res = [15,10,5,1]

        self.txt_simname =  pn.widgets.TextInput(name='Enter simulation name', placeholder=self.sim_name)
        self.txt_simname.value = self.sim_name 

        # self.btn_select_file = pn.widgets.Button(name='Browse for AMI data file for selected feeder', button_type='primary', align=('center','center'))
        # self.btn_select_file.on_click(self.select_files)
        # self.selected_file = pn.pane.Markdown("Selected file: ", width=500, renderer='markdown')

        self.select_feeder = pn.widgets.Select(name='Select feeder', options=feeders)
        # self.select_adoption = pn.widgets.Select(name='Select adoption scenario', options=self.adoption_scenarios)
        self.select_control = pn.widgets.Select(name='Select control', options=self.controllers, value=next(iter(self.controllers)), size=len(self.controllers)) #, options=['Uncontrolled', 'TOU ASAP', 'TOU ALAP', 'TOU Random'])
        # self.multi_controller_select = pn.widgets.MultiSelect(name='Select controller(s)', value=['Uncontrolled', 'TOU ASAP'], options=['Uncontrolled', 'TOU ASAP', 'TOU ALAP', 'TOU Random'], size=4)
        # self.select_profile_gen = pn.widgets.Select(name='Select load profile generation', options=self.load_profiles)
        self.select_month = pn.widgets.Select(name='Select the month of simulation', options=self.months)
        self.select_day_of_week = pn.widgets.Select(name='Select the day of week of simulation', options=[d for d in range(1,8,1)])
        # self.select_display_res = pn.widgets.Select(name='Select result display resolution (minute)', options=self.display_res)

        self.info_panel_feeder = self.update_feeder_info(self.feed)
        self.info_panel_control = self.update_controller_info(self.select_control.value)
        # self.info_panel3 = pn.Column(self.update_load_profile_info(self.load_profiles[0]))
        self.info_panel_adoption = self.update_adoption_info(self.adoption_name)

        self.info_feeder_select = pn.pane.Markdown('* <span>Please make sure the AMI data you upload matches the feeder you selected. If no AMI data is selected, the results will only show EV charging profiles.</span>')
        self.info_controller_select = pn.pane.Markdown('* <span>Hold <code>Ctrl</code> to select multiple options. Simulation will be run for each selected controller. Click on a control type to see its description.</span>')

        self.create_callback(self.select_feeder, self.info_panel_feeder, self.update_feeder_info)
        self.create_callback(self.select_control, self.info_panel_control, self.update_controller_info)

    def create_callback(self, select_widget: pn.widgets.Select | pn.widgets.MultiSelect, info_widget, update_fn):
        def on_click(event):
            selected_item = select_widget.value
            #print(selected_item)
            info_widget[:] = [update_fn(selected_item)] 
            # self.info_panel_adoption[:] = [self.update_adoption_info(self.adoption_name)]
        
        select_widget.param.watch(on_click, 'value')

    def update_feeder_info(self, selection):
        
        self.feed = selection
        self.reg = self.mappings['reg_mappings'][self.feed]
        str_reg = ', '.join(self.reg)
        self.num_xf = len(self.mappings['xf_mappings'][self.feed])
        self.num_prem = len(self.mappings['prem_mappings'][self.feed])
        self.num_of_ev = len(self.mappings['veh_mappings'][self.feed])

        info = f"""
        <span style="font-size:12pt;">Selected feeder: </span><span style="font-size:12pt; font-weight: bold;">{self.feed}</span>
        *** 
        - <span style="font-size:11pt;">Region(s):</span> <span style="font-size:11pt; font-weight: bold;">{str_reg}</span>
        - <span style="font-size:11pt;">Number of transformers:</span> <span style="font-size:11pt; font-weight: bold;">{self.num_xf}</span>
        - <span style="font-size:11pt;">Number of premises:</span> <span style="font-size:11pt; font-weight: bold;">{self.num_prem}</span>
        - <span style="font-size:11pt;">Number of EVs:</span> <span style="font-size:11pt; font-weight: bold;">{self.num_of_ev}</span>
        """

        return pn.Column(pn.pane.Markdown(info, width=500, renderer='markdown'))
    
    def update_controller_info(self, selection):

        optional_setting = None
        des = self.json_controllers[selection]['description']       
    
        info = f"""
        <span style="font-size:12pt; display: inline-block; word-wrap: break-word;">EV controller:</span> <span style="font-size:12pt; font-weight: bold;">{selection}</span>
        ***
        <span style="font-size:12pt; font-weight: bold;">Description: </span></span><span style="font-size:11pt;">{des}</span>  
        """

        #return pn.Column(pn.pane.Markdown(info, width=400, renderer='markdown'), pn.Column(optional_setting, align='center'))
        return pn.Column(pn.pane.Markdown(info, width=400, renderer='markdown'))
    
    def update_adoption_info(self, selection):

        info = f"""
        <span style="font-size:12pt; display: inline-block; word-wrap: break-word;">Adoption scenario:</span> <span style="font-size:12pt; font-weight: bold;">{selection}</span>
        """

        return pn.Column(pn.pane.Markdown(info, width=400, renderer='markdown'))

    b = param.Integer()
    files = param.List()

    @param.depends('b', 'files')
    def panel(self):       
        
        app = pn.Column(
            pn.Row(
                pn.Column(
                self.txt_simname,
                self.select_month,
                self.select_day_of_week,
                ),
                self.info_panel_adoption,
                width=350,
            ),
            pn.Row(
                pn.Column(
                    self.select_feeder,
                    self.info_feeder_select,
                    width=350,
                ),
                self.info_panel_feeder,
                width=700,
            ),
            pn.Row(
                pn.Column(
                    self.select_control,
                    # self.info_controller_select,
                    width=350
                ),
                self.info_panel_control,
                width=900,
            ),
        )                                                    

        return app
    
        

