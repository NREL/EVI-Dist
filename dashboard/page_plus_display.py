import os
import sys
sys.path.append(os.getcwd())
from pathinit import EVIDIST_ROOT_PATH
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
from gen_text_stats import gen_text_stats
import json
import io
import zipfile

from actions import DataOperatorPlus
import matplotlib.pyplot as plt
from datetime import datetime

from plots import LinePlot, gen_plot_object
from tables import Table
from maps import Map
from collections import namedtuple

import pickle

from modules.data_structures import Signal
      
class pgPlusDisplay(param.Parameterized):
     
    file_names: param.Dict = param.Dict()
    configs: param.Dict = param.Dict()
    
    ready = param.Boolean(default=False)

    def __init__(self, **params):
        super().__init__(**params)
        
        # self.file_names = params['file_names']
        self.paths = {}
        
        self.paths['evloads'] = self.file_names['evloads']
        self.paths['linecurrents'] = self.file_names['linecurrents']
        self.paths['linedata'] = self.file_names['linedata']
        self.paths['trnscurrents'] = self.file_names['trnscurrents']
        self.paths['trnskva'] = self.file_names['trnskva']
        self.paths['trnskva_ratings'] = self.file_names['trnskva_ratings']
        self.paths['voltages'] = self.file_names['voltages']
        self.paths['bus_info'] = self.file_names['bus_info']
        # self.paths['ev_profiles'] = dict()
    
        self.dop = DataOperatorPlus(self.paths)#self.paths, self.configs) 

        self.tbl_ev_loads = pn.widgets.Tabulator(self.dop.get_evloads(), height=400, width=700, pagination=None, disabled=True)
        
        ##Summary section
        # tables
        self.tbl_trns_max_load = pn.widgets.Tabulator(self.dop.get_trns_max_load_summary(), pagination=None, disabled=True, show_index=False, height=400, width=400)
        self.tbl_lines_max_load = pn.widgets.Tabulator(self.dop.get_lines_max_load_summary(), pagination=None, disabled=True, show_index=False, height=400, width=400)
        self.tbl_pcc_min_voltage = pn.widgets.Tabulator(self.dop.get_pcc_min_voltage_summary(), pagination=None, disabled=True, show_index=False, height=400, width=400)
        # plots   
        self.bar_trns_loading_count = self.gen_bar_trns_loading()
        self.bar_lines_loading_count = self.gen_bar_lines_loading()
        self.hist_pcc_min_voltage = self.gen_hist_pcc_min_voltage()
        #buttons and sliders
        self.trns_loading_slider = pn.widgets.IntSlider(name='Transformer Loading Cut-off', start=0, end=200, step=1, value=100)
        self.trns_loading_button = pn.widgets.Button(name='Apply', button_type='primary')
        self.lines_loading_slider = pn.widgets.IntSlider(name='Lines Loading Cut-off', start=0, end=200, step=1, value=100)
        self.lines_loading_button = pn.widgets.Button(name='Apply', button_type='primary')
        
        #Individual elements section
        self.tbl_trns_summary = pn.widgets.Tabulator(self.dop.get_trns_tbl_df(),
                                                    pagination=None,
                                                    disabled=True,
                                                    show_index=False,
                                                    layout='fit_columns',
                                                    text_align='center',
                                                    selectable=1,
                                                    height=400,
                                                    width=550)
        self.plt_trns_kva = self.gen_plt_trns_kva(self.tbl_trns_summary.value.iloc[0]["Name"])
        self.hist_trns_kva = self.gen_hist_trns_kva(self.tbl_trns_summary.value.iloc[0]["Name"])
        
        self.tbl_lines_summary = pn.widgets.Tabulator(self.dop.get_lines_tbl_df(),
                                                    pagination=None,
                                                    disabled=True,
                                                    show_index=False,
                                                    layout='fit_columns',
                                                    text_align='center',
                                                    selectable=1,
                                                    height=400,
                                                    width=550)
        self.plt_line_i_mag = self.gen_plt_line_i_mag(self.tbl_lines_summary.value.iloc[0]["Name"])
        self.hist_line_i_mag = self.gen_hist_line_i_mag(self.tbl_lines_summary.value.iloc[0]["Name"])
        
        self.tbl_bus_summary = pn.widgets.Tabulator(self.dop.get_bus_tbl_df(),
                                                    pagination=None,
                                                    disabled=True,
                                                    show_index=False,
                                                    layout='fit_columns',
                                                    text_align='center',
                                                    selectable=1,
                                                    height=400,
                                                    width=550)
        self.plt_bus_v_mag = self.gen_plt_bus_v_mag(self.tbl_bus_summary.value.iloc[0]["Bus"])
        self.hist_bus_v_mag = self.gen_hist_bus_v_mag(self.tbl_bus_summary.value.iloc[0]["Bus"])


        self.save_button = pn.widgets.FileDownload(
            callback=self.get_zip_data, 
            filename="downloaded_data.zip", 
            button_type="primary",  
            label="Save Sim Plus Data"
        )
    
    def gen_bar_trns_loading_fig(self, kva_percent: int = 100):
        df_trns_loading_count = self.dop.get_trns_kva_loading(kva_percent=kva_percent)
        fig = px.bar(df_trns_loading_count, x='Rating (kVA)', y='Count (#)', color='Scenario', title='Overloaded (>{}%) Transformers Per Size'.format(kva_percent), barmode='group')
        # Update layout to set x-ticks and labels
        fig.update_layout(
            xaxis=dict(
                tickmode='array',
                tickvals=df_trns_loading_count["Rating (kVA)"].unique().tolist(),  # Positions of the ticks
                ticktext=df_trns_loading_count["Rating (kVA)"].apply(lambda x: str(round(x))).unique().tolist() # Labels for the ticks
            )
        )
        return fig
    
    def gen_bar_trns_loading(self, kva_percent: int = 100):
        fig = self.gen_bar_trns_loading_fig(kva_percent=kva_percent)
        return pn.pane.Plotly(fig, height=400, width=700)
    
    def gen_bar_lines_loading_fig(self, loading_percent: int=100):
        df_lines_loading_count = self.dop.get_lines_loading(loading_percent=loading_percent)
        fig = px.bar(df_lines_loading_count, x='Line Code', y='Distance (miles)', color='Scenario', title='Overloaded (>{}%) Line Miles Per Line Code'.format(loading_percent), barmode='group')
        return fig
    
    def gen_bar_lines_loading(self, loading_percent: int=100):
        fig = self.gen_bar_lines_loading_fig(loading_percent)
        return pn.pane.Plotly(fig, height=400, width=700)
    
    def gen_hist_pcc_min_voltage(self) -> pn.pane.Plotly:
        nodes_df = self.dop.get_pcc_min_voltage_summary()
        fig = px.histogram(nodes_df, x='V_mag_min', nbins=100, title='PCC Voltage Minimum')
        fig.update_layout(
            xaxis_title_text = "Voltage Magnitude (p.u.)",
            yaxis_title_text = "Number of Nodes (#)",
        )
        return pn.pane.Plotly(fig, width=600)
        
    def gen_plt_trns_kva_fig(self, trns_name: str) -> pn.pane.Plotly:
        kva_df = self.dop.get_trns_kva_ts(trns_name)
        fig = px.line(kva_df, x='Time', y='kva_mag', title='[{}] kVA magnitude'.format(trns_name))
        return fig
        
    def gen_plt_trns_kva(self, trns_name: str) -> pn.pane.Plotly:
        fig = self.gen_plt_trns_kva_fig(trns_name)
        return pn.pane.Plotly(fig, width=600)
            
    def gen_hist_trns_kva_fig(self, trns_name: str) -> pn.pane.Plotly:
        kva_df = self.dop.get_trns_kva_ts(trns_name)
        fig = px.histogram(kva_df, x='kva_mag', y='Time', nbins=100, title='[{}] kVA Magnitude Distribution'.format(trns_name))
        return fig
    
    def gen_hist_trns_kva(self, trns_name: str) -> pn.pane.Plotly:
        fig = self.gen_hist_trns_kva_fig(trns_name)
        return pn.pane.Plotly(fig, width=600)
        
    def gen_plt_line_i_mag_fig(self, line_name: str) -> pn.pane.Plotly:
        i_mag_df = self.dop.get_line_i_ts(line_name)
        fig = px.line(i_mag_df, x='Time', y='i_mag', title='[{}] Current magnitude'.format(line_name))
        return fig
        
    def gen_plt_line_i_mag(self, line_name: str) -> pn.pane.Plotly:
        fig = self.gen_plt_line_i_mag_fig(line_name)
        return pn.pane.Plotly(fig, width=600)
            
    def gen_hist_line_i_mag_fig(self, line_name: str) -> pn.pane.Plotly:
        i_mag_df = self.dop.get_line_i_ts(line_name)
        fig = px.histogram(i_mag_df, x='i_mag', y='Time', nbins=100, title='[{}] Current Magnitude Distribution'.format(line_name))
        return fig
    
    def gen_hist_line_i_mag(self, line_name: str) -> pn.pane.Plotly:
        fig = self.gen_hist_line_i_mag_fig(line_name)
        return pn.pane.Plotly(fig, width=600)
        
    def gen_plt_bus_v_mag_fig(self, bus_name: str) -> pn.pane.Plotly:
        v_mag_df = self.dop.get_bus_v_ts(bus_name)
        fig = px.line(v_mag_df, x='Time', y='v_mag', color='node', title='[{}] Voltage magnitude'.format(bus_name))
        return fig
        
    def gen_plt_bus_v_mag(self, bus_name: str) -> pn.pane.Plotly:
        fig = self.gen_plt_bus_v_mag_fig(bus_name)
        return pn.pane.Plotly(fig, width=600)
            
    def gen_hist_bus_v_mag_fig(self, bus_name: str) -> pn.pane.Plotly:
        v_mag_df = self.dop.get_bus_v_ts(bus_name)
        fig = px.histogram(v_mag_df, x='v_mag', y='Time', color='node', nbins=100, title='[{}] Voltage Magnitude Distribution'.format(bus_name))
        return fig
            
    def gen_hist_bus_v_mag(self, bus_name: str) -> pn.pane.Plotly:
        fig = self.gen_hist_bus_v_mag_fig(bus_name)
        return pn.pane.Plotly(fig, width=600)
        
    def save_session_JSON(self):
        save_session_dict = {
            "file_names": dict(self.file_names.items()),
            "configs": dict(self.configs.items())
        }
        
        for k,v in save_session_dict.items():
            for k2,v2 in v.items():
                if k2 == "month":
                    v[k2] = str(v2)
                    
        return save_session_dict


    def get_zip_data(self):
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zip_file:
            # Add CSV files to ZIP
            for name, path in self.paths.items():
                zip_file.write(path, arcname=self.configs["sim_name"] + "_" + name + ".csv")  # Use original file names in ZIP

            # Add JSON data to ZIP
            json_data = json.dumps(dict(self.save_session_JSON().items()), indent=4).encode('utf-8')
            zip_file.writestr('session_info.json', json_data)  # Save JSON with a specific name

        zip_buffer.seek(0)  # Reset buffer position for reading
        return zip_buffer

    def on_trns_loading_button_click(self, event):
        kva_percent = self.trns_loading_slider.value
        self.bar_trns_loading_count.object = self.gen_bar_trns_loading_fig(kva_percent)
        # self.bar_trns_loading_count.object.update_traces

    def on_lines_loading_button_click(self, event):
        loading_percent = self.lines_loading_slider.value
        self.bar_lines_loading_count.object = self.gen_bar_lines_loading_fig(loading_percent)
        
    def update_trns_kva_plots(self, event):
        idx = event.row
        row = self.tbl_trns_summary.value.iloc[idx]
        self.plt_trns_kva.object = self.gen_plt_trns_kva_fig(trns_name=row["Name"])
        self.hist_trns_kva.object = self.gen_hist_trns_kva_fig(trns_name=row["Name"])
        
    def update_lines_i_mag_plots(self, event):
        idx = event.row
        row = self.tbl_lines_summary.value.iloc[idx]
        self.plt_line_i_mag.object = self.gen_plt_line_i_mag_fig(line_name=row["Name"])
        self.hist_line_i_mag.object = self.gen_hist_line_i_mag_fig(line_name=row["Name"])
        
    def update_bus_v_mag_plots(self, event):
        idx = event.row
        row = self.tbl_bus_summary.value.iloc[idx]
        self.plt_bus_v_mag.object = self.gen_plt_bus_v_mag_fig(bus_name=row["Bus"])
        self.hist_bus_v_mag.object = self.gen_hist_bus_v_mag_fig(bus_name=row["Bus"])
        
        
    def panel(self):
        
        css = """
        .center-content .bk {
            display: flex;
            justify-content: center;
            align-items: center;
        }
        """
        self.trns_loading_button.on_click(self.on_trns_loading_button_click)
        self.lines_loading_button.on_click(self.on_lines_loading_button_click)
        
        self.tbl_trns_summary.on_click(self.update_trns_kva_plots)
        self.tbl_lines_summary.on_click(self.update_lines_i_mag_plots)
        self.tbl_bus_summary.on_click(self.update_bus_v_mag_plots)
        
        pn.config.raw_css.append(css)

        pane_des = pn.pane.Markdown(f"""<span style="font-size:12pt">Simulation Name: <b>{self.configs['sim_name']}</b>
                                        </span>""")

        app = pn.Column(
            pane_des,
            pn.layout.Card(
                pn.Row(
                    pn.Column(
                        pn.Row(
                            self.trns_loading_slider,
                            self.trns_loading_button,
                        ),
                        self.bar_trns_loading_count,
                    ),
                    self.tbl_trns_max_load,
                    height=500,
                ),
                pn.Row(
                    pn.Column(
                        pn.Row(
                            self.lines_loading_slider,
                            self.lines_loading_button,
                        ),
                        self.bar_lines_loading_count,
                    ),
                    self.tbl_lines_max_load,
                    height=500,
                ),
                pn.Row(
                    self.hist_pcc_min_voltage,
                    self.tbl_pcc_min_voltage,
                    height=400,
                ),
                title="Simulation Summary",
                collapsed=False,
                height=1500,
                width=1200,
            ),
            pn.Spacer(height=10),
            pn.layout.Card(
                pn.Tabs(
                    ("Transformers", pn.Row(
                        self.tbl_trns_summary,
                        pn.Tabs(
                            ("Time Series", self.plt_trns_kva),
                            ("Histogram", self.hist_trns_kva),
                            width=600,
                        ),
                        )
                    ),
                    ("Lines", pn.Row(
                        self.tbl_lines_summary,
                        pn.Tabs(
                            ("Time Series", self.plt_line_i_mag),
                            ("Histogram", self.hist_line_i_mag),
                            width=600,
                        ),
                        )
                    ),
                    ("Busses", pn.Row(
                        self.tbl_bus_summary,
                        pn.Tabs(
                            ("Time Series", self.plt_bus_v_mag),
                            ("Histogram", self.hist_bus_v_mag),
                            width=600,
                        ),
                        )
                    ),
                ),
                title="Analyze Individual Elements",
                collapsed=False,
                height=700,
                width=1200,
                ),
            pn.Spacer(height=100),
            pn.Row(self.tbl_ev_loads),
            self.save_button,
            width=1200,
        )
        return app
