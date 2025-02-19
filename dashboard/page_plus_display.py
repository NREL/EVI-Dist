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
import pickle

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

    input_file_names: param.Dict = param.Dict()
    output_file_names: param.Dict = param.Dict()
    configs: param.Dict = param.Dict()

    ready = param.Boolean(default=False)

    def __init__(self, **params):
        super().__init__(**params)

        # self.file_names = params['file_names']
        self.paths = {}

        self.paths['evloads'] = self.output_file_names['evloads']
        self.paths['linecurrents'] = self.output_file_names['linecurrents']
        self.paths['linedata'] = self.output_file_names['linedata']
        self.paths['trnscurrents'] = self.output_file_names['trnscurrents']
        self.paths['trnskva'] = self.output_file_names['trnskva']
        self.paths['trnskva_ratings'] = self.output_file_names['trnskva_ratings']
        self.paths['voltages'] = self.output_file_names['voltages']
        self.paths['bus_info'] = self.output_file_names['bus_info']
        self.paths['charge_events'] = self.output_file_names['charge_events']
        self.paths['trns_premise_ev_mapping'] = self.output_file_names['trns_premise_ev_mapping']
        self.paths['ev_charge_stats'] = self.output_file_names['ev_charge_stats']
        # self.paths['ev_profiles'] = dict()

        self.simulation_description = pn.pane.Markdown(f"""
            ## Simulation Configuration
            - Name: <b>{self.configs["sim_name"]}</b>
            - Feeder: <b>{self.configs["feeder"]}</b>
            - EV charging controller: <b>{self.configs["controller"]}</b>
            - Simulated month: <b>{self.configs["month"]}</b>
            - Simulated day of week: <b>{self.configs["day_of_week"]}</b>
            """,
            height=200)

        self.dop: DataOperatorPlus = pn.state.dop

        self.simulation_summary = pn.pane.Markdown(f"""
            ## Feeder Information
            - Total number of transformers: <b>{self.dop.num_trns}</b>
            - Total number of premises: <b>{self.dop.num_premises}</b>
            - Total number of EVs that charged: <b>{self.dop.num_ev}</b>
            - Ratio of EV charge events completed: <b>{self.dop.num_charge_events_completed}/{self.dop.num_charge_events}</b>
            """,
            height=200)


        # self.tbl_ev_loads = pn.widgets.Tabulator(self.dop.get_evloads(), height=400, width=700, pagination=None, disabled=True)

        ##Summary section
        # tables
        self.tbl_trns_loading_count = pn.widgets.Tabulator(pd.DataFrame(),
                                                    pagination=None,
                                                    disabled=True,
                                                    show_index=False,
                                                    layout='fit_columns',
                                                    text_align='center',
                                                    selectable=1,
                                                    height=350,
                                                    width=300,
                                                    margin=0)
        self.tbl_lines_p_loading_count = pn.widgets.Tabulator(pd.DataFrame(),
                                                    pagination=None,
                                                    disabled=True,
                                                    show_index=False,
                                                    layout='fit_columns',
                                                    text_align='center',
                                                    selectable=1,
                                                    height=300,
                                                    width=300)
        self.tbl_lines_s_loading_count = pn.widgets.Tabulator(pd.DataFrame(),
                                                    pagination=None,
                                                    disabled=True,
                                                    show_index=False,
                                                    layout='fit_columns',
                                                    text_align='center',
                                                    selectable=1,
                                                    height=300,
                                                    width=300)
        self.tbl_bus_loading_count = pn.widgets.Tabulator(pd.DataFrame(),
                                                    pagination=None,
                                                    disabled=True,
                                                    show_index=False,
                                                    layout='fit_columns',
                                                    text_align='center',
                                                    selectable=1,
                                                    height=300,
                                                    width=300)
        # plots
        self.bar_trns_loading_count, self.tbl_trns_loading_count.value = self.gen_bar_trns_loading()
        self.bar_lines_p_loading_count, self.bar_lines_s_loading_count, self.tbl_lines_p_loading_count.value, self.tbl_lines_s_loading_count.value = self.gen_bar_lines_loading()
        self.hist_pcc_min_voltage, self.tbl_bus_loading_count.value = self.gen_hist_pcc_min_voltage()
        self.trns_loading_info = pn.pane.Markdown(f"""
                                                  ## Overloaded Transformers:
                                                  **Total: {len(self.tbl_trns_loading_count.value)}**
                                                  """,
                                                  margin=0)
        self.lines_p_loading_info = pn.pane.Markdown(f"""
                                                    ## Overloaded Lines:
                                                    ### Primary:
                                                    **Total: {len(self.tbl_lines_p_loading_count.value)}**
                                                    """)
        self.lines_s_loading_info = pn.pane.Markdown(f"""
                                                    ### Secondary:
                                                    **Total: {len(self.tbl_lines_s_loading_count.value)}**
                                                    """)
        self.bus_loading_info = pn.pane.Markdown(f"""
                                                ## Under Voltage PCC Buses:
                                                **Total: {len(self.tbl_bus_loading_count.value)}**
                                                """)


        #buttons and sliders

        self.trns_loading_slider = pn.widgets.IntSlider(name='Transformer Loading Cut-off (%)', start=0, end=200, step=1, value=100)
        self.trns_loading_duration_slider = pn.widgets.IntSlider(name='Transformer Overloading Duration (min)', start=0, end=15*4*24, step=15, value=0)
        self.trns_loading_duration_options = pn.widgets.RadioBoxGroup(name='RadioBoxGroup', options=['Consecutive Overloading Duration', 'Total Overloading Duration'], inline=True)
        self.trns_loading_button = pn.widgets.Button(name='Apply', button_type='primary')
        self.lines_loading_slider = pn.widgets.IntSlider(name='Lines Loading Cut-off (%)', start=0, end=200, step=1, value=100)
        self.lines_loading_duration_slider = pn.widgets.IntSlider(name='Lines Overloading Duration (min)', start=0, end=15*4*24, step=15, value=0)
        self.lines_loading_duration_options = pn.widgets.RadioBoxGroup(name='RadioBoxGroup', options=['Consecutive Overloading Duration', 'Total Overloading Duration'], inline=True)
        self.lines_loading_button = pn.widgets.Button(name='Apply', button_type='primary')
        self.bus_loading_slider = pn.widgets.FloatSlider(name='PCC Bus Voltage Cut-off (pu)', start=0, end=1.0, step=0.01, value=0.95)
        self.bus_loading_duration_slider = pn.widgets.IntSlider(name='PCC Bus Overloading Duration (min)', start=0, end=15*4*24, step=15, value=0)
        self.bus_loading_duration_options = pn.widgets.RadioBoxGroup(name='RadioBoxGroup', options=['Consecutive Under Voltage Duration', 'Total Under Voltage Duration'], inline=True)
        self.bus_loading_button = pn.widgets.Button(name='Apply', button_type='primary')

        #Individual elements section
        self.tbl_trns_summary = pn.widgets.Tabulator(self.dop.get_trns_tbl_df(),
                                                    pagination=None,
                                                    disabled=True,
                                                    show_index=False,
                                                    layout='fit_columns',
                                                    sizing_mode='stretch_width',
                                                    text_align='center',
                                                    selectable=1,
                                                    header_filters={
                                                        'Name <br> (ID)': {'type': 'input', 'func': 'like', 'placeholder': '== X'},
                                                        'Rating <br> (kVA)': {'type': 'list', 'func': '=', 'valuesLookup': True, 'sort': 'asc', 'multiselect': False, 'placeholder': '<select>'},
                                                        'Max Load <br> Power (pu)': {'type': 'input', 'func': '>=', 'placeholder': '>= X'},
                                                        'Avg Load <br> Power (pu)': {'type': 'input', 'func': '>=', 'placeholder': '>= X'},
                                                        'Min Load <br> Power (pu)': {'type': 'input', 'func': '>=', 'placeholder': '>= X'},
                                                        'Phases <br> (#)': {'type': 'list', 'func': 'in', 'valuesLookup': True, 'sort': 'asc', 'multiselect': True, 'placeholder': '<select>'},
                                                        'Premises <br> (#)': {'type': 'input', 'func': '>=', 'placeholder': '>= X'},
                                                        'EVs <br> (#)': {'type': 'input', 'func': '>=', 'placeholder': '>= X'},
                                                        'Charge Events <br> Completed (%)': {'type': 'input', 'func': '<=', 'placeholder': '<= X'},
                                                        },
                                                    height=500,
                                                    min_width=870)
        self.plt_trns_kva = self.gen_plt_trns_kva(self.tbl_trns_summary.value.iloc[0]["Name <br> (ID)"])
        self.hist_trns_kva = self.gen_hist_trns_kva(self.tbl_trns_summary.value.iloc[0]["Name <br> (ID)"])

        self.tbl_lines_summary = pn.widgets.Tabulator(self.dop.get_lines_tbl_df(),
                                                    pagination=None,
                                                    disabled=True,
                                                    show_index=False,
                                                    layout='fit_columns',
                                                    sizing_mode='stretch_width',
                                                    text_align='center',
                                                    selectable=1,
                                                    header_filters={
                                                        'Name <br> (ID)': {'type': 'input', 'func': 'like', 'placeholder': '== X'},
                                                        'Type <br> (str)': {'type': 'list', 'func': 'in', 'valuesLookup': True, 'sort': 'asc', 'multiselect': False, 'placeholder': '<select>'},
                                                        'Line Code <br> (str)': {'type': 'list', 'func': 'in', 'valuesLookup': True, 'sort': 'asc', 'multiselect': True, 'placeholder': '<select>'},
                                                        'Length <br> (kft)': {'type': 'input', 'func': '>=', 'placeholder': '>= X'},
                                                        'Phases <br> (#)': {'type': 'list', 'func': 'in', 'valuesLookup': True, 'sort': 'asc', 'multiselect': True, 'placeholder': '<select>'},
                                                        'Rating <br> (A)': {'type': 'input', 'func': '>=', 'placeholder': '>= X'},
                                                        'Max Load <br> (pu)': {'type': 'input', 'func': '>=', 'placeholder': '>= X'},
                                                        'Avg Load <br> (pu)': {'type': 'input', 'func': '>=', 'placeholder': '>= X'},
                                                        'Min Load <br> (pu)': {'type': 'input', 'func': '>=', 'placeholder': '>= X'},
                                                        },
                                                    height=500,
                                                    min_width=870)
        self.plt_line_i_mag = self.gen_plt_line_i_mag(self.tbl_lines_summary.value.iloc[0]["Name <br> (ID)"])
        self.hist_line_i_mag = self.gen_hist_line_i_mag(self.tbl_lines_summary.value.iloc[0]["Name <br> (ID)"])

        self.tbl_bus_summary = pn.widgets.Tabulator(self.dop.get_bus_tbl_df(),
                                                    pagination=None,
                                                    disabled=True,
                                                    show_index=False,
                                                    layout='fit_columns',
                                                    sizing_mode='stretch_width',
                                                    text_align='center',
                                                    selectable=1,
                                                    header_filters={
                                                        'Bus <br> (ID)': {'type': 'input', 'func': 'like', 'placeholder': '== X'},
                                                        'Is PCC <br> (Y/N)': {'type': 'list', 'func': 'in', 'valuesLookup': True, 'sort': 'asc', 'multiselect': False, 'placeholder': '<select>'},
                                                        'Phases <br> (#)': {'type': 'list', 'func': 'in', 'valuesLookup': True, 'sort': 'asc', 'multiselect': True, 'placeholder': '<select>'},
                                                        'Min |V| <br> (pu)': {'type': 'input', 'func': '<=', 'placeholder': '<= X'},
                                                        'Avg |V| <br> (pu)': {'type': 'input', 'func': '>=', 'placeholder': '>= X'},
                                                        'Max |V| <br> (pu)': {'type': 'input', 'func': '>=', 'placeholder': '>= X'},
                                                        },
                                                    height=500,
                                                    min_width=870)
        self.plt_bus_v_mag = self.gen_plt_bus_v_mag(self.tbl_bus_summary.value.iloc[0]["Bus <br> (ID)"])
        self.hist_bus_v_mag = self.gen_hist_bus_v_mag(self.tbl_bus_summary.value.iloc[0]["Bus <br> (ID)"])


        self.save_button = pn.widgets.FileDownload(
            callback=self.get_zip_data,
            filename=self.configs["sim_name"] + "_sim_plus_data.zip",
            button_type="primary",
            label="Save Simulation Results"
        )

        # Button to trigger opening a new instance
        self.new_session_button = pn.widgets.Button(name="Open New Tab Session", button_type="default")
        self.new_session_js_code = f"""window.open("{pn.state.location.href}")"""

    def gen_bar_trns_loading_fig(self, kva_percent: int = 100, duration: int = 0, loading_option: str = "Consecutive Overloading Duration"):
        df_trns_loading_count, df_list = self.dop.get_trns_kva_loading(kva_percent=kva_percent, duration=duration*60, loading_option=loading_option)
        fig = px.bar(df_trns_loading_count, x='Rating (kVA)', y='Count (#)', color='Scenario',
                    title='Transformers Per Size, Loaded >{}% for >{} min'.format(kva_percent, duration),
                    barmode='group',
                    text_auto=True)
        # Update layout to set x-ticks and labels
        fig.update_layout(
            xaxis_type='category',
            xaxis=dict(
                tickmode='array',
                tickvals=df_trns_loading_count["Rating (kVA)"].unique().tolist(),  # Positions of the ticks
                ticktext=df_trns_loading_count["Rating (kVA)"].apply(lambda x: str(round(x))).unique().tolist() # Labels for the ticks
            ),
            legend=dict(
                orientation="h",  # Set legend orientation to horizontal
                yanchor="bottom",
                y=1.0,  # Position slightly below the plot to avoid overlapping xlabel
                xanchor="left",
                x=0  # Position at the left edge
            ),
            margin=dict(
                l=10,
                r=10,
                t=80,
                b=20
            ),
        )
        return fig, df_list

    def gen_bar_trns_loading(self, kva_percent: int = 100):
        fig, df_list = self.gen_bar_trns_loading_fig(kva_percent=kva_percent)
        return pn.pane.Plotly(fig, height=400, min_width=570, config={'responsive': True}, sizing_mode='stretch_width'), df_list

    def gen_bar_lines_loading_fig(self, loading_percent: int=100, duration: int = 0, loading_option: str = "Consecutive Overloading Duration"):
        df_lines_loading_count, df_list = self.dop.get_lines_loading(loading_percent=loading_percent, duration=duration*60, loading_option=loading_option)

        fig_primary = px.bar(df_lines_loading_count[df_lines_loading_count["Type"] == "Primary"], x='Line Code', y='Distance (miles)', color='Scenario',
                    title='Primary Line Miles Per Line Code, Loaded >{}% for >{} min'.format(loading_percent, duration),
                    barmode='group',
                    text_auto=".1f")
        fig_primary.update_layout(
            xaxis_type='category',
            xaxis=dict(
                tickmode='array',
                tickvals=df_lines_loading_count["Line Code"].unique().tolist(),  # Positions of the ticks
                tickangle=90,
            ),
            legend=dict(
                orientation="h",  # Set legend orientation to horizontal
                yanchor="bottom",
                y=1.0,  # Position slightly below the plot to avoid overlapping xlabel
                xanchor="left",
                x=0  # Position at the left edge
            ),
            margin=dict(
                l=10,
                r=10,
                t=80,
                b=20
            ),
        )

        fig_secondary = px.bar(df_lines_loading_count[df_lines_loading_count["Type"] == "Secondary"], x='Line Code', y='Distance (miles)', color='Scenario',
                    title='Secondary Line Miles Per Line Code, Loaded >{}% for >{} min'.format(loading_percent, duration),
                    barmode='group',
                    text_auto=".1f")
        fig_secondary.update_layout(
            xaxis_type='category',
            xaxis=dict(
                tickmode='array',
                tickvals=df_lines_loading_count["Line Code"].unique().tolist(),  # Positions of the ticks
                tickangle=90,
            ),
            legend=dict(
                orientation="h",  # Set legend orientation to horizontal
                yanchor="bottom",
                y=1.0,  # Position slightly below the plot to avoid overlapping xlabel
                xanchor="left",
                x=0  # Position at the left edge
            ),
            margin=dict(
                l=10,
                r=10,
                t=80,
                b=20
            ),
        )
        return fig_primary, fig_secondary, df_list[df_list["Type"] == "Primary"].drop(["Type", "Line Code"], axis=1), df_list[df_list["Type"] == "Secondary"].drop(["Type", "Line Code"], axis=1)

    def gen_bar_lines_loading(self, loading_percent: int=100):
        fig_p, fig_s, df_p, df_s = self.gen_bar_lines_loading_fig(loading_percent)
        return pn.pane.Plotly(fig_p, height=450, min_width=570, config={'responsive': True}, sizing_mode='stretch_width'), pn.pane.Plotly(fig_s, height=450, min_width=570, config={'responsive': True}, sizing_mode='stretch_width'), df_p, df_s

    def gen_hist_pcc_min_voltage_fig(self, voltage_cutoff: float = 0.95, duration: int = 0, loading_option: str = "Consecutive Under Voltage Duration"):
        nodes_df = self.dop.get_pcc_min_voltage_summary(voltage_cutoff, duration*60, loading_option)
        fig = px.histogram(nodes_df, x='Min |V| (pu)', nbins=100, title=f"PCC Voltage Minimum for <{duration} min")
        fig.add_vline(x=voltage_cutoff, line_width=1, line_dash="dash", line_color="red")
        fig.update_layout(
            xaxis_title_text = "Voltage Magnitude (pu)",
            yaxis_title_text = "Number of Nodes (#)",
            legend=dict(
                orientation="h",  # Set legend orientation to horizontal
                yanchor="top",
                y=-0.2,  # Position slightly below the plot to avoid overlapping xlabel
                xanchor="left",
                x=0  # Position at the left edge
            ),
            margin=dict(
                l=10,
                r=10,
                t=30,
                b=20
            ),
        )
        return fig, nodes_df[nodes_df["Min |V| (pu)"] <= voltage_cutoff]

    def gen_hist_pcc_min_voltage(self, voltage_cutoff: float = 0.95, duration: int = 0, loading_option: str = "Consecutive Under Voltage Duration"):
        fig, df_list = self.gen_hist_pcc_min_voltage_fig(voltage_cutoff, duration, loading_option)
        return pn.pane.Plotly(fig, height=350, min_width=570, config={'responsive': True}, sizing_mode='stretch_width'), df_list

    def gen_plt_trns_kva_fig(self, trns_name: str) -> pn.pane.Plotly:
        kva_df = self.dop.get_trns_kva_ts(trns_name)
        fig = px.line(kva_df, x='Time (hour)', y='Power Magnitude (kVA)', color='Load', title='Transformer: {}, Power Time Series'.format(trns_name), line_shape="hv", markers=True)
        for i in range(len(fig.data)):
            fig.data[i].marker.size = 3
            if "Veh" in fig.data[i].name:
                fig.data[i].line.dash = 'dash'
        fig.update_layout(
            legend=dict(
                orientation="h",  # Set legend orientation to horizontal
                yanchor="top",
                y=-0.2,  # Position slightly below the plot to avoid overlapping xlabel
                xanchor="left",
                x=0  # Position at the left edge
            ),
            margin=dict(
                l=10,
                r=10,
                t=30,
                b=20
            ),
        )
        return fig

    def gen_plt_trns_kva(self, trns_name: str) -> pn.pane.Plotly:
        fig = self.gen_plt_trns_kva_fig(trns_name)
        return pn.pane.Plotly(fig, min_width=700, config={'responsive': True}, sizing_mode='stretch_width')

    def gen_hist_trns_kva_fig(self, trns_name: str) -> pn.pane.Plotly:
        kva_df = self.dop.get_trns_kva_ts(trns_name)
        fig = px.histogram(kva_df[kva_df["Load"] == "Total"], x='Power Magnitude (kVA)', y='Time (hour)', color='Load', nbins=100, title='Transformer: {}, Power Distribution'.format(trns_name))
        fig.update_layout(
            legend=dict(
                orientation="h",  # Set legend orientation to horizontal
                yanchor="top",
                y=-0.2,  # Position slightly below the plot to avoid overlapping xlabel
                xanchor="left",
                x=0  # Position at the left edge
            ),
            margin=dict(
                l=10,
                r=10,
                t=30,
                b=20
            ),
        )
        return fig

    def gen_hist_trns_kva(self, trns_name: str) -> pn.pane.Plotly:
        fig = self.gen_hist_trns_kva_fig(trns_name)
        return pn.pane.Plotly(fig, min_width=700, config={'responsive': True}, sizing_mode='stretch_width')

    def gen_plt_line_i_mag_fig(self, line_name: str) -> pn.pane.Plotly:
        i_mag_df = self.dop.get_line_i_ts(line_name)
        fig = px.line(i_mag_df, x='Time (hour)', y='Current Magnitude (A)', color='Phase', title='Line: {}, Current Time Series'.format(line_name), line_shape="hv", markers=True)
        for i in range(len(fig.data)):
            fig.data[i].marker.size = 3
        fig.update_layout(
            legend=dict(
                orientation="h",  # Set legend orientation to horizontal
                yanchor="top",
                y=-0.2,  # Position slightly below the plot to avoid overlapping xlabel
                xanchor="left",
                x=0  # Position at the left edge
            ),
            margin=dict(
                l=10,
                r=10,
                t=30,
                b=20
            ),
        )
        return fig

    def gen_plt_line_i_mag(self, line_name: str) -> pn.pane.Plotly:
        fig = self.gen_plt_line_i_mag_fig(line_name)
        return pn.pane.Plotly(fig, min_width=700, config={'responsive': True}, sizing_mode='stretch_width')

    def gen_hist_line_i_mag_fig(self, line_name: str) -> pn.pane.Plotly:
        i_mag_df = self.dop.get_line_i_ts(line_name)
        fig = px.histogram(i_mag_df, x='Current Magnitude (A)', y='Time (hour)', color='Phase', nbins=100, title='Line: {}, Current Distribution'.format(line_name))
        fig.update_layout(
            legend=dict(
                orientation="h",  # Set legend orientation to horizontal
                yanchor="top",
                y=-0.2,  # Position slightly below the plot to avoid overlapping xlabel
                xanchor="left",
                x=0  # Position at the left edge
            ),
            margin=dict(
                l=10,
                r=10,
                t=30,
                b=20
            ),
        )
        return fig

    def gen_hist_line_i_mag(self, line_name: str) -> pn.pane.Plotly:
        fig = self.gen_hist_line_i_mag_fig(line_name)
        return pn.pane.Plotly(fig, min_width=700, config={'responsive': True}, sizing_mode='stretch_width')

    def gen_plt_bus_v_mag_fig(self, bus_name: str) -> pn.pane.Plotly:
        v_mag_df = self.dop.get_bus_v_ts(bus_name)
        fig = px.line(v_mag_df, x='Time (hour)', y='Voltage Magnitude (V)', color='node', title='Bus: {}, Voltage Time Series'.format(bus_name), line_shape="hv", markers=True)
        for i in range(len(fig.data)):
            fig.data[i].marker.size = 3
        fig.update_layout(
            legend=dict(
                orientation="h",  # Set legend orientation to horizontal
                yanchor="top",
                y=-0.2,  # Position slightly below the plot to avoid overlapping xlabel
                xanchor="left",
                x=0  # Position at the left edge
            ),
            margin=dict(
                l=10,
                r=10,
                t=30,
                b=20
            ),
        )
        return fig

    def gen_plt_bus_v_mag(self, bus_name: str) -> pn.pane.Plotly:
        fig = self.gen_plt_bus_v_mag_fig(bus_name)
        return pn.pane.Plotly(fig, min_width=700, config={'responsive': True}, sizing_mode='stretch_width')

    def gen_hist_bus_v_mag_fig(self, bus_name: str) -> pn.pane.Plotly:
        v_mag_df = self.dop.get_bus_v_ts(bus_name)
        fig = px.histogram(v_mag_df, x='Voltage Magnitude (V)', y='Time (hour)', color='node', nbins=100, title='Bus: {}, Voltage Distribution'.format(bus_name))
        fig.update_layout(
            legend=dict(
                orientation="h",  # Set legend orientation to horizontal
                yanchor="top",
                y=-0.2,  # Position slightly below the plot to avoid overlapping xlabel
                xanchor="left",
                x=0  # Position at the left edge
            ),
            margin=dict(
                l=10,
                r=10,
                t=30,
                b=20
            ),
        )
        return fig

    def gen_hist_bus_v_mag(self, bus_name: str) -> pn.pane.Plotly:
        fig = self.gen_hist_bus_v_mag_fig(bus_name)
        return pn.pane.Plotly(fig, min_width=700, config={'responsive': True}, sizing_mode='stretch_width')

    def save_session_JSON(self):
        #first clear user's dir information from input file names.
        input_file_names = {k: os.path.basename(v) for k,v in self.input_file_names.items()}

        save_session_dict = {
            "input_file_names": dict(input_file_names),
            "output_file_names": dict(self.output_file_names.items()),
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
                if os.path.exists(EVIDIST_ROOT_PATH + "/data/temp_sim_plus/" + path):
                    zip_file.write(EVIDIST_ROOT_PATH + "/data/temp_sim_plus/" + path, arcname="sim_plus_" + name + ".csv")  # Use original file names in ZIP

            # Add JSON data to ZIP
            json_data = json.dumps(dict(self.save_session_JSON().items()), indent=4).encode('utf-8')
            zip_file.writestr('session_info.json', json_data)  # Save JSON with a specific name

            # Add DataOperatorPlus pickle to ZIP
            dop_pickle = pickle.dumps(self.dop)
            zip_file.writestr("dop.pickle", dop_pickle)

        zip_buffer.seek(0)  # Reset buffer position for reading
        return zip_buffer

    def on_trns_loading_button_click(self, event):
        kva_percent = self.trns_loading_slider.value
        duration = self.trns_loading_duration_slider.value
        loading_option = self.trns_loading_duration_options.value
        self.bar_trns_loading_count.object, self.tbl_trns_loading_count.value = self.gen_bar_trns_loading_fig(kva_percent,duration,loading_option)
        self.trns_loading_info.object = f"""
                                        ## Overloaded Transformers:
                                        **Total: {len(self.tbl_trns_loading_count.value)}**
                                        """

    def on_lines_loading_button_click(self, event):
        loading_percent = self.lines_loading_slider.value
        duration = self.lines_loading_duration_slider.value
        loading_option = self.trns_loading_duration_options.value
        self.bar_lines_p_loading_count.object, self.bar_lines_s_loading_count.object, self.tbl_lines_p_loading_count.value, self.tbl_lines_s_loading_count.value = self.gen_bar_lines_loading_fig(loading_percent, duration, loading_option)
        self.lines_p_loading_info.object = f"""
                                        ## Overloaded Lines:
                                        ### Primary:
                                        **Total: {len(self.tbl_lines_p_loading_count.value)}**
                                        """
        self.lines_s_loading_info.object = f"""
                                        ### Secondary:
                                        **Total: {len(self.tbl_lines_s_loading_count.value)}**
                                        """

    def on_bus_loading_button_click(self, event):
        voltage_cutoff = self.bus_loading_slider.value
        duration = self.bus_loading_duration_slider.value
        loading_option = self.bus_loading_duration_options.value
        self.hist_pcc_min_voltage.object, self.tbl_bus_loading_count.value = self.gen_hist_pcc_min_voltage_fig(voltage_cutoff, duration, loading_option)
        self.bus_loading_info.object = f"""
                                        ## Under Voltage PCC Buses:
                                        **Total: {len(self.tbl_bus_loading_count.value)}**
                                        """

    def update_trns_kva_plots(self, event):
        idx = event.row
        row = self.tbl_trns_summary.value.iloc[idx]
        self.plt_trns_kva.object = self.gen_plt_trns_kva_fig(trns_name=row["Name <br> (ID)"])
        self.hist_trns_kva.object = self.gen_hist_trns_kva_fig(trns_name=row["Name <br> (ID)"])

    def update_lines_i_mag_plots(self, event):
        idx = event.row
        row = self.tbl_lines_summary.value.iloc[idx]
        self.plt_line_i_mag.object = self.gen_plt_line_i_mag_fig(line_name=row["Name <br> (ID)"])
        self.hist_line_i_mag.object = self.gen_hist_line_i_mag_fig(line_name=row["Name <br> (ID)"])

    def update_bus_v_mag_plots(self, event):
        idx = event.row
        row = self.tbl_bus_summary.value.iloc[idx]
        self.plt_bus_v_mag.object = self.gen_plt_bus_v_mag_fig(bus_name=row["Bus <br> (ID)"])
        self.hist_bus_v_mag.object = self.gen_hist_bus_v_mag_fig(bus_name=row["Bus <br> (ID)"])


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
        self.bus_loading_button.on_click(self.on_bus_loading_button_click)

        self.tbl_trns_summary.on_click(self.update_trns_kva_plots)
        self.tbl_lines_summary.on_click(self.update_lines_i_mag_plots)
        self.tbl_bus_summary.on_click(self.update_bus_v_mag_plots)

        self.new_session_button.js_on_click(code=self.new_session_js_code)

        pn.config.raw_css.append(css)

        app = pn.Column(
            pn.Row(
                self.save_button,
                self.new_session_button,
            ),
            pn.Row(
                self.simulation_description,
                self.simulation_summary,
            ),
            pn.layout.Card(
                pn.Column(
                    self.trns_loading_duration_options,
                    pn.Row(
                        self.trns_loading_slider,
                        self.trns_loading_duration_slider,
                        self.trns_loading_button,
                    ),
                    pn.Row(
                        self.bar_trns_loading_count,
                        pn.Column(
                            self.trns_loading_info,
                            self.tbl_trns_loading_count,
                        ),
                    ),
                ),
                title="Transformer Loading Summary",
                collapsed=False,
                height=600,
                min_width=900,
                sizing_mode='stretch_width',
            ),
            pn.Spacer(height=10),
            pn.layout.Card(
                pn.Column(
                    self.lines_loading_duration_options,
                    pn.Row(
                        self.lines_loading_slider,
                        self.lines_loading_duration_slider,
                        self.lines_loading_button,
                    ),
                    pn.Row(
                        self.bar_lines_p_loading_count,
                        pn.Column(
                            self.lines_p_loading_info,
                            self.tbl_lines_p_loading_count,
                        ),
                    ),
                    pn.Row(
                        self.bar_lines_s_loading_count,
                        pn.Column(
                            self.lines_s_loading_info,
                            self.tbl_lines_s_loading_count,
                        ),
                    ),
                ),
                title="Lines Loading Summary",
                collapsed=False,
                height=1050,
                min_width=900,
                sizing_mode='stretch_width',
            ),
            pn.Spacer(height=10),
            pn.layout.Card(
                pn.Column(
                    self.bus_loading_duration_options,
                    pn.Row(
                        self.bus_loading_slider,
                        self.bus_loading_duration_slider,
                        self.bus_loading_button,
                    ),
                    pn.Row(
                        self.hist_pcc_min_voltage,
                        pn.Column(
                            self.bus_loading_info,
                            self.tbl_bus_loading_count,
                        ),
                    ),
                ),
                title="PCC Bus Voltage Summary",
                collapsed=False,
                height=600,
                min_width=900,
                sizing_mode='stretch_width',
            ),
            pn.Spacer(height=10),
            pn.layout.Card(
                pn.Tabs(
                    ("Transformers", pn.Column(
                        self.tbl_trns_summary,
                        pn.Spacer(height=10),
                        pn.Tabs(
                            ("Time Series", self.plt_trns_kva),
                            ("Histogram", self.hist_trns_kva),
                            tabs_location='left',
                            min_width=900,
                            sizing_mode='stretch_width',
                        ),
                        sizing_mode='stretch_width',
                        ),
                    ),
                    ("Lines", pn.Column(
                        self.tbl_lines_summary,
                        pn.Spacer(height=10),
                        pn.Tabs(
                            ("Time Series", self.plt_line_i_mag),
                            ("Histogram", self.hist_line_i_mag),
                            tabs_location='left',
                            min_width=900,
                            sizing_mode='stretch_width',
                        ),
                        sizing_mode='stretch_width',
                        )
                    ),
                    ("Buses", pn.Column(
                        self.tbl_bus_summary,
                        pn.Spacer(height=10),
                        pn.Tabs(
                            ("Time Series", self.plt_bus_v_mag),
                            ("Histogram", self.hist_bus_v_mag),
                            tabs_location='left',
                            min_width=900,
                            sizing_mode='stretch_width',
                        ),
                        sizing_mode='stretch_width',
                        )
                    ),
                ),
                title="Analyze Individual Elements",
                collapsed=False,
                height=1070,
                min_width=900,
                sizing_mode='stretch_width',
                ),
            # pn.Row(self.tbl_ev_loads),
            min_width=900,
            sizing_mode='stretch_width',
        )
        return app
