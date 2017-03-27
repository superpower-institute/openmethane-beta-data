"""
application: simulate set of observations from output of the forward model
like all transform in transfunc this is referenced from the transform function
eg: transform( model_output_instance, datadef.ObservationData ) == obs_operator( model_output_instance )
"""

import numpy as np

import _get_root
from fourdvar.datadef import ModelOutputData, ObservationData
import fourdvar.util.obs_handle as obs_handle
import fourdvar.params.template_defn as template
import fourdvar.util.netcdf_handle as ncf

def obs_operator( model_output ):
    """
    application: simulate set of observations from output of the forward model
    input: ModelOutputData
    output: ObservationData
    """
    
    sim_obs = ObservationData.load_blank( template.obsmeta )
    msg = 'obsmeta and conc templates have different griddata'
    assert sim_obs.check_grid( template.conc ) is True, msg
    
    obs_by_date = obs_handle.get_obs_by_date( sim_obs )
    
    for ymd, obslist in obs_by_date.items():
        conc_file = model_output.file_data['conc.'+ymd]['actual']
        spcs = obs_handle.get_obs_spcs( obslist )
        var_dict = ncf.get_variable( conc_file, spcs )
        for obs in obslist:
            if obs.value is None:
                obs.value = 0
            for coord,weight in obs.weight_grid.items():
                if str( coord[0] ) == ymd:
                    step,lay,row,col,spc = coord[1:]
                    conc = var_dict[spc][step,lay,row,col]
                    obs.value += ( weight * conc )
    
    for obs in sim_obs.dataset:
        if obs.value is None:
            obs.valid = False
    return sim_obs

