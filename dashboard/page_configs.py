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


# Month January does not have ami data for MEAD 2104
# Therefore, it shows the baseload as 0

class pgConfig(param.Parameterized):

    file_names = param.Dict()
    months = param.List()
    configs = param.Dict()

    @param.output('file_names','configs')
    def output(self):
        self.configs = {}
        self.configs['feeder'] = self.select_feeder.value
        self.configs['controller'] = self.multi_controller_select.value
        self.configs['adoption'] = self.txt_adoption.value
        self.configs['load_profile'] = self.select_profile_gen.value
        self.configs['ami_data_file'] = self.selected_file.object
        if self.configs['ami_data_file'] == "Selected file: ":
            self.configs['ami_data_file'] = "No file selected"
        self.configs['month'] = self.select_month.value

        return self.file_names, self.configs
    
    def __init__(self, **params):
        super().__init__(**params)

        # print(self.file_names)
        # print(self.months)

        with open(os.getcwd() + "/data/mappings/mappings.pkl", "rb") as pickle_file:
            self.mappings = pickle.load(pickle_file)

        with open(os.getcwd() + "/data/inputs/adoption_scenarios.json", "rb") as json_file:
            self.json_adoption_scenarios = json.load(json_file) 

        with open(os.getcwd() + "/data/inputs/ev_controllers.json", "rb") as json_file:
            self.json_controllers = json.load(json_file) 

        with open(os.getcwd() + "/data/inputs/load_profiles.json", "rb") as json_file:
            self.json_load_profiles = json.load(json_file) 
       
        feeders = [feeder for feeder in self.mappings['xf_mappings']]
        self.adoption_scenarios = [i for i in self.json_adoption_scenarios]   
        self.controllers = [i for i in self.json_controllers]  
        self.load_profiles = [i for i in self.json_load_profiles]  
        
        self.feed = feeders[0]
        self.reg = str()
        self.num_xf = int()
        self.num_prem = int()
        self.num_of_ev = int() 
        self.adoption_name = "Untitled"

        self.txt_adoption =  pn.widgets.TextInput(name='Name adoption scenario', placeholder='Untitled', align=('center','center'))
        self.txt_adoption.value = self.adoption_name 

        self.btn_select_file = pn.widgets.Button(name='Browse for AMI data file for selected feeder', button_type='primary', align=('center','center'))
        self.btn_select_file.on_click(self.select_files)
        self.selected_file = pn.pane.Markdown("Selected file: ", width=500, renderer='markdown')

        self.select_feeder = pn.widgets.Select(name='Select feeder', options=feeders)
        self.select_adoption = pn.widgets.Select(name='Select adoption scenario', options=self.adoption_scenarios)
        self.select_control = pn.widgets.Select(name='Select EV control', options=self.controllers)
        self.multi_controller_select = pn.widgets.MultiSelect(name='Select controller(s)', value=['Uncontrolled', 'TOU ASAP'], options=['Uncontrolled', 'TOU ASAP', 'TOU ALAP', 'TOU Random'], size=4)
        self.select_profile_gen = pn.widgets.Select(name='Select load profile generation', options=self.load_profiles)
        self.select_month = pn.widgets.Select(name='Select the month of simulation', options=self.months)
        
        self.info_panel1 = pn.Column(self.update_feeder_info(self.feed))
        self.info_panel2 = pn.Column(self.update_controller_info(self.controllers))
        self.info_panel3 = pn.Column(self.update_load_profile_info(self.load_profiles[0]))
        self.info_panel4 = pn.Column(self.update_adoption_info(self.adoption_name))

        self.info_feder_select = pn.pane.Markdown('* <span>Please make sure the AMI data you upload matches the feeder you selected. If no AMI data is selected, the results will only show EV charging profiles.</span>')
        self.info_controller_select = pn.pane.Markdown('* <span>Hold <code>Ctrl</code> to select multiple options. Simulation will be run for each selected controller. Click on a control type to see its description.</span>')

        self.create_callback(self.select_feeder, self.info_panel1, self.update_feeder_info)
        self.create_callback(self.select_control, self.info_panel2, self.update_controller_info)
        self.create_callback(self.select_profile_gen, self.info_panel3, self.update_load_profile_info)
        self.create_callback(self.multi_controller_select, self.info_panel2, self.update_controller_info)

        self.txt_adoption.param.watch(self.text_input_changed, 'value')

    def text_input_changed(self, event):
        self.adoption_name = self.txt_adoption.value
        #print(self.adoption_name)
        self.info_panel4[:] = [self.update_adoption_info(self.adoption_name)]

    def create_callback(self, select_widget, info_widget, update_fn):
        def on_click(event):
            selected_item = select_widget.value
            #print(selected_item)
            info_widget[:] = [update_fn(selected_item)] 
            self.info_panel4[:] = [self.update_adoption_info(self.adoption_name)]
        
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
        """  
        # - <span style="font-size:11pt;">Number of EVs:</span> <span style="font-size:11pt; font-weight: bold;">{self.num_of_ev}</span>

        return pn.Column(pn.pane.Markdown(info, width=500, renderer='markdown'))
    
    def update_controller_info(self, selection):

        optional_setting = None
        #print(selection)
        des = self.json_controllers[selection[0]]['description']       

        if selection[0] == 'Uncontrolled':
            
            optional_setting = pn.panel(pn.widgets.FloatSlider(name='Cap charging power (%)', start=0, end=100, step=1, value=0), sizing_mode='stretch_width')
        elif selection[0] == 'TOU ASAP':
            
            optional_setting = pn.panel(pn.widgets.IntRangeSlider(name='Peak period (hour)', start=0, end=24, value=(15, 19), step=1), sizing_mode='stretch_width', bar_color='#e92f08') 
        elif selection[0] == 'TOU ALAP':
            
            optional_setting = pn.panel(pn.widgets.IntRangeSlider(name='Peak period (hour)', start=0, end=24, value=(15, 19), step=1), sizing_mode='stretch_width', bar_color='#e92f08')       
        elif selection[0] == 'TOU Random':
            
            optional_setting = pn.panel(pn.widgets.IntRangeSlider(name='Peak period (hour)', start=0, end=24, value=(15, 19), step=1), sizing_mode='stretch_width', bar_color='#e92f08')   
        elif selection[0] == 'Coordinated':
            None
            
        
        info = f"""
        <span style="font-size:12pt; display: inline-block; word-wrap: break-word;">EV controller:</span> <span style="font-size:12pt; font-weight: bold;">{selection[0]}</span>
        ***
        <span style="font-size:12pt; font-weight: bold;">Description: </span></span><span style="font-size:11pt;">{des}</span>  
        """

        #return pn.Column(pn.pane.Markdown(info, width=400, renderer='markdown'), pn.Column(optional_setting, align='center'))
        return pn.Column(pn.pane.Markdown(info, width=400, renderer='markdown'))

    
    def update_load_profile_info(self, selection):

        des = self.json_load_profiles[selection]['description']
        
        info = f"""
        <span style="font-size:12pt; display: inline-block; word-wrap: break-word;">Load profile generation:</span> <span style="font-size:12pt; font-weight: bold;">{selection}</span>
        ***
        <span style="font-size:12pt; font-weight: bold;">Description: </span></span><span style="font-size:11pt;">{des}</span>  
        """

        return pn.Column(pn.pane.Markdown(info, width=500, renderer='markdown'), self.btn_select_file, self.selected_file)
    
    def update_adoption_info(self, selection):

        info = f"""
        <span style="font-size:12pt; display: inline-block; word-wrap: break-word;">Adoption scenario:</span> <span style="font-size:12pt; font-weight: bold;">{selection}</span>
        ***
        <span style="font-size:11pt">Based on the uploaded adoption scenario file, the number of EVs to be simulated for this feeder is <b>{self.num_of_ev}</b>.</span>
        """

        return pn.Column(pn.pane.Markdown(info, width=400, renderer='markdown'), self.txt_adoption)

    def select_files(self, event):
        root = Tk()
        root.withdraw()                                        
        root.call('wm', 'attributes', '.', '-topmost', True)   
        file_name = filedialog.askopenfilename(multiple=False)    
        self.selected_file.object = file_name

    b = param.Integer()
    files = param.List()

    @param.depends('b', 'files')
    def panel(self):

        

        selection_column = pn.Column(self.select_feeder,
                                     self.info_feder_select,
                                     self.multi_controller_select,
                                     self.info_controller_select,
                                     self.select_month,
                                     width=350)

        description_top_row = pn.Row(self.info_panel1,
                                     self.info_panel2)  

        description_bottom_row = pn.Row(self.info_panel3,
                                        self.info_panel4)   

        description = pn.Column(description_top_row, description_bottom_row) 
        final = pn.Row(selection_column, description)                                                                      

        # left_1 = pn.Spacer(height=250, width=200, styles={'flex': '1 1 auto'})
        # middle_1 = pn.Row(
        #             pn.Column(
        #             self.select_feeder,
        #             self.info_feder_select,
        #             #self.select_control,
        #             self.multi_controller_select,
        #             self.info_controller_select,
        #             self.select_profile_gen,
        #             height=500,
        #             width=350),
        #             pn.Row(
        #             self.info_panel1,
        #             self.info_panel2),
        #             styles={'flex': '3 1 auto'}
        #             )                
        
        # right_1 = pn.Spacer(height=250, width=200, styles={'flex': '1 1 auto'})

        
        # left_2 = pn.Spacer(height=250, width=200, styles={'flex': '1 1 auto'})
        # middle_2 = pn.Row(
        #             pn.Column(
        #             height=500,
        #             width=350),
        #             pn.Row(
        #             self.info_panel3,
        #             self.info_panel4),
        #             styles={'flex': '3 1 auto'}
        #             )                
        
        # right_2 = pn.Spacer(height=250, width=200, styles={'flex': '1 1 auto'})


        # top_row = pn.Row(left_1, middle_1, right_1)
        # bottom_row = pn.Row(left_2, middle_2, right_2)

        # final_pane = pn.Column(top_row, bottom_row)

        return final
    
        

