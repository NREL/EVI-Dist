import sys
from abc import ABC, abstractmethod
import plotly.graph_objs as go
import plotly.express as px
import random
import statistics as stats
import numpy as np

from matplotlib.figure import Figure
from matplotlib import cm

import matplotlib.pyplot as plt

# sys.path.append('../')
# from modules.data_structures import Signal


class Plot(ABC):

    def __init__(self) -> None:
        self.fig : go.Figure
    #     self.params = params
    #     self.signal = signal
        self.color = {}

    def _update_theme(self, params):

        if params['theme'] == 'plotly_white':
            self.color['title'] = 'black'
            self.color['line'] = 'black'
            self.color['grid'] = '#d6dbdf'
        else:
            self.color['title'] = 'white'
            self.color['line'] = 'white'
            self.color['grid'] = '#515a5a'

    
    @abstractmethod
    def gen_plot(self):
        # Generate the actual plotly object to return
        pass

    @abstractmethod # argument should be of some type, like a time series
    def add_trace(self, signal : dict, color_seq : int):
        pass

    def set_res(self, res : int):
        pass

    def set_xlabel(self, label : str):
        self.fig.update_layout(xaxis=dict(title=label))

    def set_ylabel(self, label : str):
        self.fig.update_layout(yaxis=dict(title=label))

    def set_title(self, title : str):
        self.fig.update_layout(title=title)

    def set_width(self, width : int):
        self.fig.update_layout(width=width)

    def set_height(self, height : int):
        self.fig.update_layout(height=height)

    def set_xlim(self, lim : list):
        self.fig.update_layout(xaxis=dict(range=lim))

    def set_ylim(self, lim : list):
        self.fig.update_layout(yaxis=dict(range=lim))

    def save(self, filename : str):
        pass

    def set_fontsize(self, size : int):
        self.fig.update_layout(
            xaxis=dict(tickfont=dict(size=size)),  # Adjust size of x-axis ticks
            yaxis=dict(tickfont=dict(size=size))  # Adjust size of y-axis ticks
        )    

class LinePlot(Plot):
    
    def __init__(self, signal, params) -> None:

        super().__init__()

        self.signal = signal
        self.params = params
        self.fig = go.Figure()
        self.color_seq = px.colors.qualitative.D3

    def gen_plot(self):
        
        self._update_theme(self.params)
        
        trace = go.Scatter(x=self.signal.x, y=self.signal.y, name=self.signal.name, showlegend=True, line=dict(color=self.color_seq[0]))
        self.fig.add_trace(trace)
        self.fig.update_layout(title=self.params['title'], 
                               xaxis_title=self.params['xlabel'], 
                               yaxis_title=self.params['ylabel'], 
                               template=self.params['theme'], 
                               width=self.params['width'], 
                               height=self.params['height'])
        self.fig.update_layout(font_size=self.params['fontsize'])
        self.fig.update_traces(line_shape='hv')

        decimation = int(len(self.signal.x)/7)

        # self.fig.update_layout(
        #     xaxis = dict(
        #     showgrid =True,
        #     tickmode = 'array',
        #     tickvals = self.signal.x[::decimation],
        #     tickformat='%b %d'),
        #     yaxis = dict(showgrid=True)
        # )
        self.fig.update_layout(
            xaxis = dict(
            tickformat='%A\n%H:%M:%S',
            dtick="D1",
            tickmode="auto"),
            yaxis = dict(showgrid=True)
        )
        self.fig.update_layout(
            xaxis=dict(tickfont=dict(size=self.params['fontsize'])),  # Adjust size of x-axis ticks
            yaxis=dict(tickfont=dict(size=self.params['fontsize']))  # Adjust size of y-axis ticks
        )
        self.fig.update_layout(
            title={
                'y':0.95,  # Vertical position: 0 (bottom) to 1 (top)
                'x':0.0,  # Horizontal position: 0 (left) to 1 (right)
                'xanchor': 'left',  # Title text horizontal alignment
                'yanchor': 'top'      # Title text vertical alignment
            }
        )
        # self.fig.update_layout(
        #     xaxis=dict(range=[0, max(self.signal.x)]), # Set xlim
        # )
        self.fig.update_layout(
            #title='',  # Remove the title
            margin=dict(l=50, r=10, t=80, b=50)  # Adjust margins to reduce spacing
        )
        self.fig.update_layout(
            plot_bgcolor='rgba(0,0,0,0)',  # Set plot area background to transparent
            paper_bgcolor='rgba(0,0,0,0)'  # Set paper (outer) area background to transparent
        )

        self.fig.update_xaxes(title_font_color=self.color['title'], linewidth=1, linecolor=self.color['line'])
        self.fig.update_yaxes(title_font_color=self.color['title'], linewidth=1, linecolor=self.color['line'])

        self.fig.update_layout(
            xaxis=dict(
                gridcolor=self.color['grid'],  # Set the color of the gridlines
                gridwidth=0.5  # Set the width of the gridlines
            ),
            yaxis=dict(
                gridcolor=self.color['grid'],  # Set the color of the gridlines
                gridwidth=0.5  # Set the width of the gridlines
            )
        )
        self.fig.update_layout(legend=dict(orientation='h', yanchor='top', y=1.2, xanchor='right', x=1))

        return self.fig

    def add_trace(self, signal : dict, color_seq : int):
        #print(self.color_seq)
        #print(type(print(self.color_seq)))
        trace = go.Scatter(x=signal.x, y=signal.y, name=signal.name, showlegend=True, line=dict(color=self.color_seq[color_seq]))
        self.fig.add_trace(trace)

class SimpleLinePlot(Plot):

    def __init__(self, params, fig_type="notebook"):
        self.params = params
        if fig_type == "notebook":
            self.fig = plt.figure(figsize=(8,3))
        else:
            self.fig = Figure(figsize=(8,3))
        self.axis = self.fig.subplots(nrows=params['nrows'], ncols=params['ncols'])
        self.axis = self.axis.flatten()

    def gen_plot(self, signal, label, pos=0):
        line, = self.axis[pos].plot(signal.x, signal.y, label=label)
        return line

    def add_trace(self, signal, label, pos=0): # This is a dublicate of gen_plot, so it is reduntant. Added for consistency, but can be removed in future. 
        line, =  self.axis[pos].plot(signal.x, signal.y, label=label)
        return line

    def add_bar(self, signal, label, pos=0):
        bar = self.axis[pos].bar(signal.x, signal.y, label=label)
        return bar

    def add_text(self, coord : tuple(), text, color, ha, va, pos=0):
        self.axis[pos].text(coord[0], coord[1], text, color, ha, va)

class BarPlot(Plot):
    def __init__(self, params):
        pass

    def gen_plot(self):
        pass

class HistogramPlot(Plot):

    def __init__(self, signal, params) -> None:

        super().__init__()

        self.signal = signal
        self.params = params
        self.color_seq = px.colors.qualitative.D3
        self.fig = go.Figure()


    def gen_plot(self):
        
        self._update_theme(self.params)
        trace = go.Histogram(x=self.signal.y, name=self.signal.name, marker=dict(color=self.color_seq[0]))
        self.fig.add_trace(trace)

        self.fig.update_layout(title=self.params['title'], 
                               xaxis_title=self.params['xlabel'], 
                               yaxis_title=self.params['ylabel'], 
                               template=self.params['theme'], 
                               width=self.params['width'], 
                               height=self.params['height'])
        self.fig.update_layout(font_size=self.params['fontsize'])
        self.fig.update_layout(barmode='overlay')
        self.fig.update_traces(opacity=0.75)
        self.fig.update_layout(xaxis=dict(showgrid=True),
                               yaxis=dict(showgrid=True))
        self.fig.update_layout(
            xaxis=dict(tickfont=dict(size=self.params['fontsize'])),  # Adjust size of x-axis ticks
            yaxis=dict(tickfont=dict(size=self.params['fontsize']))  # Adjust size of y-axis ticks
        )
        self.fig.update_layout(
            title={
                'y':0.95,  # Vertical position: 0 (bottom) to 1 (top)
                'x':0.0,  # Horizontal position: 0 (left) to 1 (right)
                'xanchor': 'left',  # Title text horizontal alignment
                'yanchor': 'top'      # Title text vertical alignment
            }
        )
        self.fig.update_layout(
            margin=dict(l=50, r=10, t=80, b=50)  # Adjust margins to reduce spacing
        )

        self.fig.update_layout(
            plot_bgcolor='rgba(0,0,0,0)',  # Set plot area background to transparent
            paper_bgcolor='rgba(0,0,0,0)'  # Set paper (outer) area background to transparent
        )

        self.fig.update_xaxes(title_font_color=self.color['title'], linewidth=1, linecolor=self.color['line'])
        self.fig.update_yaxes(title_font_color=self.color['title'], linewidth=1, linecolor=self.color['line'])

        self.fig.update_layout(
            xaxis=dict(
                gridcolor=self.color['grid'],  # Set the color of the gridlines
                gridwidth=0.5  # Set the width of the gridlines
            ),
            yaxis=dict(
                gridcolor=self.color['grid'],  # Set the color of the gridlines
                gridwidth=0.5  # Set the width of the gridlines
            )
        )

        self.fig.update_layout(legend=dict(orientation='h', yanchor='top', y=1.2, xanchor='right', x=1))

        return self.fig
    
    def add_trace(self, signal : dict, color_seq : int):
        trace = go.Histogram(x=signal.y, name=signal.name, marker=dict(color=self.color_seq[color_seq]))
        self.fig.add_trace(trace)

# Factory method
def gen_plot_object(signal, params : dict):
    # signal contains the x,y values
    # type may contain info about how the specific figure paremeters should be
    if params['type'] == 'timeseries':
        return LinePlot(signal, params)
    
    elif params['type'] == 'histogram':
        return HistogramPlot(signal, params)
    


