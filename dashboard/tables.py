from bokeh.models.widgets.tables import NumberFormatter, BooleanFormatter
import panel as pn

class Table:

    def __init__(self, df, theme = 'simple') -> None:

        stylesheet = """
        .tabulator-cell {
            font-size: 10pt;
        }
        .tabulator-col-title {
            font-size: 10pt;
        }
        """

        bokeh_formatters = {
            'Transformer ID': NumberFormatter(format='00000000')
        }

        # This filter can be automatically generated.
        filters = {
            'Transformer ID': {'type': 'input', 'func': 'like', 'placeholder': 'Enter XF'},
            'Bank Size': {'type': 'input', 'func': 'like', 'placeholder': 'Enter size'},
            'Num of Prems': {'type': 'input', 'func': '>=', 'placeholder': '>= X'},
            'Num of EVs': {'type': 'input', 'func': '>=', 'placeholder': '>= X'},
            'Max Overload (%)': {'type': 'input', 'func': '>=', 'placeholder': '>= X%'},
            'Output Voltage': {'type': 'input', 'func': 'like', 'placeholder': 'Enter voltage'}
        }  

        self.table = pn.widgets.Tabulator(df, 
                                          disabled=True,
                                          theme=theme, 
                                          page_size=14, 
                                          stylesheets=[stylesheet],
                                          formatters=bokeh_formatters,
                                          theme_classes=['thead-dark', 'table-sm'],
                                          header_filters=filters,
                                          height=500,
                                          text_align='center',
                                          align=('center','center'))
        
    def gen_table(self):
        return self.table    


