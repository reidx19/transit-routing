"""
Runs the query algorithm
"""
import os
from pathlib import Path
user_directory = os.fspath(Path.home())
file_directory = r"\Documents\GitHub\transit-routing" #directory of bikewaysim outputs
homeDir = user_directory+file_directory
os.chdir(homeDir)

#%%

#post processing specific
from datetime import datetime, timedelta, date
from shapely.ops import LineString, MultiLineString
import geopandas as gpd
import pandas as pd
import numpy as np
import pickle
from tqdm import tqdm
import time
import glob

#suppress error message
import warnings
from shapely.errors import ShapelyDeprecationWarning
warnings.filterwarnings("ignore", category=ShapelyDeprecationWarning) 
warnings.filterwarnings("ignore", category=FutureWarning) 
#warnings.filterwarnings("ignore", category=SettingWithCopyWarning) 

#%%

#make sure thing is str
def check_type(item):
    if type(item) == float:
        item = str(int(item))
    elif type(item) == int:
        item = str(item)      
    return item


def map_routes(selected_trips,impedance_col,snapped_tazs,snapped_stops,shape_map):

    #import bike path geo
    with open(rf'C:\Users\tpassmore6\Documents\TransitSimData\Data\Outputs\{impedance_col}_all_paths.pkl','rb') as fh:
        all_paths = pickle.load(fh)
    
    for selected_trip in selected_trips:
    
        with open(selected_trip,'rb') as fh:
            trip_dict = pickle.load(fh)
    
        #process text
        file_path = os.path.split(selected_trip)[-1].split('.pkl')[0]
        
        #get taz name
        start_taz = file_path.split('_')[0]
        
        #get start time
        trip_time = file_path.split('_')[1] + '_' + file_path.split('_')[2]
        
        #flm mode
        flm_mode = file_path.split('_')[3]
    
    
        for x in tqdm(trip_dict.keys()):
            start_taz = check_type(x[0])
            end_taz = check_type(x[1])
            
            start_transit = check_type(trip_dict[x][3])
            end_transit = check_type(trip_dict[x][4])
        
            #get OSM nodes to get path from all paths    
            start_tazN = snapped_tazs[start_taz]
            end_tazN = snapped_tazs[end_taz]
            start_transitN = snapped_stops[start_transit]
            end_transitN = snapped_stops[end_transit]
        
            #get bike edge if available
            #also get impedance values
            if (start_tazN,start_transitN) in all_paths.keys():
                bike_edge1 = all_paths[(start_tazN,start_transitN)]
            else:
                bike_edge1 = None
            
            if (end_transitN,end_tazN) in all_paths.keys():
                bike_edge2 = all_paths[(end_transitN,end_tazN)]
            else:
                bike_edge2 = None
                
            #get transit edges
            edge_list = trip_dict[x][0]
        
            transit_edges = []
            route_types = []
            route_ids = []
            start_stop = []
            end_stop = []
            time_spent = []
        
            #TODO function for getting transit shapes instead of connnecting start/end nodes
            for edge in edge_list:
                
                #get start station, end station, and tripid
                start = edge[0]
                end = edge[1]
                
                #append
                start_stop.append(check_type(start))
                end_stop.append(check_type(end))
                time_spent.append(edge[2].total_seconds()/60)
                
                #get start and end stops points
                start_point = stops_file.loc[stops_file['stop_id'] == start,'geometry'].drop_duplicates().item()
                end_point = stops_file.loc[stops_file['stop_id'] == end,'geometry'].drop_duplicates().item()
                
                #get transit specific info
                if edge[-1] in ['rail','bus']:
                    #extract trip_id
                    trip_id = check_type(edge[3])
        
                    #extract route_id
                    route_id = str.split(trip_id,'_')[0]
                    route_ids.append(route_id)
                    
                    #get transit type
                    route_type = edge[-1]
                    route_types.append(route_type)
                    
                    #get shape_id
                    shape_id = shape_map[shape_map['new_route_id'] == route_id]
                    
                    #just go with first one
                    shape_id = shape_id.iloc[0,0]
                    
                    #candidate_lines = []
                    
                    #there are multiple shape ids for the same route
                    #for shape_id in shape_ids['shape_id'].tolist():
                        
                    #filter shapes
                    shape = feed.shapes[feed.shapes['shape_id']==shape_id].copy()
                    
                    #make the pt sequence the index
                    shape.index = shape['shape_pt_sequence']
                    
                    #create geo column
                    shape.loc[:,'geometry'] = gpd.points_from_xy(shape['shape_pt_lon'],shape['shape_pt_lat'])
                    
                    #turn to gdf
                    shape = gpd.GeoDataFrame(shape,geometry='geometry',crs='epsg:4326')
                    
                    #project
                    shape.to_crs('epsg:2240',inplace=True)
                    
                    #get start pt sequence (snap start stop to geometry)
                    start_point_snapped = shape.distance(start_point).idxmin()
                    
                    #get end pt sequence
                    end_point_snapped = shape.distance(end_point).idxmin()
                    
                    #make sure they aren't the same points
                    #if start_point_snapped != end_point_snapped:
                    #only get shape points needed
                    if start_point_snapped < end_point_snapped:
                        line = shape.loc[start_point_snapped:end_point_snapped]
                    else:
                        line = shape.loc[end_point_snapped:start_point_snapped]
                        
                    #get linestring
                    line = LineString(line['geometry'].to_list())
                    
                        #append to candidate list
                        #candidate_lines.append(line)
                        
                    #get whatever the longest segment is
                    #candidate_lines = gpd.GeoSeries(candidate_lines,crs='epsg:2240')
                    #line = #candidate_lines.loc[candidate_lines.length.idxmax()]
                    
                else:
                    route_types.append('walking')
                    route_ids.append('walking')
                    line = LineString([start_point,end_point])
                    
                #replace the edge
                transit_edges.append(line) 
        
            if (bike_edge1 is not None) & (bike_edge2 is not None):
                route_types = ['bike'] + route_types + ['bike']
                start_stops = [start_taz] + start_stop + [start]
                end_stops = [end] + end_stop + [end_taz]
                route_ids = ['bike'] + route_ids + ['bike']
                time_spent = [bike_edge1.length] + time_spent + [bike_edge2.length]
                geometry = [bike_edge1] + transit_edges + [bike_edge2]
            elif (bike_edge1 is None) & (bike_edge2 is None):
                route_types = route_types
                start_stops = start_stop
                end_stops = end_stop
                route_ids = route_ids
                time_spent = time_spent
                geometry = transit_edges
            elif bike_edge1 is None:
                route_types = route_types + ['bike']
                start_stops = start_stop + [end]
                end_stops = end_stop + [end_taz]
                route_ids = route_ids + ['bike']
                time_spent = time_spent + [bike_edge2.length]
                geometry = transit_edges + [bike_edge2]
            elif bike_edge2 is None:
                route_types = ['bike'] + route_types
                start_stops = [start_taz] + start_stop
                end_stops = [start] + end_stop
                route_ids = ['bike'] + route_ids
                time_spent = [bike_edge1.length] + time_spent
                geometry = [bike_edge1] + transit_edges
        
            #create gdf
            gdf = pd.DataFrame(data={'start_stop':start_stops,'end_stop':end_stops,'mode':route_types,
                                     'route_ids':route_ids,'time':time_spent,'geometry':geometry})
            gdf = gpd.GeoDataFrame(gdf,geometry='geometry',crs='epsg:2240')
        
            #export
            trip_name = str(x[0]) + '_' + str(x[1])
        
            #create new folder
            if not os.path.exists(rf'C:\Users\tpassmore6\Documents\TransitSimData\Data\Outputs\mapped\{start_taz}\{impedance_col}'):
                os.makedirs(rf'C:\Users\tpassmore6\Documents\TransitSimData\Data\Outputs\mapped\{start_taz}\{impedance_col}') 
            
            gdf.to_file(rf'C:\Users\tpassmore6\Documents\TransitSimData\Data\Outputs\mapped\{start_taz}\{impedance_col}\{trip_name}.gpkg',layer=f'{flm_mode}_{trip_time}')
        #gdf.to_file(rf'C:\Users\tpassmore6\Documents\TransitSimData\Data\mapped\testing.gpkg',layer=trip_name,driver='GPKG')

#%% run

#set network name
#NETWORK_NAME = './marta'

#get route type
route = pd.read_csv(r'GTFS/marta/route.txt')

#get stops
stops_file = pd.read_csv('GTFS/marta/stops.txt')
stops_file = gpd.GeoDataFrame(stops_file, geometry=gpd.points_from_xy(stops_file['stop_lon'], stops_file['stop_lat']), crs='epsg:4326')
stops_file.to_crs('epsg:2240',inplace=True)

#get shapes from partrigh
import partridge as ptg

path = r'marta_gtfs.zip'#'gtfs.zip'

_date = date(2022, 11, 24)

service_ids = ptg.read_service_ids_by_date(path)
service_ids = service_ids[_date]

view = {'trips.txt': {'service_id': service_ids}}

#get gtfs feed
feed = ptg.load_feed(path, view)

# make sure both str
route['route_id'] = route['route_id'].astype(str)
feed.trips['route_id'] = feed.trips['route_id'].astype(str)

#shape id is in og trips file
#merge route and trips using old route id
shape_map = route.merge(feed.trips[['route_id','shape_id']], on='route_id')[['shape_id','new_route_id']].drop_duplicates()
shape_map['new_route_id'] = shape_map['new_route_id'].astype(str)

#import snapped tazs and stops
with open(r'C:\Users\tpassmore6\Documents\TransitSimData\Data\snapped_tazs.pkl','rb') as fh:
    snapped_tazs = pickle.load(fh)
with open(r'C:\Users\tpassmore6\Documents\TransitSimData\Data\snapped_stops.pkl','rb') as fh:
    snapped_stops = pickle.load(fh)


impedance_col = 'dist'
#select_tazs = ['448','411','1272','225']
trips_dir = os.fspath('C:/Users/tpassmore6/Documents/TransitSimData/Data/Outputs/trip_dicts')
all_trips= glob.glob(os.path.join(trips_dir,rf"{impedance_col}/*.pkl"))


#all_trips = [f'C:/Users/tpassmore6/Documents/TransitSimData/Data/Outputs/trip_dicts/dist\\{taz}.pkl' for taz in select_tazs]
map_routes(all_trips,impedance_col,snapped_tazs,snapped_stops,shape_map)

# impedance_col = 'imp_dist'
# select_tazs = ['448','411','1272','225']
# all_trips = [f'C:/Users/tpassmore6/Documents/TransitSimData/Data/Outputs/trip_dicts/dist\\{taz}.pkl' for taz in select_tazs]
# map_routes(all_trips,impedance_col,snapped_tazs,snapped_stops,shape_map)

#%%

