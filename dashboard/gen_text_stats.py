import pandas as pd
from actions import get_stats, DataOperator
import panel as pn 

def gen_stats_md(data, threshold, dop, controller):

        
        stats_baseload = get_stats(data['baseload'], threshold)
        stats_evload = get_stats(data['evload'], threshold)
        stats_total = get_stats(data['total'], threshold)
        ID = data['ID']

        num_of_evs = len(dop.mappings['xf_mappings'][dop.feeder][int(ID)]['vehicles'])
        num_of_houses = len(dop.mappings['xf_mappings'][dop.feeder][int(ID)]['premises'])

        text = f"""
            <style type="text/css">
            .tg  {{border:none;border-collapse:collapse;border-spacing:0;}}
            .tg td{{border-style:solid;border-width:0px;font-family:Arial, sans-serif;font-size:14px;overflow:hidden;padding:3px 5px;
            word-break:normal;}}
            .tg th{{border-style:solid;border-width:0px;font-family:Arial, sans-serif;font-size:14px;font-weight:normal;
            overflow:hidden;padding:2px 5px;word-break:normal;}}
            .tg .tg-1wig{{font-weight:bold;text-align:left;vertical-align:top}}
            .tg .tg-tf2e{{text-align:left;vertical-align:top}}
            .tg .tg-0lax{{text-align:left;vertical-align:top}}
            .tg .tg-3kij{{font-weight:bold;text-align:left;vertical-align:top}}
            </style>
            <table class="tg"><thead>
            <tr style="border-top: 2px solid; border-bottom: 2px solid;">
                <th class="tg-spag" colspan="2" style="border-right: 2px solid;"><span style="font-weight:bold">Transformer ID</span></th>
                <th class="tg-spag" colspan="2"><span style="font-weight:bold">{ID}</span></th>
            </tr></thead>
            <tbody>
            <tr>
                <td class="tg-2bhk" colspan="2" style="border-right: 2px solid;">Number of houses</td>
                <td class="tg-8nwd" colspan="2">{num_of_houses}</td>
            </tr>
            <tr style="border-bottom: 2px solid;">
                <td class="tg-0pky" colspan="2" style="border-right: 2px solid;">Number of EVs</td>
                <td class="tg-fymr" colspan="2">{num_of_evs}</td>
            </tr>
            <tr style="border-bottom: 2px solid;">
                <td class="tg-es04" colspan="2" style="border-right: 2px solid;"><span style="font-weight:bold">Baseload</span></td>
                <td class="tg-es04" colspan="2"><span style="font-weight:bold">Baseload + EV ({controller})</span></td>
            </tr>
            <tr>
                <td class="tg-0pky">Max load (kVA)</td>
                <td class="tg-7btt" style="border-left: 2px solid; border-right: 2px solid;">{stats_baseload['max']:.2f}</td>
                <td class="tg-0pky">Max load (kVA)</td>
                <td class="tg-7btt" style="border-left: 2px solid; border-right: 2px solid;">{stats_total['max']:.2f}</td>
            </tr>
            <tr>
                <td class="tg-2bhk">Min load (kVA)</td>
                <td class="tg-uw39" style="border-left: 2px solid; border-right: 2px solid;">{stats_baseload['min']:.2f}</td>
                <td class="tg-2bhk">Min load (kVA)</td>
                <td class="tg-uw39" style="border-left: 2px solid; border-right: 2px solid;">{stats_total['min']:.2f}</td>
            </tr>
            <tr>
                <td class="tg-0pky">Avg load (kVA)</td>
                <td class="tg-7btt" style="border-left: 2px solid; border-right: 2px solid;">{stats_baseload['avg']:.2f}</td>
                <td class="tg-0pky">Avg load (kVA)</td>
                <td class="tg-7btt" style="border-left: 2px solid; border-right: 2px solid;">{stats_total['avg']:.2f}</td>
            </tr>
            <tr>
                <td class="tg-2bhk">Duration above {threshold} kVA</td>
                <td class="tg-8nwd" style="border-left: 2px solid; border-right: 2px solid;">{stats_baseload['dat']:.2f}h</td>
                <td class="tg-2bhk">Duration above {threshold} kVA</td>
                <td class="tg-uw39" style="border-left: 2px solid; border-right: 2px solid;">{stats_total['dat']:.2f}h</td>
            </tr>
            <tr>
                <td class="tg-0pky">Likelihood of overload above {threshold} kVA</td>
                <td class="tg-fymr" style="border-left: 2px solid; border-right: 2px solid;">{stats_baseload['lot']:.2f}%</td>
                <td class="tg-0pky">Likelihood of overload above {threshold} kVA</td>
                <td class="tg-7btt" style="border-left: 2px solid; border-right: 2px solid;">{stats_total['lot']:.2f}%</td>
            </tr>
            <tr>
                <td class="tg-2bhk"></td>
                <td class="tg-2bhk" style="border-right: 2px solid;"></td>
                <td class="tg-2bhk">Percent increase in load due to EVs </td>
                <td class="tg-uw39" style="border-left: 2px solid; border-right: 2px solid;">{(float(stats_total['max'])-float(stats_baseload['max']))/float(max(1, stats_baseload['max'])) * 100:.2f}%</td>
            </tr>
            </tbody></table>
        """

        return text

def gen_text_stats(pane, data, dop, threshold, controller):

    threshold_slider = pn.widgets.FloatSlider(name='Threshold (kVA)', start=0, end=2*threshold, step=1, value=threshold)
    btn_eval_threshold = pn.widgets.Button(name='Compute', button_type='primary', align=('center','center'))

    def cal_stats(event):
        print('Threshold value is ', threshold_slider.value)
        markdown_text = gen_stats_md(data, threshold_slider.value, dop, controller) 
        text_stats = pn.Column(pn.Row(threshold_slider, btn_eval_threshold), markdown_text)
        pane[:] = [text_stats]

    btn_eval_threshold.on_click(cal_stats)

    markdown_text = gen_stats_md(data, threshold, dop, controller)    
    text_stats = pn.Column(pn.Row(threshold_slider, btn_eval_threshold), markdown_text)
    pane[:] = [text_stats]


