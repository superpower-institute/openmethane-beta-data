"""
ESA_co_preprocess.py

Copyright 2016 University of Melbourne.
Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and limitations under the License.
"""

import os
import glob
import numpy as np
import datetime as dt

import context
from obsESA_defn import ObsSRON
from model_space import ModelSpace
from netCDF4 import Dataset
import fourdvar.util.file_handle as fh
from fourdvar.util.date_handle import start_date, end_date
from fourdvar.params.root_path_defn import store_path
import fourdvar.params.input_defn as input_defn
import math
##NS added:
import pdb

#-CONFIG-SETTINGS---------------------------------------------------------

#'filelist': source = list of OCO2-Lite files
#'directory': source = directory, use all files in source
#'pattern': source = file_pattern_string, use all files that match pattern
source_type = 'filelist'
     
#source = [ os.path.join( store_path, 'obs_src', 's5p_l2_co_0007_04270.nc' ) ]
source = ['/home/unimelb.edu.au/prayner/work/openmethane-beta/py4dvar/sat_data/data/20220701-00-00-00_20220702-23-59-59_104.0_-47.0_162.0_-6.0/S5P_OFFL_L2__CH4____20220702T040957_20220702T055126_24442_02_020301_20220703T200603.SUB.nc4']

output_file = input_defn.obs_file

# minimum qa_value before observation is discarded
qa_cutoff = 0.5
#--------------------------------------------------------------------------

model_grid = ModelSpace.create_from_fourdvar()

if source_type.lower() == 'filelist':
    filelist = [ os.path.realpath( f ) for f in source ]
elif source_type.lower() == 'pattern':
    filelist = [ os.path.realpath( f ) for f in glob.glob( source ) ]
elif source_type.lower() == 'directory':
    dirname = os.path.realpath( source )
    filelist = [ os.path.join( dirname, f )
                 for f in os.listdir( dirname )
                 if os.path.isfile( os.path.join( dirname, f ) ) ]
else:
    raise TypeError( "source_type '{}' not supported".format(source_type) )

obslist = []
for fname in filelist:
    print('read {}'.format( fname ))
    var_dict = {}
    with Dataset( fname, 'r' ) as f:
        instrument = f.groups['PRODUCT']
        meteo = f['/PRODUCT/SUPPORT_DATA/INPUT_DATA']
        product = f['/PRODUCT']
        diag = f['/PRODUCT']
        geo = f['/PRODUCT/SUPPORT_DATA/GEOLOCATIONS']
        
        latitude = instrument.variables['latitude'][:]
        latitude_center = latitude.reshape((latitude.size,))
        longitude = instrument.variables['longitude'][:]
        longitude_center = longitude.reshape((longitude.size,)) 
        timeUTC = instrument.variables['time_utc'][:]
        timeUTC = np.stack([timeUTC]*latitude.shape[2], axis=2)
        time = timeUTC.reshape((timeUTC.size,))           
        latitude_bounds = geo.variables['latitude_bounds'][:]
        latitude_corners = latitude_bounds.reshape((latitude.size,4))
        longitude_bounds = geo.variables['longitude_bounds'][:]
        longitude_corners = longitude_bounds.reshape((longitude.size,4))
        solar_zenith_deg = geo.variables['solar_zenith_angle'][:]
        solar_zenith_angle = solar_zenith_deg.reshape((solar_zenith_deg.size,))
        viewing_zenith_deg = geo.variables['viewing_zenith_angle'][:]       
        viewing_zenith_angle = viewing_zenith_deg.reshape((viewing_zenith_deg.size,))
        solar_azimuth_deg = geo.variables['solar_azimuth_angle'][:]
        solar_azimuth_angle = solar_azimuth_deg.reshape((solar_azimuth_deg.size,))
        viewing_azimuth_deg = geo.variables['viewing_azimuth_angle'][:]
        viewing_azimuth_angle = viewing_azimuth_deg.reshape((viewing_azimuth_deg.size,))
        pressure_interval = meteo.variables['pressure_interval'][:,:]
#        pressure_levels = pressure.reshape((latitude.size,50))
        ch4 = product.variables['methane_mixing_ratio_bias_corrected'][...]
        ch4_column = ch4.reshape((ch4.size,))
        ch4_precision = product.variables['methane_mixing_ratio_precision'][:]
        ch4_column_precision = ch4_precision.reshape((ch4_precision.size,))
        ch4_averaging_kernel = product['SUPPORT_DATA/DETAILED_RESULTS/column_averaging_kernel'][...]
        averaging_kernel = np.reshape( ch4_averaging_kernel, (-1,ch4_averaging_kernel.shape[-1]))
        #ch4_column_apriori = product.variables['ch4_column_apriori'][:]
        #ch4_profile_apriori = product.variables['ch4_profile_apriori'][:,:]
        qa = diag.variables['qa_value'][:]
        qa_value = qa.reshape((qa.size,))


    mask_arr = np.ma.getmaskarray( ch4_column )

    #quick filter out: mask, lat, lon and quality
    lat_filter = np.logical_and( latitude_center>=model_grid.lat_bounds[0],
                                 latitude_center<=model_grid.lat_bounds[1] )                          
    lon_filter = np.logical_and( longitude_center>=model_grid.lon_bounds[0],
                                 longitude_center<=model_grid.lon_bounds[1] )                               
    mask_filter = np.logical_not( mask_arr )
    qa_filter = ( qa_value > qa_cutoff )
    include_filter = np.logical_and.reduce((lat_filter,lon_filter,mask_filter,qa_filter))

    epoch = dt.datetime.utcfromtimestamp(0)
    sdate = dt.datetime( start_date.year, start_date.month, start_date.day )
    edate = dt.datetime( end_date.year, end_date.month, end_date.day )
    size = include_filter.sum()
    print('found {} soundings'.format( size ))
    for i,iflag in enumerate(include_filter):
        if iflag:
            #scanning time is slow, do it after other filters.
            #tsec = (dt.datetime(*time[i,:])-epoch).total_seconds()
            dt_time = dt.datetime.strptime( time[i][0:19], '%Y-%m-%dT%H:%M:%S' )
            tsec = (dt_time-epoch).total_seconds()
            time0 = (sdate-epoch).total_seconds()
            time1 = (edate-epoch).total_seconds() + 24*60*60
            if tsec < time0 or tsec > time1:
                continue
            ###reading reference profile 
            Ref_file=   glob.glob('Path to ref profile output directory/Ref_profile{}*.nc'.format(time[i][0:10])) 
            for f in Ref_file:
              #print 'read {}'.format( f )
              with Dataset( f, 'r' ) as f:
                if (f.dimensions['nobs'].size==size):
                  ch4_profile_apriori = f.variables['CH4_profile_apriori'][:] 
                  ch4_column_apriori = f.variables['CH4_column_apriori'][:] 
                  lat_check = f.variables['LAT'][:] 
                  lon_check = f.variables['LON'][:] 
                  
            var_dict = {}
            #var_dict['time'] = dt.datetime( *time[0,i] )
            var_dict['time'] = dt.datetime.strptime( time[i][0:19], '%Y-%m-%dT%H:%M:%S' )
            var_dict['latitude_center'] = latitude_center[i]
            var_dict['longitude_center'] = longitude_center[i]
            var_dict['latitude_corners'] = latitude_corners[i,:]
            var_dict['longitude_corners'] = longitude_corners[i,:]
            var_dict['solar_zenith_angle'] = solar_zenith_angle[i]
            var_dict['viewing_zenith_angle'] = viewing_zenith_angle[i]
            var_dict['solar_azimuth_angle'] = solar_azimuth_angle[i]
            var_dict['viewing_azimuth_angle'] = viewing_azimuth_angle[i]
            press_levels=np.zeros([51]) ##we need to put pressure=0 at the first leveli
            for j in range(1,51):
             press_levels[j]= pressure_levels[i,j-1]
            var_dict['pressure_levels'] = press_levels
            var_dict['ch4_column'] = ch4_column[i]
            var_dict['ch4_column_precision'] = ch4_column_precision[i]
            var_dict['obs_kernel'] = averaging_kernel [i,:]
            var_dict['qa_value'] = qa_value[i]
            
            ###find the proper index for ch4_profile_apriori:
            for j in range(size): 
              if (lat_check[j]==latitude_center[i]) and (lon_check[j]==longitude_center[i]):            
                var_dict['ch4_profile_apriori'] = ch4_profile_apriori[j,:]
                var_dict['ch4_column_apriori'] = ch4_column_apriori[j]

            obs = ObsSRON.create( **var_dict )           
            obs.interp_time = False
            obs.model_process( model_grid )           
            if obs.valid is True:
                obslist.append( obs.get_obsdict() )
                ##pdb.set_trace() ##NS added
if len( obslist ) > 0:
    domain = model_grid.get_domain()
    domain['is_lite'] = False
    datalist = [ domain ] + obslist     
    fh.save_list( datalist, output_file )
    print('recorded observations to {}'.format( output_file ))
else:
    print('No valid observations found, no output file generated.')
