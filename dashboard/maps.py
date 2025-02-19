import folium
from folium.map import Marker as FoliumMarker
from folium.plugins import MarkerCluster
import panel as pn

class Map():
    def __init__(self, init_coor, df) -> None:
        self.m = folium.Map(location=init_coor, zoom_start=12)
        marker_cluster = MarkerCluster().add_to(self.m)
  
        for index, xf in df.iterrows():
            x = xf['Longitude_X']
            y = xf['Latitude_Y']
            
            folium.Marker(
                location=[y , x],
                tooltip =  str(xf['Transformer ID']),
                #tooltip= "Transformer ID\n" + xf['Transformer ID'],
                popup = "Waypoint", # This popup menu could be improved and show more content in detail
                icon=folium.Icon(color="green"),
            ).add_to(marker_cluster)

        self.map = pn.pane.plot.Folium(self.m, height=500, width=800)

    def gen_map(self):
        return self.map
