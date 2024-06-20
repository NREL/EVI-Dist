import panel as pn
from tkinter import Tk, filedialog
import param
import pandas as pd
import numpy as np
import datetime as dt
import folium
from bokeh.models.widgets.tables import NumberFormatter, BooleanFormatter
from ipyleaflet import Map as LeafletMap, Marker as LeafletMarker, MarkerCluster as LeafletCluster
from folium.plugins import MarkerCluster
from jinja2 import Template
from folium.map import Marker as FoliumMarker
import plotly.graph_objs as go
import plotly.express as px
import os
from gen_text_stats import gen_text_stats

from actions import DataOperator 
import matplotlib.pyplot as plt
from datetime import datetime

from plots import LinePlot, gen_plot_object
from tables import Table
from maps import Map
from collections import namedtuple

import pickle
import sys

parent_directory = os.getcwd()

sys.path.append(parent_directory + "\\modules")

from data_structures import Signal
      
class pgDisplay(param.Parameterized):
     
    file_names = param.Dict()
    configs = param.Dict()

    def __init__(self, **params):
        super().__init__(**params)

        # print(self.file_names)
        # print(self.configs)
       
        paths = {}
        paths['premise_report'] = self.file_names['premise_report']
        paths['ev_adoption'] = self.file_names['ev_adoption']
        paths['baseload_profiles'] = parent_directory + "\\data\\temp\\baseload_profiles.csv"
        paths['ev_profiles'] = dict()
        
        for cntl in self.configs['controller']:
            paths['ev_profiles'][cntl] = parent_directory + "\\data\\temp\\ev_profiles_" + cntl + ".csv"
        
        paths['mappings'] = parent_directory + "\\data\\mappings\\mappings.pkl"
        
        #self.dop = DataOperator(paths, self.configs['feeder'], self.configs['controller']) 
        self.dop = DataOperator(paths, self.configs) 

        self.pane_timeseries = pn.pane.Plotly()
        self.pane_comparison = pn.pane.Plotly()
        self.pane_histogram = pn.pane.Plotly()

        self.toggle_feeder_plots = pn.widgets.Switch(name='switch')
        self.select_controller = pn.widgets.Select(name='Select controller', options=self.configs['controller'])


        self.table = self.dop.get_table()
        self.obj_map = Map([39.638143, -104.788596], self.table)  ################  THIS NEEDS TO BE FIXED
        self.folium_pane = self.obj_map.map

        self.obj_table = Table(self.table.loc[:, ['Transformer ID', 'Bank Size', 'OH/UG', 'Bank Configuration', 'Output Voltage']])
        self.premise_table = self.obj_table.table

        self.pane_stats = pn.Column(height=500) 

        self.month_dict = {
            1: 'January',
            2: 'February',
            3: 'March',
            4: 'April',
            5: 'May',
            6: 'June',
            7: 'July',
            8: 'August',
            9: 'September',
            10: 'October',
            11: 'November',
            12: 'December'
        }

        starting_index = int()
        for index, row in self.table.iterrows():
            
            if str(row['Transformer ID']) in self.dop.base_load.columns:
                #print(f"{row['Transformer ID']} exists, index = {index}")
                starting_index = index
                break
            else:
                None
                #print(f"{row['Transformer ID']} does not exists, index = {index}")

        self.selected_row = self.table.iloc[[starting_index]] 


    def get_selected_xf(self, xf_id, threshold):  

        if self.toggle_feeder_plots.value:  
            baseload = self.dop.get_feeder_load()
            ev_load = self.dop.get_agg_ev_load_by_feeder(self.select_controller.value)
            ev_load_comp = self.dop.get_agg_ev_load_by_feeder_comparison()
            title = "Feeder level"
        else:
            baseload = self.dop.get_base_load_by_xf_id(xf_id)
            ev_load = self.dop.get_agg_ev_load_by_xf_id(xf_id, self.select_controller.value)
            ev_load_comp = self.dop.get_agg_ev_load_by_xf_id_comparison(xf_id)
            title = 'XF ID: ' + str(xf_id)

        # time = np.arange(len(baseload))
        time = self.dop.get_time(self.select_controller.value)

        signal_base_load = Signal(time, baseload, 'Baseload', 60, ('m','kW'))
        signal_ev_load = Signal(time, ev_load, 'EV load', 60, ('m','kW'))

        signal_ev_load_comp = dict()
        signal_combined_load_comp = dict()
        for cntrl in self.configs['controller']:
            signal_ev_load_comp[cntrl] = Signal(time, ev_load_comp[cntrl], cntrl, 60, ('m','kW'))
            signal_combined_load_comp[cntrl] = signal_base_load + signal_ev_load_comp[cntrl]
            signal_combined_load_comp[cntrl].name =  cntrl       

        signal_combined_load = signal_base_load + signal_ev_load
        signal_combined_load.name = 'Baseload+EV'

        if not self.toggle_feeder_plots.value:
            dataset = {'baseload' : signal_base_load.y, 'evload' : signal_ev_load.y, 'total' : signal_combined_load.y, 'ID' : str(xf_id)}
            gen_text_stats(self.pane_stats, dataset, self.dop, threshold, self.select_controller.value)   
        else:
            self.pane_stats[:] = [pn.Column("""Turn off **Feeder level plots** to see statistics for individual transformers.""")]

        x = float(self.selected_row['Longitude_X'])
        y = float(self.selected_row['Latitude_Y'])

        # self.obj_map.m.fit_bounds([[y-0.001/2, x-0.001/2], [y+0.001/2, x+0.001/2]]) ##############################  Will be updated
        # self.obj_map.m.fit_bounds([[y-0.001/2, x-0.001/2], [y+0.001/2, x+0.001/2]]) ##############################  Will be updated
        
        self.obj_map.m.fit_bounds([[y-0.0001, x-0.0001], [y+0.0001, x+0.0001]]) ##############################  Will be updated
        self.obj_map.m.fit_bounds([[y-0.0001, x-0.0001], [y+0.0001, x+0.0001]]) ##############################  Will be updated
        self.folium_pane.object = self.obj_map.m
  
        param_for_timeseries = dict()
        param_for_timeseries['type'] = 'timeseries'
        param_for_timeseries['xlabel'] = f"Time (day) in {self.month_dict[self.configs['month']]}"
        param_for_timeseries['ylabel'] = 'Power [kVA]'
        param_for_timeseries['title'] = title
        param_for_timeseries['theme'] = 'plotly_white' if pn.config.theme == 'default' else 'plotly_dark'
        param_for_timeseries['width'] = 650
        param_for_timeseries['height'] = 425
        param_for_timeseries['fontsize'] = 14

        param_for_histogram = dict()
        param_for_histogram['type'] = 'histogram'
        param_for_histogram['xlabel'] = 'Power [kVA]'
        param_for_histogram['ylabel'] = 'Counts'
        param_for_histogram['title'] = title
        param_for_histogram['theme'] = 'plotly_white' if pn.config.theme == 'default' else 'plotly_dark'
        param_for_histogram['width'] = 650
        param_for_histogram['height'] = 425
        param_for_histogram['fontsize'] = 14

        obj_timeseries = gen_plot_object(signal_base_load, param_for_timeseries)
        obj_timeseries.add_trace(signal_combined_load, color_seq=1)
        obj_timeseries.add_trace(signal_ev_load, color_seq=2)
        fig_timeseries = obj_timeseries.gen_plot()
        
        obj_comparison = gen_plot_object(signal_combined_load_comp[self.configs['controller'][0]], param_for_timeseries)
        for i in range(1, len(self.configs['controller'])):
            obj_comparison.add_trace(signal_combined_load_comp[self.configs['controller'][i]], color_seq=i)
        fig_comparsion = obj_comparison.gen_plot()

        obj_histogram = gen_plot_object(signal_base_load, param_for_histogram)
        obj_histogram.add_trace(signal_combined_load, color_seq=1)
        obj_histogram.add_trace(signal_ev_load, color_seq=2)
        fig_histogram = obj_histogram.gen_plot()

        self.pane_timeseries.object = fig_timeseries
        self.pane_histogram.object = fig_histogram 
        self.pane_comparison.object = fig_comparsion

    def panel(self):

        #print(pn.config.theme)

        ####### PLOTLY WIDGET #######

        #print(int(self.selected_row['Transformer ID']), int(self.selected_row['Bank Size']))
        self.get_selected_xf(int(self.selected_row['Transformer ID']), threshold=int(self.selected_row['Bank Size'])) 


        def click(self, event):

            self.selected_row = self.table.iloc[event.row]
            threshold = int(self.selected_row['Bank Size'])
            xf = int(self.selected_row['Transformer ID'])
            x = self.selected_row['Longitude_X']            
            y = self.selected_row['Latitude_Y']  

            if event.column == 'Transformer ID':
                self.get_selected_xf(xf, threshold)

        self.premise_table.on_click(lambda event: click(self, event))

        def on_toggle(event):
            self.get_selected_xf(int(self.selected_row['Transformer ID']), threshold=int(self.selected_row['Bank Size'])) 

        def on_select(event):
            self.get_selected_xf(int(self.selected_row['Transformer ID']), threshold=int(self.selected_row['Bank Size'])) 
            # Update results for the selected controller

        settings1 = pn.Column(pn.Row(pn.widgets.StaticText(value='Show feeder level plots'), self.toggle_feeder_plots, self.select_controller), self.pane_timeseries)
        settings2 = pn.Column(pn.Row(pn.widgets.StaticText(value='Show feeder level plots'), self.toggle_feeder_plots, self.select_controller), self.pane_histogram)
        settings3 = pn.Column(pn.Row(pn.widgets.StaticText(value='Show feeder level plots'), self.toggle_feeder_plots), self.pane_comparison)

        self.toggle_feeder_plots.param.watch(on_toggle, 'value')
        self.select_controller.param.watch(on_select, 'value')

        ###### SYSTEM STATES ######
        # try:
        #     res_id = int(pn.state.session_args.get('res_id')[0])
        #     print(res_id)
        # except Exception:
        #     phase = 1

        ###### CREATE TABS #######

        css = """
        .center-content .bk {
            display: flex;
            justify-content: center;
            align-items: center;
        }
        """
        pn.config.raw_css.append(css)

        if self.configs['adoption'] == "":
            self.configs['adoption'] = "Untitled"

        pane_des = pn.pane.Markdown(f"""<span style="font-size:12pt">Feeder: <b>{self.configs['feeder']}</b>, Controller: <b>{self.configs['controller']}</b>, Adoption: <b>{self.configs['adoption']}</b>,  Load profile: <b>{self.configs['load_profile']}</b>
                                        </span>""")
        
        tabs = pn.Tabs(('Time series', settings1), ('Comparison', settings3), ('Histogram', settings2), ('Stats', pn.Column(pn.Row(pn.widgets.StaticText(value='Show feeder level plots'), self.toggle_feeder_plots, self.select_controller), self.pane_stats)), ('Location', self.folium_pane))

        left = pn.Spacer(height=500, styles={'flex': '1 1 auto'})
        middle = pn.Row(
                    self.premise_table, 
                    tabs,
                    styles={'flex': '2 1 auto'},
                    )                
        
        right = pn.Spacer(height=500, styles={'flex': '1 1 auto'})

        app = pn.Column(pane_des, pn.Row(self.premise_table, tabs))
        # gspec = pn.GridSpec(height=800)
        # gspec[:,   0  ] = pn.Spacer()
        # gspec[:,   1:6] = self.premise_table
        # gspec[:,   6:11] = tabs
        # gspec[:,   11  ] = pn.Spacer()
        #app = pn.Column(pane_des, gspec)
        
        return app
