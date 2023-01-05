"""
Author: Mikhail Schee
Created: 2022-03-31

This script contains helper functions which filter data and create figures

"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib as mpl
# For making insets in plots
from mpl_toolkits.axes_grid1.inset_locator import inset_axes
# For formatting data into dataframes
import pandas as pd
# For matching regular expressions
import re
# For formatting date objects
from datetime import datetime
# For reading netcdf files
import xarray as xr
# Import the Thermodynamic Equation of Seawater 2010 (TEOS-10) from GSW
# For finding alpha and beta values
import gsw
# For adding subplot labels a, b, c, ...
import string
# For taking moving averages
import scipy.ndimage as ndimage
# For interpolating
from scipy import interpolate
# For making clusters
import hdbscan
# For computing Adjusted Rand Index
from sklearn import metrics
# For calculating the distance between pairs of (latitude, longitude)
from geopy.distance import geodesic

"""
To install Cartopy and its dependencies, follow:
https://scitools.org.uk/cartopy/docs/latest/installing.html#installing

Relevent command:
$ conda install -c conda-forge cartopy
"""
import cartopy.crs as ccrs
import cartopy.feature

science_data_file_path = '/Users/Grey/Documents/Research/Science_Data/'

# This list gets filled in with the names of all the available columns for the
#   given data during the `apply_data_filters()` function
available_variables_list = []

################################################################################
# Declare variables for plotting
################################################################################
dark_mode = True

# Enable dark mode plotting
if dark_mode:
    plt.style.use('dark_background')
    std_clr = 'w'
    alt_std_clr = 'yellow'
    clr_ocean = 'k'
    clr_land  = 'grey'
    clr_lines = 'w'
else:
    std_clr = 'k'
    alt_std_clr = 'olive'
    clr_ocean = 'w'
    clr_land  = 'grey'
    clr_lines = 'k'
# Other colors
clr_ml = 'tab:green'
clr_gl = 'tab:orange'

# Set some plotting styles
mrk_size      = 0.5
mrk_alpha     = 0.4 #0.05
noise_alpha   = 0.1 #0.01
pf_alpha      = 0.5
lgnd_mrk_size = 60
map_mrk_size  = 7
big_map_mrkr  = 80
cent_mrk_size = 30
pf_mrk_size   = 15
layer_mrk_size= 10
std_marker = '.'
map_marker = '.' #'x'
map_ln_wid = 0.5
l_cap_size = 3.0
l_marker   = '+'

# The magnitude limits for axis ticks before they use scientific notation
sci_lims = (-3,3)

#   Get list of standard colors
mpl_clrs = plt.rcParams['axes.prop_cycle'].by_key()['color']
#   Make list of marker styles
mpl_mrks = ['o', 'x', 'd', '*', '<', '>','+']
# Define array of linestyles to cycle through
l_styles = ['-', '--', '-.', ':']

# Set random seed
rand_seq = np.random.RandomState(1234567)

# A list of variables for which the y-axis should be inverted so the surface is up
y_invert_vars = ['press', 'depth', 'sigma', 'ma_sigma']
# A list of the variables on the `Layer` dimension
layer_vars = []
# A list of the variables that don't have the `Vertical` or `Layer` dimensions
pf_vars = ['entry', 'prof_no', 'BL_yn', 'dt_start', 'dt_end', 'lon', 'lat', 'region', 'up_cast', 'R_rho', 'p_theta_max', 's_theta_max', 'theta_max']
# A list of the variables on the `Vertical` dimension
vertical_vars = ['press', 'depth', 'iT', 'CT', 'SP', 'SA', 'sigma', 'alpha', 'beta', 'aiT', 'aCT', 'BSP', 'BSA', 'ss_mask', 'ma_iT', 'ma_CT', 'ma_SP', 'ma_SA', 'ma_sigma', 'la_iT', 'la_CT', 'la_SP', 'la_SA', 'la_sigma']
# Make lists of clustering variables
pca_prefix = 'pca_'
pca_vars   = [ f'{pca_prefix}{var}' for var in vertical_vars]
cmc_prefix = 'cmc_'
cmc_vars   = [ f'{cmc_prefix}{var}' for var in vertical_vars]
ca_prefix  = 'ca_'
ca_vars    = [ f'{ca_prefix}{var}' for var in vertical_vars]
clstr_vars = ['cluster'] + pca_vars + cmc_vars + ca_vars
# mc_prefix = 'mc_'
# mc_vars   = [ f'{mc_prefix}{var}' for var in vertical_vars]

################################################################################
# Declare classes for custom objects
################################################################################

class Data_Set:
    """
    Loads data from netcdfs and returns a list of xarrays with filters applied
    Note: Only filters to a selection of profiles. Does not filter individual
        profiles in any manner

    sources_dict    A dictionary with the following format:
                    {'ITP_1':[13,22,32],'ITP_2':'all'}
                    where the keys are the netcdf filenames without the extension
                    and the values are lists of profiles to include or 'all'
    data_filters    A custom Data_Filters object that contains the filters to apply
    """
    def __init__(self, sources_dict, data_filters):
        # Load just the relevant profiles into the xarrays
        self.sources_dict = sources_dict
        self.data_filters = data_filters
        xarrs, self.var_attr_dicts = list_xarrays(sources_dict)
        self.arr_of_ds = apply_data_filters(xarrs, data_filters)

################################################################################

class Data_Filters:
    """
    A set of filters to select certain profiles
    Note: Only filters to a selection of profiles. Does not filter individual
        profiles in any manner

    keep_black_list     True/False whether to keep profiles marked on black list
    cast_direction      'up','down',or 'all' to keep certain directions of casts
    geo_extent          None to keep all profiles regardless of geographic region
                        or 'CS' for Chukchi Sea, 'SBS' for Southern Beaufort Sea,
                        'CB' for Canada Basin, 'MB' for Makarov Basin, 'EB' for
                        Eurasian Basin, or 'BS' for Barents Sea
    date_range          ['start_date','end_date'] where the dates are strings in
                        the format 'YYYY/MM/DD' or None to keep all profiles
    """
    def __init__(self, keep_black_list=False, cast_direction='up', geo_extent=None, date_range=None):
        self.keep_black_list = keep_black_list
        self.cast_direction = cast_direction
        self.geo_extent = geo_extent
        self.date_range = date_range

################################################################################

class Analysis_Group:
    """
    Takes in a list of xarray datasets and applies filters to individual profiles
    Returns a list of pandas dataframes, one for each source

    data_set            A Data_Set object
    profile_filters     A custom Profile_Filters object with filters to apply to
                        all individual profiles in the xarrays
    plt_params          A custom Plot_Parameters object
    """
    def __init__(self, data_set, profile_filters, plt_params, plot_title=None):
        self.data_set = data_set
        self.vars_available = list(data_set.arr_of_ds[0].keys())
        self.profile_filters = profile_filters
        self.plt_params = get_axis_labels(plt_params, data_set.var_attr_dicts)
        self.plot_title = plot_title
        self.vars_to_keep = find_vars_to_keep(plt_params, profile_filters, self.vars_available)
        # Load just the relevant profiles into the xarrays
        self.data_frames = apply_profile_filters(data_set.arr_of_ds, self.vars_to_keep, profile_filters, plt_params)

################################################################################

class Profile_Filters:
    """
    A set of filters to apply to each profile. If None is passed for any filter,
    that filter will not be applied. All these are ignored when plotting 'by_pf'

    p_range             [p_min, p_max] where the values are floats in dbar
                          or, "Shibley2017" to follow their method of selecting a range
    d_range             [d_min, d_max] where the values are floats in m
    iT_range            [T_min, T_max] where the values are floats in degrees C
    SP_range            [S_min, S_max] where the values are floats in g/kg
    subsample           True/False whether to apply the subsample mask to the profiles
    regrid_TS           [T_var, d_temp, S_var, d_salt] or None if you don't want to re-grid
    detected_layers     'all', 'ml', or 'gl'. If None, this is ignored
    regime              'all', 'dc', or 'sf'. If None, this is ignored
    """
    def __init__(self, p_range=None, d_range=None, iT_range=None, CT_range=None, SP_range=None, SA_range=None, subsample=False, regrid_TS=None, run_SDA=False, detected_layers=None, regime=None):
        self.p_range = p_range
        self.d_range = d_range
        self.iT_range = iT_range
        self.CT_range = CT_range
        self.SP_range = SP_range
        self.SA_range = SA_range
        self.subsample = subsample
        self.regrid_TS = regrid_TS
        self.run_SDA = run_SDA
        self.detected_layers = detected_layers
        self.regime = regime

################################################################################

class Plot_Parameters:
    """
    A set of parameters to determine what kind of plot to make

    plot_type       A string of the kind of plot to make from these options:
                        'xy', 'map', 'profiles'
    plot_scale      A string specifying either 'by_pf', 'by_vert', or 'by_layer'
                    which will determine whether to add one data point per
                    profile, per vertical observation, or per detected layer,
                    respectively
    x_vars          A list of strings of the variables to plot on the x axis
    y_vars          A list of strings of the variables to plot on the y axis
                    Note: 'xy' and 'profiles' expect both x_vars and y_vars and
                      'map' ignores this variable as it always plots lon vs. lat
                    Default plot is 'SP' vs. 'iT'
                    Accepted 'by_pf' vars: 'entry', 'prof_no', 'BL_yn', 'dt_start',
                      'dt_end', 'lon', 'lat', 'region', 'up_cast', 'R_rho'
                    Accepted 'by_vert' vars: all 'by_pf' vars plus 'press',
                      'depth', 'iT', 'CT', 'SP', 'SA', 'sigma', 'alpha', 'beta',
                      'aiT', 'aCT', 'BSP', 'BSA', 'ma_iT', 'ma_CT', 'ma_SP',
                      'ma_SA', 'ma_sigma', 'ss_mask', 'la_iT', 'la_CT', 'la_SA',
                      'la_sigma'
                    Accepted 'by_layer' vars: ???
    ax_lims         An optional dictionary of the limits on the axes for the final plot
                      Ex: {'x_lims':[x_min,x_max], 'y_lims':[y_min,y_max]}
    first_dfs       A list of booleans of whether to take the first differences
                      of the plot_vars before analysis. Defaults to all False
                    'xy' expects a list of 2, ex: [True, False]
                    'map' and 'profiles' ignore this parameter
    clr_map         A string to determine what color map to use in the plot
                    'xy' can use 'clr_all_same', 'clr_by_source',
                      'clr_by_instrmt', 'density_hist', or any regular variable
                    'map' can use 'clr_all_same', 'clr_by_source',
                      'clr_by_instrmt', or any 'by_pf' regular variable
                    'profiles' can use 'clr_all_same' or any regular variable
    extra_args      A general use argument for passing extra info for the plot
                    'map' expects a dictionary following this format:
                        {'map_extent':'Canada_Basin'}
                    'density_hist' expects a dictionary following this format:
                        {'clr_min':0, 'clr_max':20, 'clr_ext':'max', 'xy_bins':250}
                        All 4 of those arguments must be provided for it to work
                        If no extra_args is given, those default values are used
                    'clr_by_clusters' expects a dictionary following this format:
                        {'min_cs':[45,60,75], 'n_pf_step':5} where if 'min_cs' is
                        not a list, it will plot the clusters, but if it is, it
                        will plot number of clusters per number of profiles used, or
                        {'min_cs':120, 'pfs_to_plot':[1257,1259]} where pfs_to_plot
                        is a list of profiles to plot as T and S vs pressure and
                        min_cs must not be a list
                        {'x_param':'attr', 'y_param':'value', 'x_tuple':[],
                        'z_param':'attr', 'z_list':[]}
    """
    def __init__(self, plot_type='xy', plot_scale='by_vert', x_vars=['SP'], y_vars=['iT'], ax_lims=None, first_dfs=[False, False], clr_map='clr_all_same', extra_args=None):
        # Add all the input parameters to the object
        self.plot_type = plot_type
        self.plot_scale = plot_scale
        self.x_vars = x_vars
        self.y_vars = y_vars
        self.xlabels = [None,None]
        self.ylabels = [None,None]
        self.ax_lims = ax_lims
        self.first_dfs = first_dfs
        self.clr_map = clr_map
        self.clabel = None
        # If trying to plot a map, make sure x and y vars are None
        if plot_type == 'map':
            x_vars = None
            y_vars = None
        # If trying to plot a map, make sure `map_extent` exists
        if plot_type == 'map' and isinstance(extra_args, type(None)):
            self.extra_args = {'map_extent':'Canada_Basin'}
        else:
            self.extra_args = extra_args

################################################################################
# Define class functions #######################################################
################################################################################

def list_xarrays(sources_dict):
    """
    Returns a list of xarrays, one for each data source as specified by the
    input dictionary

    sources_dict    A dictionary with the following format:
                    {'ITP_1':[13,22,32],'ITP_2':'all'}
                    where the keys are the netcdf filenames without the extension
                    and the values are lists of profiles to include or 'all'
    """
    # Make an empty list
    xarrays = []
    var_attr_dicts = []
    for source in sources_dict.keys():
        ds = xr.load_dataset('netcdfs/'+source+'.nc')
        # Build the dictionary of netcdf attributes, variables, units, etc.
        var_attrs = {}
        for this_var in list(ds.keys()):
            var_attrs[ds[this_var].name] = ds[this_var].attrs
        var_attr_dicts.append(var_attrs)
        # Convert the datetime variables from dtype `object` to `datetime64`
        ds['Time'] = pd.DatetimeIndex(ds['Time'].values)
        # Check whether to only take certain profiles
        pf_list = sources_dict[source]
        if isinstance(pf_list, list):
            # Start a blank list for all the profile-specific xarrays
            temp_list = []
            for pf in pf_list:
                temp_list.append(ds.where(ds.prof_no==pf, drop=True).squeeze())
            # Concatonate all those xarrays together
            ds1 = xr.concat(temp_list, 'Time')
            xarrays.append(ds1)
        # Take all profiles
        elif pf_list=='all':
            xarrays.append(ds)
        else:
            print(pf_list,'is not a valid list of profiles')
            exit(0)
        #
    # print(var_attr_dicts)
    return xarrays, var_attr_dicts

################################################################################

def apply_data_filters(xarrays, data_filters):
    """
    Returns a list of the same xarrays as provided, but with the filters applied

    xarrays         A list of xarray dataset objects
    data_filters    A custom Data_Filters object that contains the filters to apply
    """
    # Make an empty list
    output_arrs = []
    for ds in xarrays:
        ## Filters on a per-profile basis
        ##      I turned off squeezing because it drops the `Time` dimension if
        ##      you only pass in one profile per dataset
        #   Filter based on the black list
        if data_filters.keep_black_list == False:
            ds = ds.where(ds.BL_yn==False, drop=True)#.squeeze()
        #   Filter based on the cast direction
        if data_filters.cast_direction == 'up':
            ds = ds.where(ds.up_cast==True, drop=True)#.squeeze()
        elif data_filters.cast_direction == 'down':
            ds = ds.where(ds.up_cast==False, drop=True)#.squeeze()
        #   Filter based on the geographical region
        if data_filters.geo_extent == 'CB':
            ds = ds.where(ds.region=='CB', drop=True)#.squeeze()
        #   Filter based on the date range
        if not isinstance(data_filters.date_range, type(None)):
            # Allow for date ranges that do or don't specify the time
            try:
                start_date_range = datetime.strptime(data_filters.date_range[0], r'%Y/%m/%d %H:%M:%S')
            except:
                start_date_range = datetime.strptime(data_filters.date_range[0], r'%Y/%m/%d')
            try:
                end_date_range   = datetime.strptime(data_filters.date_range[1], r'%Y/%m/%d %H:%M:%S')
            except:
                end_date_range   = datetime.strptime(data_filters.date_range[1], r'%Y/%m/%d')
            ds = ds.sel(Time=slice(start_date_range, end_date_range))
        #
        output_arrs.append(ds)
    return output_arrs

################################################################################

def find_vars_to_keep(pp, profile_filters, vars_available):
    """
    Returns a list the variables to keep for an analysis group based on the plot
    parameters and profile filters given

    pp                  A custom Plot_Parameters object
    profile_filters     A custom Profile_Filters object with filters to apply to
                        all individual profiles in the xarrays
    vars_available      A list of variables available for this data
    """
    # If plot type is 'summary', then keep all the variables
    if pp.plot_type == 'summary':
        # Check the plot scale
        #   This will include all the measurements within each profile
        if plt_params.plot_scale == 'by_vert':
            vars_to_keep = ['entry', 'prof_no', 'dt_start', 'dt_end', 'lon', 'lat', 'R_rho', 'press', 'depth', 'iT', 'CT', 'SP', 'SA', 'sigma', 'alpha', 'beta', 'ss_mask', 'ma_iT', 'ma_CT', 'ma_SP', 'ma_SA', 'ma_sigma']
        #   This will only include variables with 1 value per profile
        elif plt_params.plot_scale == 'by_pf':
            vars_to_keep = ['entry', 'prof_no', 'dt_start', 'dt_end', 'lon', 'lat', 'R_rho']
        # print('vars_to_keep:')
        # print(vars_to_keep)
        return vars_to_keep
    else:
        # Always include the entry and profile numbers
        vars_to_keep = ['entry', 'prof_no']
        # Add vars based on plot type
        if pp.plot_type == 'map':
            vars_to_keep.append('lon')
            vars_to_keep.append('lat')
        # Add all the plotting variables
        plot_vars = pp.x_vars+pp.y_vars+[pp.clr_map]
        if not isinstance(pp.extra_args, type(None)):
            for key in pp.extra_args.keys():
                if key in ['cl_x_var', 'cl_y_var']:
                    plot_vars.append(pp.extra_args[key])
        # print('plot_vars:',plot_vars)
        for var in plot_vars:
            if var not in vars_to_keep and var in vars_available:
                vars_to_keep.append(var)
            if var == 'aiT':
                vars_to_keep.append(var)
                if 'alpha' not in vars_to_keep:
                    vars_to_keep.append('alpha')
                if 'iT' not in vars_to_keep:
                    vars_to_keep.append('iT')
            elif var == 'aCT':
                vars_to_keep.append(var)
                if 'alpha' not in vars_to_keep:
                    vars_to_keep.append('alpha')
                if 'CT' not in vars_to_keep:
                    vars_to_keep.append('CT')
            elif var == 'BSP':
                vars_to_keep.append(var)
                if 'beta' not in vars_to_keep:
                    vars_to_keep.append('beta')
                if 'SP' not in vars_to_keep:
                    vars_to_keep.append('SP')
            elif var == 'BSA':
                vars_to_keep.append(var)
                if 'beta' not in vars_to_keep:
                    vars_to_keep.append('beta')
                if 'SA' not in vars_to_keep:
                    vars_to_keep.append('SA')
            # Check for profile cluster average variables
            if 'pca_' in var:
                # Take out the first 4 characters of the string to leave the original variable name
                var_str = var[4:]
                vars_to_keep.append(var_str)
                # Don't add cluster variables to vars_to_keep
            # Check for cluster mean-centered variables
            elif 'cmc_' in var:
                # Take out the first 4 characters of the string to leave the original variable name
                var_str = var[4:]
                vars_to_keep.append(var_str)
                # Don't add cluster variables to vars_to_keep
            # Check for local anomaly variables
            elif 'la_' in var:
                # Take out the first 3 characters of the string to leave the original variable name
                var_str = var[3:]
                vars_to_keep.append(var_str)
                # Calculate it later in calc_extra_vars
                vars_to_keep.append(var)
            # Check for cluster average variables
            elif 'ca_' in var:
                # Take out the first 3 characters of the string to leave the original variable name
                var_str = var[3:]
                vars_to_keep.append(var_str)
                # Don't add cluster variables to vars_to_keep
            # Check for mean-centered variables
            elif 'mc_' in var:
                # Take out the first 3 characters of the string to leave the original variable name
                var_str = var[3:]
                vars_to_keep.append(var_str)
                # Calculate it later in calc_extra_vars
                vars_to_keep.append(var)
            #
        # Add vars for the colormap, if applicable
        if pp.clr_map in vars_available and pp.clr_map not in vars_to_keep:
            vars_to_keep.append(pp.clr_map)
        # Add vars for the profile filters, if applicable
        scale = pp.plot_scale
        if scale == 'by_vert' or scale == 'by_layer':
            if not isinstance(profile_filters.p_range, type(None)) and 'press' not in vars_to_keep:
                vars_to_keep.append('press')
            if not isinstance(profile_filters.d_range, type(None)) and 'depth' not in vars_to_keep:
                vars_to_keep.append('depth')
            if not isinstance(profile_filters.iT_range, type(None)) and 'iT' not in vars_to_keep:
                vars_to_keep.append('iT')
            if not isinstance(profile_filters.CT_range, type(None)) and 'CT' not in vars_to_keep:
                vars_to_keep.append('CT')
            if not isinstance(profile_filters.SP_range, type(None)) and 'SP' not in vars_to_keep:
                vars_to_keep.append('SP')
            if not isinstance(profile_filters.SA_range, type(None)) and 'SA' not in vars_to_keep:
                vars_to_keep.append('SA')
            if profile_filters.subsample and 'ss_mask' not in vars_to_keep:
                vars_to_keep.append('ss_mask')
            #
        #
        # print('vars_to_keep:')
        # print(vars_to_keep)
        # exit(0)
        return vars_to_keep

################################################################################

def apply_profile_filters(arr_of_ds, vars_to_keep, profile_filters, pp):
    """
    Returns a list of pandas dataframes, one for each array in arr_of_ds with
    the filters applied to all individual profiles

    arr_of_ds           An array of datasets from a custom Data_Set object
    vars_to_keep        A list of variables to keep for the analysis
    profile_filters     A custom Profile_Filters object that contains the filters to apply
    pp                  A custom Plot_Parameters object that contains at least:
    plot_scale      A string specifying either 'by_pf', 'by_vert', or 'by_layer'
                    which will determine whether to add one data point per
                    profile, per vertical observation, or per detected layer,
                    respectively
    """
    print('- Applying profile filters')
    plot_scale = pp.plot_scale
    # Make an empty list
    output_dfs = []
    # What's the plot scale?
    if plot_scale == 'by_vert':
        for ds in arr_of_ds:
            ds = calc_extra_vars(ds, vars_to_keep)
            # Convert to a pandas data frame
            df = ds[vars_to_keep].to_dataframe()
            # Add a notes column
            df['notes'] = ''
            #   True/False, apply the subsample mask to the profiles
            if profile_filters.subsample:
                # `ss_mask` is null for the points that should be masked out
                # so apply mask to all the variables that were kept
                df.loc[df['ss_mask'].isnull(), vars_to_keep] = None
                # Set a new column so the ss_scheme can be found later for the title
                df['ss_scheme'] = ds.attrs['Sub-sample scheme']
            # Remove rows where the plot variables are null
            for var in pp.x_vars+pp.y_vars:
                if var in vars_to_keep:
                    df = df[df[var].notnull()]
            # Add expedition and instrument columns
            df['source'] = ds.Expedition
            df['instrmt'] = ds.Instrument
            ## Filters on each profile separately
            df = filter_profile_ranges(df, profile_filters, 'press', 'depth', iT_key='iT', CT_key='CT', SP_key='SP', SA_key='SA')
            ## Re-grid temperature and salinity data
            if not isinstance(profile_filters.regrid_TS, type(None)):
                # Figure out which salinity and temperature variable to re-grid
                T_var = profile_filters.regrid_TS[0]
                S_var = profile_filters.regrid_TS[2]
                # Make coarse grids for temp and salt based on given arguments
                d_temp = profile_filters.regrid_TS[1]
                d_salt = profile_filters.regrid_TS[3]
                t_arr  = np.array(df[T_var])
                s_arr  = np.array(df[S_var])
                t_min, t_max = min(t_arr), max(t_arr)
                s_min, s_max = min(s_arr), max(s_arr)
                t_grid = np.arange(t_min-d_temp, t_max+d_temp, d_temp)
                s_grid = np.arange(s_min-d_salt, s_max+d_salt, d_salt)
                # Make re-gridded arrays of temp and salt
                temp_rg = t_grid[abs(t_arr[None, :] - t_grid[:, None]).argmin(axis=0)]
                salt_rg = s_grid[abs(s_arr[None, :] - s_grid[:, None]).argmin(axis=0)]
                # Overwrite original temp and salt values with those regridded arrays
                df[T_var] = temp_rg
                df[S_var] = salt_rg
                # Note the regridding in the notes column
                df['notes'] = df['notes'] + r'$\Delta t_{rg}=$'+str(d_temp)+r', $\Delta s_{rg}=$'+str(d_salt)
            #
            # Check whether or not to take first differences
            first_dfs = pp.first_dfs
            # Take first differences in both variables
            if len(first_dfs)==2 and all(first_dfs):
                print('Have not completed the code to do first differences yet')
                exit(0)
                # Find the vars to take the first difference of
                var0 = plt_params.plot_vars[0]
                var1 = plt_params.plot_vars[1]
                # Make new names for the columns of first differences
                dvar0 = 'd_'+var0
                dvar1 = 'd_'+var1
                plt_params.plot_vars[0] = dvar0
                plt_params.plot_vars[1] = dvar1
                # Loop across each profile
                pfs = np.unique(np.array(df['prof_no']))
                new_dfs = []
                for pf in pfs:
                    # Find the data for just that profile
                    data_pf = df[df['prof_no'] == pf]
                    # Make the given variables into first differences
                    data_pf[dvar0] = data_pf[var0].diff()
                    data_pf[dvar1] = data_pf[var1].diff()
                    # Remove rows with null values (one per profile because of diff())
                    data_pf = data_pf[data_pf[dvar0].notnull()]
                    data_pf = data_pf[data_pf[dvar1].notnull()]
                    new_dfs.append(data_pf)
                df = pd.concat(new_dfs)
            # If just taking first differences of one variable
            elif any(first_dfs):
                print('Have not completed the code to do first differences yet')
                exit(0)
                # Is the var in position 0 or 1?
                var_idx = first_dfs.index(True)
                # Find the var to take the first difference of
                var = plt_params.plot_vars[var_idx]
                # Make new names for the columns of first differences
                dvar = 'd_'+var
                plt_params.plot_vars[var_idx] = dvar
                # Loop across each profile
                pfs = np.unique(np.array(df['prof_no']))
                new_dfs = []
                for pf in pfs:
                    # Find the data for just that profile
                    data_pf = df[df['prof_no'] == pf]
                    # Make the given variable into first differences
                    data_pf[dvar] = data_pf[var].diff()
                    # Remove rows with null values (one per profile because of diff())
                    data_pf = data_pf[data_pf[dvar].notnull()]
                    new_dfs.append(data_pf)
                df = pd.concat(new_dfs)
            #
            # Append the filtered dataframe to the list
            output_dfs.append(df)
        #
    elif plot_scale == 'by_layer':
        for ds in arr_of_ds:
            ds = calc_extra_vars(ds, vars_to_keep)
            # Convert to a pandas data frame
            df = ds[vars_to_keep].to_dataframe()
            # Add a notes column
            df['notes'] = ''
            # Remove rows where the plot variables are null
            for var in pp.x_vars+pp.y_vars:
                if var in vars_to_keep:
                    df = df[df[var].notnull()]
            # Add expedition and instrument columns
            df['source'] = ds.Expedition
            df['instrmt'] = ds.Instrument
            ## Filters on each profile separately
            df = filter_profile_ranges(df, profile_filters, 'press', 'depth', iT_key='iT', CT_key='CT', SP_key='SP', SA_key='SA')
            # Find a value of the Vertical dimension that is included in all profiles
            try:
                df.reset_index(inplace=True, level=['Vertical'])
                v_vals = df['Vertical'].values
                print('\t- Dropping Vertical dimension')
                for pf_no in df['prof_no'].values:
                    v_vals = list(set(v_vals) & set(df[df['prof_no']==pf_no]['Vertical'].values))
                # Avoid the nan's on the edges, find a value in the middle of the array
                v_med = v_vals[len(v_vals)//2]
                # Drop dimension by just taking the rows where Vertical = v_med
                df = df[df['Vertical']==v_med]
            except:
                foo = 2
            #
            # Append the filtered dataframe to the list
            output_dfs.append(df)
        #
    elif plot_scale == 'by_pf':
        for ds in arr_of_ds:
            # Convert to a pandas data frame
            df = ds[vars_to_keep].to_dataframe()
            # Add expedition and instrument columns
            df['source'] = ds.Expedition
            df['instrmt'] = ds.Instrument
            ## Filters on each profile separately
            df = filter_profile_ranges(df, profile_filters, 'press', 'depth', iT_key='iT', CT_key='CT', SP_key='SP', SA_key='SA')
            # Drop dimensions, if needed
            if 'Vertical' in df.index.names or 'Layer' in df.index.names:
                # Drop duplicates along the `Time` dimension
                #   (need to make the index `Time` a column first)
                df.reset_index(level=['Time'], inplace=True)
                df.drop_duplicates(inplace=True, subset=['Time'])
            # Add a notes column
            df['notes'] = ''
            # Filter to just one entry per profile
            #   Turns out, if `vars_to_keep` doesn't have any multi-dimensional
            #       vars like 'temp' or 'salt', the resulting dataframe only has
            #       one row per profile automatically. Neat
            # Remove missing data (actually, don't because it will get rid of all
            #   data if one var isn't filled, like dt_end often isn't)
            # for var in vars_to_keep:
            #     df = df[df[var].notnull()]
            # print(df)
            output_dfs.append(df)
        #
    #
    return output_dfs

################################################################################

def filter_profile_ranges(df, profile_filters, p_key, d_key, iT_key=None, CT_key=None, SP_key=None, SA_key=None):
    """
    Returns the same pandas dataframe, but with the filters provided applied to
    the data within

    df                  A pandas dataframe
    profile_filters     A custom Profile_Filters object that contains the filters to apply
    p_key               A string of the pressure variable to filter
    d_key               A string of the depth variable to filter
    iT_key              A string of the in-situ temperature variable to filter
    CT_key              A string of the conservative temperature variable to filter
    SP_key              A string of the practical salinity variable to filter
    SA_key              A string of the absolute salinity variable to filter
    """
    #   Filter to a certain pressure range
    if not isinstance(profile_filters.p_range, type(None)):
        if profile_filters.p_range == "Shibley2017":
            df = filter_p_range_Shibley2017(df)
        else:
            # Get endpoints of pressure range
            p_max = max(profile_filters.p_range)
            p_min = min(profile_filters.p_range)
            # Filter the data frame to the specified pressure range
            df = df[(df[p_key] < p_max) & (df[p_key] > p_min)]
    #   Filter to a certain depth range
    if not isinstance(profile_filters.d_range, type(None)):
        # Get endpoints of depth range
        d_max = max(profile_filters.d_range)
        d_min = min(profile_filters.d_range)
        # Filter the data frame to the specified depth range
        df = df[(df[d_key] < d_max) & (df[d_key] > d_min)]
    #   Filter to a certain in-situ temperature range
    if not isinstance(profile_filters.iT_range, type(None)):
        # Get endpoints of in-situ temperature range
        t_max = max(profile_filters.iT_range)
        t_min = min(profile_filters.iT_range)
        # Filter the data frame to the specified in-situ temperature range
        df = df[(df[iT_key] < t_max) & (df[iT_key] > t_min)]
    #   Filter to a certain conservative temperature range
    if not isinstance(profile_filters.CT_range, type(None)):
        # Get endpoints of conservative temperature range
        t_max = max(profile_filters.CT_range)
        t_min = min(profile_filters.CT_range)
        # Filter the data frame to the specified conservative temperature range
        df = df[(df[CT_key] < t_max) & (df[CT_key] > t_min)]
    #   Filter to a certain practical salinity range
    if not isinstance(profile_filters.SP_range, type(None)):
        # Get endpoints of practical salinity range
        s_max = max(profile_filters.SP_range)
        s_min = min(profile_filters.SP_range)
        # Filter the data frame to the specified practical salinity range
        df = df[(df[SP_key] < s_max) & (df[SP_key] > s_min)]
    #   Filter to a certain absolute salinity range
    if not isinstance(profile_filters.SA_range, type(None)):
        # Get endpoints of absolute salinity range
        s_max = max(profile_filters.SA_range)
        s_min = min(profile_filters.SA_range)
        # Filter the data frame to the specified absolute salinity range
        df = df[(df[SA_key] < s_max) & (df[SA_key] > s_min)]
    return df

################################################################################

def calc_extra_vars(ds, vars_to_keep):
    """
    Takes in an xarray object and a list of variables and, if there are extra
    variables to calculate, it will add those to the xarray

    ds                  An xarray from the arr_of_ds of a custom Data_Set object
    vars_to_keep        A list of variables to keep for the analysis
    """
    # Check for variables to calculate
    if 'aiT' in vars_to_keep:
        ds['aiT'] = ds['alpha'] * ds['iT']
    if 'aCT' in vars_to_keep:
        ds['aCT'] = ds['alpha'] * ds['CT']
    if 'BSP' in vars_to_keep:
        ds['BSP'] = ds['beta'] * ds['SP']
    if 'BSA' in vars_to_keep:
        ds['BSA'] = ds['beta'] * ds['SA']
    # Check for variables with an underscore
    for this_var in vars_to_keep:
        if '_' in this_var and this_var != 'prof_no':
            # Split the prefix from the original variable (assumes an underscore split)
            split_var = this_var.split('_', 1)
            prefix = split_var[0]
            var = split_var[1]
            print('prefix:',prefix,'- var:',var)
            if prefix == 'la':
                # Calculate the local anomaly of this variable
                ds[this_var] = ds[var] - ds['ma_'+var]
            #
        #
    return ds

################################################################################

def get_axis_labels(pp, var_attr_dicts):
    """
    Using the dictionaries of variable attributes, this adds the xlabel and ylabel
    attributes to the plot parameters object passed in (this replaced the
    `get_axis_label` function)

    pp                  A custom Plot_Parameters object
    var_attr_dicts      A list of dictionaries containing the attribute info
                            about all the variables in the netcdf file
    """
    # Get x axis labels
    if not isinstance(pp.x_vars, type(None)):
        if len(pp.x_vars) > 0:
            try:
                pp.xlabels[0] = var_attr_dicts[0][pp.x_vars[0]]['label']
            except:
                pp.xlabels[0] = get_axis_label(pp.x_vars[0], var_attr_dicts)
        else:
            pp.xlabels[0] = None
        if len(pp.x_vars) == 2:
            try:
                pp.xlabels[1] = var_attr_dicts[0][pp.x_vars[1]]['label']
            except:
                pp.xlabels[1] = get_axis_label(pp.x_vars[1], var_attr_dicts)
        else:
            pp.xlabels[1] = None
    else:
        pp.xlabels[0] = None
        pp.xlabels[1] = None
    # Get y axis labels
    if not isinstance(pp.y_vars, type(None)):
        if len(pp.y_vars) > 0:
            try:
                pp.ylabels[0] = var_attr_dicts[0][pp.y_vars[0]]['label']
            except:
                pp.ylabels[0] = get_axis_label(pp.y_vars[0], var_attr_dicts)
        else:
            pp.ylabels[0] = None
        if len(pp.y_vars) == 2:
            try:
                pp.ylabels[1] = var_attr_dicts[0][pp.y_vars[1]]['label']
            except:
                pp.ylabels[1] = get_axis_label(pp.y_vars[1], var_attr_dicts)
        else:
            pp.ylabels[1] = None
    else:
        pp.ylabels[0] = None
        pp.ylabels[1] = None
    # Get colormap label
    if not isinstance(pp.clr_map, type(None)):
        try:
            pp.clabel = var_attr_dicts[0][pp.clr_map]['label']
        except:
            pp.clabel = get_axis_label(pp.clr_map, var_attr_dicts)

    # Check for first differences of variables
    if any(pp.first_dfs):
        if pp.first_dfs[0]:
            if not isinstance(pp.xlabels[0], type(None)):
                pp.xlabels[0] = 'First difference in '+pp.xlabels[0]
            if not isinstance(pp.xlabels[1], type(None)):
                pp.xlabels[1] = 'First difference in '+pp.xlabels[1]
        if len(pp.first_dfs)==2 and pp.first_dfs[1]:
            if not isinstance(pp.ylabels[0], type(None)):
                pp.ylabels[0] = 'First difference in '+pp.ylabels[0]
            if not isinstance(pp.ylabels[1], type(None)):
                pp.ylabels[1] = 'First difference in '+pp.ylabels[1]
    if pp.plot_type == 'map':
        pp.plot_scale = 'by_pf'
        pp.x_vars  = ['lon']
        pp.y_vars  = ['lat']
        pp.xlabels = [None, None]
        pp.ylabels = [None, None]
    #
    return pp

################################################################################

def get_axis_label(var_key, var_attr_dicts):
    """
    Takes in a variable name and returns a nicely formatted string for an axis label

    var_key             A string of the variable name
    var_attr_dicts      A list of dictionaries of variable attributes
    """
    # Check for certain modifications to variables,
    #   check longer strings first to avoid mismatching
    # Check for profile cluster average variables
    if 'pca_' in var_key:
        # Take out the first 4 characters of the string to leave the original variable name
        var_str = var_key[4:]
        return 'Profile cluster average of '+ var_attr_dicts[0][var_str]['label']
    # Check for cluster mean-centered variables
    elif 'cmc_' in var_key:
        # Take out the first 4 characters of the string to leave the original variable name
        var_str = var_key[4:]
        return 'Cluster mean-centered '+ var_attr_dicts[0][var_str]['label']
    # Check for local anomaly variables
    elif 'la_' in var_key:
        # Take out the first 3 characters of the string to leave the original variable name
        var_str = var_key[3:]
        return 'Local anomaly of '+ var_attr_dicts[0][var_str]['label']
    # Check for cluster average variables
    elif 'ca_' in var_key:
        # Take out the first 3 characters of the string to leave the original variable name
        var_str = var_key[3:]
        return 'Cluster average of '+ var_attr_dicts[0][var_str]['label']
    # Check for mean-centered variables
    # elif 'mc_' in var_key:
    #     # Take out the first 3 characters of the string to leave the original variable name
    #     var_str = var_key[3:]
    #     return 'Mean-centered '+ var_attr_dicts[0][var_str]['label']
    # Build dictionary of axis labels
    ax_labels = {
                 'hist':r'Occurrences',
                 'aiT':r'$\alpha T$',
                 'aCT':r'$\alpha \theta$',
                 'BSP':r'$\beta S_P$',
                 'BSA':r'$\beta S_A$',
                 'p_theta_max':r'$p(\theta_{max})$ (dbar)',
                 's_theta_max':r'$S(\theta_{max})$ (g/kg)',
                 'theta_max':r'$\theta_{max}$ ($^\circ$C)',
                 'distance':r'Along-path distance (km)',
                 'min_cs':r'Minimum cluster size',
                 'DBCV':'Relative validity measure',
                 'n_clusters':'Number of clusters'
                }
    if var_key in ax_labels.keys():
        return ax_labels[var_key]
    else:
        return 'None'

################################################################################
# Admin summary functions ######################################################
################################################################################

def txt_summary(groups_to_summarize, filename=None):
    """
    Takes in a list of Analysis_Group objects. Analyzes and outputs summary info
    for each one.

    groups_to_plot  A list of Analysis_Group objects
    """
    # Loop over all Analysis_Group objects
    i = 0
    for a_group in groups_to_summarize:
        i += 1
        # Concatonate all the pandas data frames together
        df = pd.concat(a_group.data_frames)
        # Find the total number of profiles
        n_profs = len(np.unique(np.array(df['prof_no'], dtype=type(''))))
        # Put all of the lines together
        lines = ["Group "+str(i)+":",
                 # "\t"+add_std_title(a_group),
                 print_global_variables(a_group.data_set),
                 "\t\tVariables to keep:",
                 "\t\t"+str(a_group.vars_to_keep),
                 "\t\tNumber of profiles: ",
                 "\t\t\t"+str(n_profs),
                 "\t\tNumber of data points: ",
                 "\t\t\t"+str(len(df))
                 ]
        # Find the ranges of the variables available
        print('working on ranges')
        var_attr_dict = a_group.data_set.var_attr_dicts[0]
        for var in a_group.vars_to_keep:
            if var in var_attr_dict.keys():
                lines.append(report_range(df, var, var_attr_dict[var]))
            #
        #
        # Check for SDA variables
        if 'SDA_n_ml_dc' in a_group.vars_to_keep and 'SDA_n_ml_sf' in a_group.vars_to_keep and 'SDA_n_gl_dc' in a_group.vars_to_keep and 'SDA_n_gl_sf' in a_group.vars_to_keep:# and 'SDA_ml_press' in a_group.vars_to_keep and 'SDA_gl_h' in a_group.vars_to_keep:
            print('working on SDA part')
            lines.append("\n\t\t-- SDA output summary --")
            lines.append(summarize_SDA_output(df, n_profs))
        lines.append("\n")
    #
    if filename != None:
        print('Writing summary file to',filename)
        with open(filename, 'w') as f:
            f.write('\n'.join(lines))
    else:
        for line in lines:
            print(line)

################################################################################

def report_range(df, key, name_and_units):
    """
    Reports the range of the key value given for the given dataframe

    df          A pandas data frame
    key         A string of the column to search in the data frame
    name_and_units      A dictionary containing:
        name_str    A string of the long version of the column data type
        units       A string of the units of the data type
    """
    name_str  = name_and_units['long_name']
    try:
        units = name_and_units['units']
    except:
        # The above will fail if no units are given, which currently happens for
        #   the time variables in the GDS netcdfs because I needed to sort them
        print('Missing units for:',key)
        units = 'YYYY-MM-DD HH:MM:SS'
    # Find this range, making sure to skip null (nan) values
    this_arr = df[df[key].notnull()][key]
    if len(this_arr) > 1:
        this_min = min(this_arr)
        this_max = max(this_arr)
        if key != 'dt_start' and key != 'dt_end':
            # This line formats all the numbers to have just 2 digits after the decimal point
            return "\t\t"+key+': '+name_str+" \n\t\t\trange: %.2f"%(this_max-this_min)+" "+units+"\n\t\t\t%.2f"%this_min+" to %.2f"%this_max+" "+units
            # This line outputs the numbers with all available digits after the decimal point
            # return "\t\t"+name_str+" range: "+str(this_max-this_min)+" "+units+"\n\t\t\t"+str(this_min)+" to "+str(this_max)+" "+units
        else:
            return "\t\t"+key+': '+name_str+" \n\t\t\trange: \n\t\t\t"+str(this_min)+" to "+str(this_max)+" "+units
    else:
        return "\t\t"+key+': '+name_str+" \n\t\t\trange: N/A \n\t\t\tN/A"

################################################################################

def print_global_variables(Dataset):
    """
    Prints out the global variables of the data sources in a Data_Set object

    Dataset         A custom Data_Set object
    """
    lines = ''
    for ds in Dataset.arr_of_ds:
        for attr in ds.attrs:
            if attr in ['Creation date', 'Last modified', 'Last modification', 'Sub-sample scheme']:
                print('\t'+attr+': '+ds.attrs[attr])
            else:
                lines = lines+'\t'+attr+': '+ds.attrs[attr]+'\n'
    return lines

################################################################################
# Admin plotting functions #####################################################
################################################################################

def make_figure(groups_to_plot, filename=None, use_same_y_axis=None):
    """
    Takes in a list of Analysis_Group objects, one for each subplot. Determines
    the needed arrangement of subplots, then passes one Analysis_Group object to
    each axis for plotting

    groups_to_plot  A list of Analysis_Group objects, one for each subplot
                    Each Analysis_Group contains the info to create each subplot
    """
    # Define number of rows and columns based on number of subplots
    #   key: number of subplots, value: (rows, cols, f_ratio, f_size)
    n_row_col_dict = {'1':[1,1, 0.8, 1.25], '2':[1,2, 0.5, 1.25], '2.5':[2,1, 0.8, 1.25],
                      '3':[1,3, 0.3, 1.40], '4':[2,2, 0.8, 2.00],#1.50],
                      '5':[2,3, 0.5, 2.00], '6':[2,3, 0.5, 2.00]}
    # Figure out what layout of subplots to make
    n_subplots = len(groups_to_plot)
    y_keys = []
    for group in groups_to_plot:
        pp = group.plt_params
        u_y_vars = np.unique(pp.y_vars)
        u_y_vars = np.delete(u_y_vars, np.where(u_y_vars == None))
        if len(u_y_vars) > 1:
            for var in u_y_vars:
                y_keys.append(var)
            #
        #
    #
    if len(y_keys) > 1 and isinstance(use_same_y_axis, type(None)):
        # If all the y_vars are the same, share the y axis between subplots
        if all(x == y_keys[0] for x in y_keys):
            use_same_y_axis = True
        else:
            use_same_y_axis = False
        #
    else:
        use_same_y_axis = False
    if n_subplots == 1:
        fig, ax = set_fig_axes([1], [1], fig_ratio=0.8, fig_size=1.25)
        xlabel, ylabel, plt_title, ax = make_subplot(ax, groups_to_plot[0], fig, 111)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        # If axes limits given, limit axes
        if not isinstance(pp.ax_lims, type(None)):
            try:
                ax.set_xlim(pp.ax_lims['x_lims'])
            except:
                foo = 2
            try:
                ax.set_ylim(pp.ax_lims['y_lims'])
            except:
                foo = 2
        ax.set_title(plt_title)
    elif n_subplots > 1 and n_subplots < 7:
        rows, cols, f_ratio, f_size = n_row_col_dict[str(n_subplots)]
        n_subplots = int(np.floor(n_subplots))
        fig, axes = set_fig_axes([1]*rows, [1]*cols, fig_ratio=f_ratio, fig_size=f_size, share_y_axis=use_same_y_axis)
        for i in range(n_subplots):
            if rows > 1 and cols > 1:
                i_ax = (i//cols,i%cols)
            else:
                i_ax = i
            ax_pos = int(str(rows)+str(cols)+str(i+1))
            xlabel, ylabel, plt_title, ax = make_subplot(axes[i_ax], groups_to_plot[i], fig, ax_pos)
            ax.set_xlabel(xlabel)
            ax.set_ylabel(ylabel)
            # If axes limits given, limit axes
            this_ax_pp = groups_to_plot[i].plt_params
            if not isinstance(this_ax_pp.ax_lims, type(None)):
                try:
                    ax.set_xlim(this_ax_pp.ax_lims['x_lims'])
                except:
                    foo = 2
                try:
                    ax.set_ylim(this_ax_pp.ax_lims['y_lims'])
                except:
                    foo = 2
            ax.set_title(plt_title)
            # Label subplots a, b, c, ...
            ax.text(-0.1, 1.1, '('+string.ascii_lowercase[i]+')', transform=ax.transAxes, size=20)
        # Turn off unused axes
        if n_subplots < (rows*cols):
            for i in range(rows*cols-1, n_subplots-1, -1):
                axes[i//cols,i%cols].set_axis_off()
    else:
        print('Too many subplots')
        exit(0)
    #
    plt.tight_layout()
    #
    if filename != None:
        print('Saving figure to',filename)
        plt.savefig(filename, dpi=400)
    else:
        plt.show()

################################################################################
# Formatting plotting functions ################################################
################################################################################

def set_fig_axes(heights, widths, fig_ratio=0.5, fig_size=1, share_x_axis=None, share_y_axis=None, prjctn=None):
    """
    Creates fig and axes objects based on desired heights and widths of subplots
    Ex: if widths=[1,5], there will be 2 columns, the 1st 1/5 the width of the 2nd

    heights      array of integers for subplot height ratios, len=rows
    widths       array of integers for subplot width  ratios, len=cols
    fig_ratio    ratio of height to width of overall figure
    fig_size     size scale factor, 1 changes nothing, 2 makes it very big
    share_x_axis bool whether the subplots should share their x axes
    share_y_axis bool whether the subplots should share their y axes
    projection   projection type for the subplots
    """
    # Set aspect ratio of overall figure
    w, h = mpl.figure.figaspect(fig_ratio)
    # Find rows and columns of subplots
    rows = len(heights)
    cols = len(widths)
    # This dictionary makes each subplot have the desired ratios
    # The length of heights will be nrows and likewise len(widths)=ncols
    plot_ratios = {'height_ratios': heights,
                   'width_ratios': widths}
    # Determine whether to share x or y axes
    if share_x_axis == None and share_y_axis == None:
        if rows == 1 and cols != 1: # if only one row, share y axis
            share_x_axis = False
            share_y_axis = True
        elif rows != 1 and cols == 1: # if only one column, share x axis
            share_x_axis = True
            share_y_axis = False
        else:                       # otherwise, forget about it
            share_x_axis = False
            share_y_axis = False
    elif share_y_axis == None:
        share_y_axis = False
        print('Set share_y_axis to', share_y_axis)
    elif share_x_axis == None:
        share_x_axis = False
        print('Set share_x_axis to', share_x_axis)
    # Set ratios by passing dictionary as 'gridspec_kw', and share y axis
    fig, axes = plt.subplots(figsize=(w*fig_size,h*fig_size), nrows=rows, ncols=cols, gridspec_kw=plot_ratios, sharex=share_x_axis, sharey=share_y_axis, subplot_kw=dict(projection=prjctn))
    # Set ticklabel format for all axes
    if (rows+cols)>2:
        for ax in axes.flatten():
            ax.ticklabel_format(style='sci', scilimits=sci_lims, useMathText=True)
    else:
        axes.ticklabel_format(style='sci', scilimits=sci_lims, useMathText=True)
    return fig, axes

################################################################################

def add_std_title(a_group):
    """
    Adds in standard information to this subplot's title, as appropriate

    a_group         A Analysis_Group object containing the info to create a subplot
    """
    # Check for an override title
    if not isinstance(a_group.plot_title, type(None)):
        return a_group.plot_title
    else:
        plt_title = ''
    # Determine a prefix, if any, for the plot title
    pfs = a_group.profile_filters
    if pfs.subsample:
        # Get a string of the subsampling scheme
        ss_scheme = np.unique(np.array(a_group.data_frames[0]['ss_scheme']))[0]
        plt_title = 'Subsampled w/ ' + ss_scheme + ':'
    sources_dict = a_group.data_set.sources_dict
    # Get a list of the sources in the plot
    sources = list(sources_dict.keys())
    # Get just the unique sources
    sources = np.unique(sources)
    if len(sources) > 3:
        plt_title += 'Many sources'
    else:
        # Note all the data sources in the title
        plt_title += sources[0].replace('_',' ')
        for i in range(1,len(sources)):
            plt_title += ', '
            plt_title += sources[i].replace('_',' ')
    #
    return plt_title

################################################################################

def add_std_legend(ax, data, x_key):
    """
    Adds in standard information to this subplot's legend, as appropriate

    ax          The axis on which to add the legend
    data        A pandas data frame which is plotted on this axis
    x_key       The string of the column name for the x data from the dataframe
    """
    # Add legend to report the total number of points and notes on the data
    n_pts_patch  = mpl.patches.Patch(color='none', label=str(len(data[x_key]))+' points')
    notes_string = ''.join(data.notes.unique())
    # Only add the notes_string if it contains something
    if len(notes_string) > 1:
        notes_patch  = mpl.patches.Patch(color='none', label=notes_string)
        ax.legend(handles=[n_pts_patch, notes_patch])
    else:
        ax.legend(handles=[n_pts_patch])

################################################################################

def get_var_color(var):
    """
    Takes in the variable name and for the variable to colormap

    var         A string of the variable name to get the color for
    """
    # Build dictionary of available colors
    vars = {
            'aiT':'salmon',
            'aCT':'salmon',
            'BSP':'darkturquoise',
            'BSA':'darkturquoise'
            }
    if var in ['entry', 'prof_no', 'dt_start', 'dt_end', 'lon', 'lat', 'press', 'depth', 'og_press', 'og_depth', 'p_theta_max']:
        return std_clr
    elif var in ['iT', 'CT', 'theta_max', 'alpha']:
        return 'lightcoral'
    elif var in ['SP', 'SA', 's_theta_max', 'beta']:
        return 'cornflowerblue'
    elif var in ['sigma']:
        return 'mediumpurple'
    elif var in ['ma_iT', 'ma_CT', 'la_iT', 'la_CT']:
        return 'tab:red'
    elif var in ['ma_SP', 'ma_SA', 'la_SP', 'la_SA']:
        return 'tab:blue'
    elif var in ['ma_sigma', 'la_sigma']:
        return 'tab:purple'
    if var in vars.keys():
        return vars[var]
    else:
        return None

################################################################################

def get_color_map(cmap_var):
    """
    Takes in the variable name and for the variable to colormap

    cmap_var    A string of the variable name for the colormap
    """
    # Build dictionary of axis labels
    cmaps = {'entry':'plasma',
             'prof_no':'plasma',
             'dt_start':'viridis',
             'dt_end':'viridis',
             'lon':'YlOrRd',
             'lat':'PuBuGn',
             'R_rho':'ocean',
             'density_hist':'inferno'
             }
    if cmap_var in ['press', 'depth', 'p_theta_max']:
        return 'cividis'
    elif cmap_var in ['iT', 'CT', 'theta_max', 'alpha', 'aiT', 'aCT', 'ma_iT', 'ma_CT', 'la_iT', 'la_CT']:
        return 'Reds'
    elif cmap_var in ['SP', 'SA', 's_theta_max', 'beta', 'BSP', 'BSA', 'ma_SP', 'ma_SA', 'la_SP', 'la_SA']:
        return 'Blues'
    elif cmap_var in ['sigma', 'ma_sigma', 'la_sigma']:
        return 'Purples'
    elif cmap_var in ['BL_yn', 'up_cast', 'ss_mask']:
        cmap = mpl.colors.ListedColormap(['green'])
        cmap.set_bad(color='red')
        return cmap
    if cmap_var in cmaps.keys():
        return cmaps[cmap_var]
    else:
        return None

################################################################################
# Main plotting function #######################################################
################################################################################

def make_subplot(ax, a_group, fig, ax_pos):
    """
    Takes in an Analysis_Group object which has the data and plotting parameters
    to produce a subplot. Returns the x and y labels and the subplot title

    ax              The axis on which to make the plot
    a_group         A Analysis_Group object containing the info to create this subplot
    fig             The figure in which ax is contained
    ax_pos          A tuple of the ax (rows, cols, linear number of this subplot)
    """
    # Get relevant parameters for the plot
    pp = a_group.plt_params
    plot_type = pp.plot_type
    clr_map   = pp.clr_map
    # Decide on a plot type
    if plot_type == 'xy':
        ## Make a standard x vs. y scatter plot
        # Set the main x and y data keys
        x_key = pp.x_vars[0]
        y_key = pp.y_vars[0]
        # Check for histogram
        if x_key == 'hist' or y_key == 'hist':
            plot_hist = True
        else:
            plot_hist = False
        # Check for twin x and y data keys
        try:
            tw_x_key = pp.x_vars[1]
            tw_ax_y  = ax.twiny()
        except:
            tw_x_key = None
            tw_ax_y  = None
        try:
            tw_y_key = pp.y_vars[1]
            tw_ax_x  = ax.twinx()
        except:
            tw_y_key = None
            tw_ax_x  = None
        # Check whether to cluster this data
        # Determine the color mapping to be used
        if clr_map in a_group.vars_to_keep:
            if pp.plot_scale == 'by_pf':
                if clr_map not in pf_vars:
                    print('Cannot use',clr_map,'with plot scale by_pf')
                    exit(0)
            # Concatonate all the pandas data frames together
            df = pd.concat(a_group.data_frames)
            # Format the dates if necessary
            if clr_map == 'dt_start' or clr_map == 'dt_end':
                cmap_data = mpl.dates.date2num(df[clr_map])
            else:
                cmap_data = df[clr_map]
            # Get the colormap
            this_cmap = get_color_map(clr_map)

            if plot_hist:
                return plot_histogram(x_key, y_key, ax, a_group, pp, clr_map=clr_map)
            heatmap = ax.scatter(df[x_key], df[y_key], c=cmap_data, cmap=this_cmap, s=mrk_size, marker=std_marker)
            # Invert y-axis if specified
            if y_key in y_invert_vars:
                ax.invert_yaxis()
            # Plot on twin axes, if specified
            if not isinstance(tw_x_key, type(None)):
                tw_clr = get_var_color(tw_x_key)
                if tw_clr == std_clr:
                    tw_clr = alt_std_clr
                # Add backing x to distinguish from main axis
                tw_ax_y.scatter(df[tw_x_key], df[y_key], color=tw_clr, s=mrk_size*10, marker='x')
                tw_ax_y.scatter(df[tw_x_key], df[y_key], c=cmap_data, cmap=this_cmap, s=mrk_size, marker=std_marker)
                tw_ax_y.set_xlabel(pp.xlabels[1])
                # Change color of the ticks on the twin axis
                tw_ax_y.tick_params(axis='x', colors=tw_clr)
                # Create the colorbar
                cbar = plt.colorbar(heatmap, ax=tw_ax_y)
            elif not isinstance(tw_y_key, type(None)):
                tw_clr = get_var_color(tw_y_key)
                if tw_clr == std_clr:
                    tw_clr = alt_std_clr
                # Add backing x to distinguish from main axis
                tw_ax_x.scatter(df[x_key], df[tw_y_key], color=tw_clr, s=mrk_size*10, marker='x')
                tw_ax_x.scatter(df[x_key], df[tw_y_key], c=cmap_data, cmap=this_cmap, s=mrk_size, marker=std_marker)
                tw_ax_x.set_ylabel(pp.ylabels[1])
                # Change color of the ticks on the twin axis
                tw_ax_x.tick_params(axis='y', colors=tw_clr)
                # Create the colorbar
                cbar = plt.colorbar(heatmap, ax=tw_ax_x)
            else:
                # Create the colorbar
                cbar = plt.colorbar(heatmap, ax=ax)
            # Format the colorbar ticks, if necessary
            if clr_map == 'dt_start' or clr_map == 'dt_end':
                loc = mpl.dates.AutoDateLocator()
                cbar.ax.yaxis.set_major_locator(loc)
                cbar.ax.yaxis.set_major_formatter(mpl.dates.ConciseDateFormatter(loc))
            cbar.set_label(pp.clabel)
            # Add a standard legend
            add_std_legend(ax, df, x_key)
            # Add a standard title
            plt_title = add_std_title(a_group)
            return pp.xlabels[0], pp.ylabels[0], plt_title, ax
        elif clr_map == 'clr_all_same':
            # Concatonate all the pandas data frames together
            df = pd.concat(a_group.data_frames)
            # Check for cluster-based variables
            if x_key in clstr_vars or y_key in clstr_vars:
                min_cs, min_s, cl_x_var, cl_y_var, plot_slopes, b_a_w_plt = get_cluster_args(pp)
                df, rel_val = HDBSCAN_(df, cl_x_var, cl_y_var, min_cs, min_samp=min_s, extra_cl_vars=[x_key,y_key])
            # Check for histogram
            if plot_hist:
                return plot_histogram(x_key, y_key, ax, a_group, pp, clr_map, df=df, txk=tw_x_key, tay=tw_ax_y, tyk=tw_y_key, tax=tw_ax_x)
            # Plot every point the same color, size, and marker
            ax.scatter(df[x_key], df[y_key], color=std_clr, s=mrk_size, marker=std_marker, alpha=mrk_alpha)
            # Invert y-axis if specified
            if y_key in y_invert_vars:
                ax.invert_yaxis()
            # Plot on twin axes, if specified
            if not isinstance(tw_x_key, type(None)):
                tw_clr = get_var_color(tw_x_key)
                if tw_clr == std_clr:
                    tw_clr = alt_std_clr
                tw_ax_y.scatter(df[tw_x_key], df[y_key], color=tw_clr, s=mrk_size, marker=std_marker, alpha=mrk_alpha)
                tw_ax_y.set_xlabel(pp.xlabels[1])
                # Change color of the ticks on the twin axis
                tw_ax_y.tick_params(axis='x', colors=tw_clr)
            elif not isinstance(tw_y_key, type(None)):
                tw_clr = get_var_color(tw_y_key)
                if tw_clr == std_clr:
                    tw_clr = alt_std_clr
                tw_ax_x.scatter(df[x_key], df[tw_y_key], color=tw_clr, s=mrk_size, marker=std_marker, alpha=mrk_alpha)
                tw_ax_x.set_ylabel(pp.ylabels[1])
                # Change color of the ticks on the twin axis
                tw_ax_x.tick_params(axis='y', colors=tw_clr)
            # Add a standard legend
            add_std_legend(ax, df, x_key)
            # Add a standard title
            plt_title = add_std_title(a_group)
            return pp.xlabels[0], pp.ylabels[0], plt_title, ax
        elif clr_map == 'clr_by_source':
            if plot_hist:
                return plot_histogram(x_key, y_key, ax, a_group, pp, clr_map)
            # Find the list of sources
            sources_list = []
            for df in a_group.data_frames:
                # Get unique sources
                these_sources = np.unique(df['source'])
                for s in these_sources:
                    sources_list.append(s)
            # The pandas version of 'unique()' preserves the original order
            sources_list = pd.unique(pd.Series(sources_list))
            i = 0
            lgnd_hndls = []
            for source in sources_list:
                # Decide on the color, don't go off the end of the array
                my_clr = mpl_clrs[i%len(mpl_clrs)]
                these_dfs = []
                for df in a_group.data_frames:
                    these_dfs.append(df[df['source'] == source])
                this_df = pd.concat(these_dfs)
                # Plot every point from this df the same color, size, and marker
                ax.scatter(this_df[x_key], this_df[y_key], color=my_clr, s=mrk_size, marker=std_marker, alpha=mrk_alpha)
                i += 1
                # Add legend to report the total number of points for this instrmt
                lgnd_label = source+': '+str(len(this_df[x_key]))+' points'
                lgnd_hndls.append(mpl.patches.Patch(color=my_clr, label=lgnd_label))
            notes_string = ''.join(this_df.notes.unique())
            # Only add the notes_string if it contains something
            if len(notes_string) > 1:
                notes_patch  = mpl.patches.Patch(color='none', label=notes_string)
                lgnd_hndls.append(notes_patch)
            # Add legend with custom handles
            lgnd = ax.legend(handles=lgnd_hndls)
            # Add a standard title
            plt_title = add_std_title(a_group)
            return pp.xlabels[0], pp.ylabels[0], plt_title, ax
        elif clr_map == 'clr_by_instrmt':
            if plot_hist:
                return plot_histogram(x_key, y_key, ax, a_group, pp, clr_map)
            i = 0
            lgnd_hndls = []
            # Loop through each data frame, the same as looping through instrmts
            for df in a_group.data_frames:
                df['source-instrmt'] = df['source']+' '+df['instrmt']
                # Get instrument name
                s_instrmt = np.unique(df['source-instrmt'])[0]
                # Decide on the color, don't go off the end of the array
                my_clr = mpl_clrs[i%len(mpl_clrs)]
                # Plot every point from this df the same color, size, and marker
                ax.scatter(df[x_key], df[y_key], color=my_clr, s=mrk_size, marker=std_marker, alpha=mrk_alpha)
                i += 1
                # Add legend to report the total number of points for this instrmt
                lgnd_label = s_instrmt+': '+str(len(df[x_key]))+' points'
                lgnd_hndls.append(mpl.patches.Patch(color=my_clr, label=lgnd_label))
                notes_string = ''.join(df.notes.unique())
            # Only add the notes_string if it contains something
            if len(notes_string) > 1:
                notes_patch  = mpl.patches.Patch(color='none', label=notes_string)
                lgnd_hndls.append(notes_patch)
            # Add legend with custom handles
            lgnd = ax.legend(handles=lgnd_hndls)
            # Add a standard title
            plt_title = add_std_title(a_group)
            return pp.xlabels[0], pp.ylabels[0], plt_title, ax
        elif clr_map == 'density_hist':
            if plot_hist:
                print('Cannot use density_hist colormap with the `hist` variable')
                exit(0)
            # Concatonate all the pandas data frames together
            df = pd.concat(a_group.data_frames)
            # Plot a density histogram where each grid box is colored to show how
            #   many points fall within it
            # Get the density histogram plotting parameters from extra args
            d_hist_dict = pp.extra_args
            if isinstance(d_hist_dict, type(None)):
                # If none are given, use the defaults here
                clr_min = 0
                clr_max = 20
                clr_ext = 'max'        # adds arrow indicating values go past the bounds
                #                       #   use 'min', 'max', or 'both'
                xy_bins = 250
            else:
                # Pull out the values from the dictionary provided
                clr_min = d_hist_dict['clr_min']
                clr_max = d_hist_dict['clr_max']
                clr_ext = d_hist_dict['clr_ext']
                xy_bins = d_hist_dict['xy_bins']
            # Make the 2D histogram, the number of bins really changes the outcome
            heatmap = ax.hist2d(df[x_key], df[y_key], bins=xy_bins, cmap=get_color_map(clr_map), vmin=clr_min, vmax=clr_max)
            # `hist2d` returns a tuple, the index 3 of which is the mappable for a colorbar
            cbar = plt.colorbar(heatmap[3], ax=ax, extend=clr_ext)
            cbar.set_label('points per pixel')
            # Add legend to report the total number of points and pixels on the plot
            n_pts_patch  = mpl.patches.Patch(color='none', label=str(len(df[x_key]))+' points')
            pixel_patch  = mpl.patches.Patch(color='none', label=str(xy_bins)+'x'+str(xy_bins)+' pixels')
            notes_string = ''.join(df.notes.unique())
            # Only add the notes_string if it contains something
            if len(notes_string) > 1:
                notes_patch  = mpl.patches.Patch(color='none', label=notes_string)
                ax.legend(handles=[n_pts_patch, pixel_patch, notes_patch])
            else:
                ax.legend(handles=[n_pts_patch, pixel_patch])
            # Add a standard title
            plt_title = add_std_title(a_group)
            return pp.xlabels[0], pp.ylabels[0], plt_title, ax
        elif clr_map in ['cluster']:
            # Add a standard title
            plt_title = add_std_title(a_group)
            # Legend is handled inside plot_clusters() or plot_n_clusters_per_n_prof()
            # Concatonate all the pandas data frames together
            df = pd.concat(a_group.data_frames)
            min_cs, min_s, cl_x_var, cl_y_var, plot_slopes, b_a_w_plt = get_cluster_args(pp)
            plot_clusters(ax, df, x_key, y_key, cl_x_var, cl_y_var, clr_map, min_cs, min_samp=min_s, box_and_whisker=b_a_w_plt)
            return pp.xlabels[0], pp.ylabels[0], plt_title, ax
            #
        else:
            # Did not provide a valid clr_map
            print('Colormap',clr_map,'not valid')
            exit(0)
        #
    #
    elif plot_type == 'map':
        ## Plot profile locations on a map of the Arctic Ocean
        # Get the map plotting parameters from extra args
        map_dict = pp.extra_args
        # See what was in that dictionary
        try:
            map_extent = map_dict['map_extent']
        except:
            map_extent = None
        #   Set latitude and longitude extents
        #   I found these values by guess-and-check, there really isn't a good way
        #       to know beforehand what you'll actually get
        if map_extent == 'Canada_Basin':
            cent_lon = -140
            ex_N = 80
            ex_S = 69
            ex_E = -156
            ex_W = -124
        elif map_extent == 'Western_Arctic':
            cent_lon = -140
            ex_N = 80
            ex_S = 69
            ex_E = -165
            ex_W = -124
        else:
            cent_lon = 0
            ex_N = 90
            ex_S = 70
            ex_E = -180
            ex_W = 180
        # Remove the current axis
        ax.remove()
        # Replace axis with one that can be made into a map
        ax = fig.add_subplot(ax_pos, projection=ccrs.NorthPolarStereo(central_longitude=cent_lon))
        ax.set_extent([ex_E, ex_W, ex_S, ex_N], ccrs.PlateCarree())
        #   Add ocean first, then land. Otherwise the ocean covers the land shapes
        # ax.add_feature(cartopy.feature.OCEAN, color=clr_ocean)
        ax.add_feature(cartopy.feature.LAND, color=clr_land, alpha=0.5)
        #   Add gridlines to show longitude and latitude
        gl = ax.gridlines(draw_labels=True, color=clr_lines, alpha=0.3, linestyle='--')
        #       x is actually all labels around the edge
        gl.xlabel_style = {'size':6, 'color':clr_lines}
        #       y is actually all labels within map
        gl.ylabel_style = {'size':6, 'color':clr_lines}
        #   Plotting the coastlines takes a really long time
        # ax.coastlines()
        # Determine the color mapping to be used
        if clr_map in a_group.vars_to_keep:
            # Make sure it isn't a vertical variable
            if clr_map in vertical_vars:
                print('Cannot use',clr_map,'as colormap for a map plot')
                exit(0)
            # Concatonate all the pandas data frames together
            df = pd.concat(a_group.data_frames)
            # If not plotting very many points, increase the marker size
            if len(df) < 10:
                mrk_s = big_map_mrkr
            else:
                mrk_s = map_mrk_size
            # Format the dates if necessary
            if clr_map == 'dt_start' or clr_map == 'dt_end':
                cmap_data = mpl.dates.date2num(df[clr_map])
            else:
                cmap_data = df[clr_map]
            # The color of each point corresponds to the number of the profile it came from
            heatmap = ax.scatter(df['lon'], df['lat'], c=cmap_data, cmap=get_color_map(clr_map), s=mrk_s, marker=map_marker, linewidths=map_ln_wid, transform=ccrs.PlateCarree())
            # Create the colorbar
            cbar = plt.colorbar(heatmap, ax=ax)
            # Format the colorbar ticks, if necessary
            if clr_map == 'dt_start' or clr_map == 'dt_end':
                loc = mpl.dates.AutoDateLocator()
                cbar.ax.yaxis.set_major_locator(loc)
                cbar.ax.yaxis.set_major_formatter(mpl.dates.ConciseDateFormatter(loc))
            cbar.set_label(a_group.data_set.var_attr_dicts[0][clr_map]['label'])
            # Add a standard legend
            add_std_legend(ax, df, 'lon')
            # Add a standard title
            plt_title = add_std_title(a_group)
            return pp.xlabels[0], pp.ylabels[0], plt_title, ax
        if clr_map == 'clr_all_same':
            # Concatonate all the pandas data frames together
            df = pd.concat(a_group.data_frames)
            # If not plotting very many points, increase the marker size
            if len(df) < 10:
                mrk_s = big_map_mrkr
            else:
                mrk_s = map_mrk_size
            # Plot every point the same color, size, and marker
            ax.scatter(df['lon'], df['lat'], color=std_clr, s=mrk_s, marker=map_marker, alpha=mrk_alpha, linewidths=map_ln_wid, transform=ccrs.PlateCarree())
            # Add a standard legend
            add_std_legend(ax, df, 'lon')
            # Add a standard title
            plt_title = add_std_title(a_group)
            return pp.xlabels[0], pp.ylabels[0], plt_title, ax
        elif clr_map == 'clr_by_source':
            # Find the list of sources
            sources_list = []
            for df in a_group.data_frames:
                # Get unique sources
                these_sources = np.unique(df['source'])
                for s in these_sources:
                    sources_list.append(s)
            # The pandas version of 'unique()' preserves the original order
            sources_list = pd.unique(pd.Series(sources_list))
            i = 0
            lgnd_hndls = []
            for source in sources_list:
                # Decide on the color, don't go off the end of the array
                my_clr = mpl_clrs[i%len(mpl_clrs)]
                these_dfs = []
                for df in a_group.data_frames:
                    these_dfs.append(df[df['source'] == source])
                this_df = pd.concat(these_dfs)
                # If not plotting very many points, increase the marker size
                if len(this_df) < 10:
                    mrk_s = big_map_mrkr
                else:
                    mrk_s = map_mrk_size
                # Plot every point from this df the same color, size, and marker
                ax.scatter(this_df['lon'], this_df['lat'], color=my_clr, s=mrk_s, marker=map_marker, alpha=mrk_alpha, linewidths=map_ln_wid, transform=ccrs.PlateCarree())
                i += 1
                # Add legend to report the total number of points for this instrmt
                lgnd_label = source+': '+str(len(this_df['lon']))+' points'
                lgnd_hndls.append(mpl.patches.Patch(color=my_clr, label=lgnd_label))
                notes_string = ''.join(this_df.notes.unique())
            # Only add the notes_string if it contains something
            if len(notes_string) > 1:
                notes_patch  = mpl.patches.Patch(color='none', label=notes_string)
                lgnd_hndls.append(notes_patch)
            # Add legend with custom handles
            lgnd = ax.legend(handles=lgnd_hndls)
            # Add a standard title
            plt_title = add_std_title(a_group)
            return pp.xlabels[0], pp.ylabels[0], plt_title, ax
        elif clr_map == 'clr_by_instrmt':
            i = 0
            lgnd_hndls = []
            # Loop through each data frame, the same as looping through instrmts
            for df in a_group.data_frames:
                df['source-instrmt'] = df['source']+' '+df['instrmt']
                # If not plotting very many points, increase the marker size
                if len(df) < 10:
                    mrk_s = big_map_mrkr
                else:
                    mrk_s = map_mrk_size
                # Get instrument name
                s_instrmt = np.unique(df['source-instrmt'])[0]
                # Decide on the color, don't go off the end of the array
                my_clr = mpl_clrs[i%len(mpl_clrs)]
                # Plot every point from this df the same color, size, and marker
                ax.scatter(df['lon'], df['lat'], color=my_clr, s=mrk_s, marker=map_marker, alpha=mrk_alpha, linewidths=map_ln_wid, transform=ccrs.PlateCarree())
                i += 1
                # Add legend to report the total number of points for this instrmt
                lgnd_label = s_instrmt+': '+str(len(df['lon']))+' points'
                lgnd_hndls.append(mpl.patches.Patch(color=my_clr, label=lgnd_label))
                notes_string = ''.join(df.notes.unique())
            # Only add the notes_string if it contains something
            if len(notes_string) > 1:
                notes_patch  = mpl.patches.Patch(color='none', label=notes_string)
                lgnd_hndls.append(notes_patch)
            # Add legend with custom handles
            lgnd = ax.legend(handles=lgnd_hndls)
            # Add a standard title
            plt_title = add_std_title(a_group)
            return pp.xlabels[0], pp.ylabels[0], plt_title, ax
    elif plot_type == 'profiles':
        # Call profile plotting function
        return plot_profiles(ax, a_group, pp)
    else:
        # Did not provide a valid plot type
        print('Plot type',plot_type,'not valid')
        exit(0)
    #
    #
    #

    #
    print('ERROR: Should not have gotten here')
    return a_group.xlabel, a_group.ylabel, plt_title, ax

################################################################################
# Auxiliary plotting functions #################################################
################################################################################

def plot_histogram(x_key, y_key, ax, a_group, pp, clr_map, df=None, txk=None, tay=None, tyk=None, tax=None):
    """
    Takes in an Analysis_Group object which has the data and plotting parameters
    to produce a subplot of individual profiles. Returns the x and y labels and
    the subplot title

    x_key           String
    ax              The axis on which to make the plot
    a_group         A Analysis_Group object containing the info to create this subplot
    pp              The Plot_Parameters object for a_group
    """
    if x_key == 'hist':
        var_key = y_key
        orientation = 'horizontal'
        x_label = 'Number of points'
        y_label = pp.ylabels[0]
        tw_var_key = tyk
        tw_ax = tax
        tw_label = pp.ylabels[1]
    elif y_key == 'hist':
        var_key = x_key
        orientation = 'vertical'
        x_label = pp.xlabels[0]
        y_label = 'Number of points'
        tw_var_key = txk
        tw_ax = tay
        tw_label = pp.xlabels[1]
    # Histograms don't work with datetime data
    if var_key in ['dt_start', 'dt_end']:
        print('Cannot make histogram with',var_key,'data')
        exit(0)
    # Determine the color mapping to be used
    if clr_map == 'clr_all_same':
        # Get histogram parameters
        h_var, res_bins, median, mean, std_dev = get_hist_params(df, var_key)
        # Plot the histogram
        ax.hist(h_var, bins=res_bins, color=std_clr, orientation=orientation)
        # Add legend to report overall statistics
        n_pts_patch   = mpl.patches.Patch(color=std_clr, label=str(len(h_var))+' points')
        median_patch  = mpl.patches.Patch(color=std_clr, label='Median:  '+'%.4f'%median)
        mean_patch    = mpl.patches.Patch(color=std_clr, label='Mean:    ' + '%.4f'%mean)
        std_dev_patch = mpl.patches.Patch(color=std_clr, label='Std dev: '+'%.4f'%std_dev)
        hndls = [n_pts_patch, median_patch, mean_patch, std_dev_patch]
        notes_string = ''.join(df.notes.unique())
        # Plot twin axis if specified
        if not isinstance(tw_var_key, type(None)):
            tw_clr = get_var_color(tw_var_key)
            if tw_clr == std_clr:
                tw_clr = alt_std_clr
            # Get histogram parameters
            h_var, res_bins, median, mean, std_dev = get_hist_params(df, tw_var_key)
            # Plot the histogram
            tw_ax.hist(h_var, bins=res_bins, color=tw_clr, alpha=mrk_alpha, orientation=orientation)
            if orientation == 'vertical':
                tw_ax.set_xlabel(tw_label)
                tw_ax.tick_params(axis='x', colors=tw_clr)
            elif orientation == 'horizontal':
                tw_ax.set_ylabel(tw_label)
                tw_ax.tick_params(axis='y', colors=tw_clr)
            # Add legend to report overall statistics
            n_pts_patch   = mpl.patches.Patch(color=tw_clr, label=str(len(h_var))+' points', alpha=mrk_alpha)
            median_patch  = mpl.patches.Patch(color=tw_clr, label='Median:  '+'%.4f'%median, alpha=mrk_alpha)
            mean_patch    = mpl.patches.Patch(color=tw_clr, label='Mean:    ' + '%.4f'%mean, alpha=mrk_alpha)
            std_dev_patch = mpl.patches.Patch(color=tw_clr, label='Std dev: '+'%.4f'%std_dev, alpha=mrk_alpha)
            tw_notes_string = ''.join(df.notes.unique())
            # Only add the notes_string if it contains something
            if len(tw_notes_string) > 1:
                tw_notes_patch  = mpl.patches.Patch(color='none', label=notes_string, alpha=mrk_alpha)
                tw_hndls=[n_pts_patch, median_patch, mean_patch, std_dev_patch, tw_notes_patch]
            else:
                tw_hndls=[n_pts_patch, median_patch, mean_patch, std_dev_patch]
        else:
            tw_hndls = []
        # Only add the notes_string if it contains something
        if len(notes_string) > 1:
            notes_patch  = mpl.patches.Patch(color='none', label=notes_string)
            ax.legend(handles=hndls+notes_patch+tw_hndls)
        else:
            ax.legend(handles=hndls+tw_hndls)
        # Add a standard title
        plt_title = add_std_title(a_group)
        return x_label, y_label, plt_title, ax
    elif clr_map == 'clr_by_source':
        # Find the list of sources
        sources_list = []
        for df in a_group.data_frames:
            # Get unique sources
            these_sources = np.unique(df['source'])
            for s in these_sources:
                sources_list.append(s)
        # The pandas version of 'unique()' preserves the original order
        sources_list = pd.unique(pd.Series(sources_list))
        i = 0
        lgnd_hndls = []
        for source in sources_list:
            # Decide on the color, don't go off the end of the array
            my_clr = mpl_clrs[i%len(mpl_clrs)]
            these_dfs = []
            for df in a_group.data_frames:
                these_dfs.append(df[df['source'] == source])
            this_df = pd.concat(these_dfs)
            # Get histogram parameters
            h_var, res_bins, median, mean, std_dev = get_hist_params(this_df, var_key)
            # Plot the histogram
            ax.hist(h_var, bins=res_bins, color=my_clr, alpha=mrk_alpha, orientation=orientation)
            i += 1
            # Add legend handle to report the total number of points for this source
            lgnd_label = source+': '+str(len(this_df[var_key]))+' points, Median:'+'%.4f'%median
            lgnd_hndls.append(mpl.patches.Patch(color=my_clr, label=lgnd_label, alpha=mrk_alpha))
            # Add legend handle to report overall statistics
            lgnd_label = 'Mean:'+ '%.4f'%mean+', Std dev:'+'%.4f'%std_dev
            lgnd_hndls.append(mpl.patches.Patch(color=my_clr, label=lgnd_label, alpha=mrk_alpha))
            notes_string = ''.join(this_df.notes.unique())
        # Only add the notes_string if it contains something
        if len(notes_string) > 1:
            notes_patch  = mpl.patches.Patch(color='none', label=notes_string)
            lgnd_hndls.append(notes_patch)
        # Add legend with custom handles
        lgnd = ax.legend(handles=lgnd_hndls)
        # Add a standard title
        plt_title = add_std_title(a_group)
        return x_label, y_label, plt_title, ax
    elif clr_map == 'clr_by_instrmt':
        i = 0
        lgnd_hndls = []
        # Loop through each data frame, the same as looping through instrmts
        for df in a_group.data_frames:
            df['source-instrmt'] = df['source']+' '+df['instrmt']
            # Get instrument name
            s_instrmt = np.unique(df['source-instrmt'])[0]
            # Decide on the color, don't go off the end of the array
            my_clr = mpl_clrs[i%len(mpl_clrs)]
            # Get histogram parameters
            h_var, res_bins, median, mean, std_dev = get_hist_params(df, var_key)
            # Plot the histogram
            ax.hist(h_var, bins=res_bins, color=my_clr, alpha=mrk_alpha, orientation=orientation)
            i += 1
            # Add legend to report the total number of points for this instrmt
            lgnd_label = s_instrmt+': '+str(len(df[var_key]))+' points'
            lgnd_hndls.append(mpl.patches.Patch(color=my_clr, label=lgnd_label, alpha=mrk_alpha))
            # Add legend handle to report overall statistics
            lgnd_label = 'Mean:'+ '%.4f'%mean+', Std dev:'+'%.4f'%std_dev
            lgnd_hndls.append(mpl.patches.Patch(color=my_clr, label=lgnd_label, alpha=mrk_alpha))
            notes_string = ''.join(df.notes.unique())
        # Only add the notes_string if it contains something
        if len(notes_string) > 1:
            notes_patch  = mpl.patches.Patch(color='none', label=notes_string)
            lgnd_hndls.append(notes_patch)
        # Add legend with custom handles
        lgnd = ax.legend(handles=lgnd_hndls)
        # Add a standard title
        plt_title = add_std_title(a_group)
        return x_label, y_label, plt_title, ax
    else:
        # Did not provide a valid clr_map
        print('Colormap',clr_map,'not valid')
        exit(0)

################################################################################

def get_hist_params(df, h_key):
    """
    Returns the needed information to make a histogram

    df      A pandas data frame of the data to plot
    h_key   A string of the column header to plot
    """
    # Pull out the variable to plot, removing null values
    h_var = np.array(df[df[h_key].notnull()][h_key])
    # Find overall statistics
    median  = np.median(h_var)
    mean    = np.mean(h_var)
    std_dev = np.std(h_var)
    # Define the bins to use in the histogram, np.arange(start, stop, step)
    start = mean - 3*std_dev
    stop  = mean + 3*std_dev
    step  = std_dev / 25
    res_bins = np.arange(start, stop, step)
    return h_var, res_bins, median, mean, std_dev

################################################################################

def plot_profiles(ax, a_group, pp, clr_map=None):
    """
    Takes in an Analysis_Group object which has the data and plotting parameters
    to produce a subplot of individual profiles. Returns the x and y labels and
    the subplot title

    ax              The axis on which to make the plot
    a_group         A Analysis_Group object containing the info to create this subplot
    pp              The Plot_Parameters object for a_group
    """
    scale = pp.plot_scale
    if scale == 'by_pf':
        print('Cannot use',pp.plot_type,'with plot scale by_pf')
        exit(0)
    # Declare variables related to plotting detected layers
    clr_map = pp.clr_map
    ## Make a plot of the given profiles vs. the vertical
    # Set the main x and y data keys
    x_key = pp.x_vars[0]
    y_key = pp.y_vars[0]
    var_clr = get_var_color(x_key)
    # Check for histogram
    if x_key == 'hist' or y_key == 'hist':
        print('Cannot plot histograms with profiles plot type')
    # Check for twin x and y data keys
    try:
        tw_x_key = pp.x_vars[1]
        tw_ax_y  = ax.twiny()
        tw_clr = get_var_color(tw_x_key)
        if tw_clr == std_clr:
            tw_clr = alt_std_clr
    except:
        tw_x_key = None
        tw_ax_y  = None
    try:
        tw_y_key = pp.y_vars[1]
        tw_ax_x  = ax.twinx()
        tw_clr = get_var_color(tw_y_key)
        if tw_clr == std_clr:
            tw_clr = alt_std_clr
    except:
        tw_y_key = None
        tw_ax_x  = None
    #
    # Make a blank list for dataframes of each profile
    profile_dfs = []
    # Loop through each data frame, the same as looping through instrmts,
    #   to build a list of dataframes for each profile to plot
    for df in a_group.data_frames:
        # Filter to specified range if applicable
        if not isinstance(a_group.plt_params.ax_lims, type(None)):
            try:
                y_lims = a_group.plt_params.ax_lims['y_lims']
                # Get endpoints of vertical range, make sure they are positive
                y_lims = [abs(ele) for ele in y_lims]
                y_max = max(y_lims)
                y_min = min(y_lims)
                # Filter the data frame to the specified vertical range
                df = df[(df[y_key] < y_max) & (df[y_key] > y_min)]
            except:
                foo = 2
            #
        # Clean out the null values
        df = df[df[x_key].notnull() & df[y_key].notnull()]
        if tw_x_key:
            df = df[df[tw_x_key].notnull()]
        if tw_y_key:
            df = df[df[tw_y_key].notnull()]
        # Get notes
        notes_string = ''.join(df.notes.unique())
        # Find the unique profiles for this instrmt
        pfs_in_this_df = np.unique(np.array(df['prof_no']))
        print('pfs_in_this_df:',pfs_in_this_df)
        # Make sure you're not trying to plot too many profiles
        if len(pfs_in_this_df) > 10:
            print('You are trying to plot',len(pfs_in_this_df),'profiles')
            print('That is too many. Try to plot less than 10')
            exit(0)
        # else:
        #     print('Plotting',len(pfs_in_this_df),'profiles')
        # Loop through each profile
        for pf_no in pfs_in_this_df:
            # print('')
            # print('profile:',pf_no)
            # Get just the part of the dataframe for this profile
            pf_df = df[df['prof_no']==pf_no]
            if scale == 'by_vert':
                # Drop `Layer` dimension to reduce size of data arrays
                #   (need to make the index `Vertical` a column first)
                pf_df_v = pf_df.reset_index(level=['Vertical'])
                pf_df_v.drop_duplicates(inplace=True, subset=['Vertical'])
            elif scale == 'by_layer':
                # Drop `Vertical` dimension to reduce size of data arrays
                #   (need to make the index `Layer` a column first)
                pf_df_v = pf_df.reset_index(level=['Layer'])
                pf_df_v.drop_duplicates(inplace=True, subset=['Layer'])
                # Technically, this profile dataframe isn't `Vertical` but
                #   it works as is, so I'll keep the variable name
            profile_dfs.append(pf_df_v)
        #
    # Check to see whether any profiles were actually loaded
    if len(profile_dfs) < 1:
        print('No profiles loaded')
        # Add a standard title
        plt_title = add_std_title(a_group)
        return pp.xlabels[0], pp.ylabels[0], plt_title, ax
    # Plot each profile
    for i in range(len(profile_dfs)):
        # Pull the dataframe for this profile
        pf_df = profile_dfs[i]
        # Make a label for this profile
        pf_label = pf_df['source'][0]+pf_df['instrmt'][0]+'-'+str(int(pf_df['prof_no'][0]))
        # Decide on marker and line styles, don't go off the end of the array
        mkr     = mpl_mrks[i%len(mpl_mrks)]
        l_style = l_styles[i%len(l_styles)]
        # Get array to plot and find bounds
        if i == 0:
            # Pull data to plot
            xvar = pf_df[x_key]
            # Find upper and lower bounds of first profile, for reference points
            xvar_low  = min(xvar)
            xvar_high = max(xvar)
            # Define shift for the profile
            xv_shift = (xvar_high - xvar_low)/5
            # Find upper and lower bounds of first profile for twin axis
            if tw_x_key:
                tvar = pf_df[tw_x_key]
                twin_low  = min(tvar)
                twin_high = max(tvar)
                tw_shift  = (twin_high - twin_low)/5
            #
        # Adjust the starting points of each subsequent profile
        elif i > 0:
            # Find array of data
            xvar = pf_df[x_key] - min(pf_df[x_key]) + xvar_high
            # Adjust upper bound
            xvar_high = max(xvar)
            if tw_x_key:
                tvar = pf_df[tw_x_key] - min(pf_df[tw_x_key]) + twin_high
                twin_high = max(tvar)
            #
        # Determine the color mapping to be used
        if clr_map in a_group.vars_to_keep:
            # Format the dates if necessary
            if clr_map == 'dt_start' or clr_map == 'dt_end':
                cmap_data = mpl.dates.date2num(pf_df[clr_map])
            else:
                cmap_data = pf_df[clr_map]
            # Plot the line of the profile
            ax.plot(xvar, pf_df[y_key], color=var_clr, linestyle=l_style, label=pf_label, zorder=1)
            # Get the colormap
            this_cmap = get_color_map(clr_map)
            # Plot the points as a heatmap
            heatmap = ax.scatter(xvar, pf_df[y_key], c=cmap_data, cmap=this_cmap, s=pf_mrk_size, marker=mkr)
            # Plot on twin axes, if specified
            if not isinstance(tw_x_key, type(None)):
                tw_ax_y.plot(tvar, pf_df[y_key], color=tw_clr, linestyle=l_style, zorder=1)
                tw_ax_y.scatter(tvar, pf_df[y_key], c=cmap_data, cmap=this_cmap, s=pf_mrk_size, marker=mkr)
            #
            # Create the colorbar, but only on the first profile
            if i == 0:
                cbar = plt.colorbar(heatmap, ax=ax)
                # Format the colorbar ticks, if necessary
                if clr_map == 'dt_start' or clr_map == 'dt_end':
                    loc = mpl.dates.AutoDateLocator()
                    cbar.ax.yaxis.set_major_locator(loc)
                    cbar.ax.yaxis.set_major_formatter(mpl.dates.ConciseDateFormatter(loc))
                cbar.set_label(pp.clabel)
        if clr_map == 'clr_all_same':
            # Plot every point the same color, size, and marker
            ax.plot(xvar, pf_df[y_key], color=var_clr, linestyle=l_style, label=pf_label, zorder=1)
            ax.scatter(xvar, pf_df[y_key], color=var_clr, s=pf_mrk_size, marker=mkr, alpha=mrk_alpha)
            # Plot on twin axes, if specified
            if not isinstance(tw_x_key, type(None)):
                tw_ax_y.plot(tvar, pf_df[y_key], color=tw_clr, linestyle=l_style, zorder=1)
                tw_ax_y.scatter(tvar, pf_df[y_key], color=tw_clr, s=pf_mrk_size, marker=mkr, alpha=mrk_alpha)
            #
        #
    #
    # Compensate for shifting the twin axis by adjusting the max xvar
    xvar_high = xvar_high + xv_shift
    # Adjust bounds on axes
    ax.set_xlim([xvar_low-0.5*xv_shift, xvar_high+xv_shift])
    # Invert y-axis if specified
    if y_key in y_invert_vars or tw_x_key in y_invert_vars:
        ax.invert_yaxis()
    if tw_x_key:
        tw_ax_y.set_xlim([twin_low-tw_shift, twin_high+0.5*tw_shift])
    # Plot on twin axes, if specified
    if not isinstance(tw_x_key, type(None)):
        tw_ax_y.set_xlabel(pp.xlabels[1])
        # Change color of the ticks on the twin axis
        tw_ax_y.tick_params(axis='x', colors=tw_clr)
    # Add legend
    lgnd = ax.legend()
    # Only add the notes_string if it contains something
    if len(notes_string) > 1:
        handles, labels = ax.get_legend_handles_labels()
        handles.append(mpl.patches.Patch(color='none'))
        labels.append(notes_string)
        lgnd = ax.legend(handles=handles, labels=labels)
    # Need to change the marker size for each label in the legend individually
    for hndl in lgnd.legendHandles:
        hndl._sizes = [lgnd_mrk_size]
    #
    # Add a standard title
    plt_title = add_std_title(a_group)
    return pp.xlabels[0], pp.ylabels[0], plt_title, ax

################################################################################

def get_cluster_args(pp):
    # Get the dictionary stored in extra_args
    cluster_plt_dict = pp.extra_args
    print('cluster_plt_dict:',cluster_plt_dict)
    # Get minimum cluster size parameter, if it was given
    try:
        min_cs = int(cluster_plt_dict['min_cs'])
    except:
        min_cs = None
    # Get minimum samples parameter, if it was given
    try:
        min_s = cluster_plt_dict['min_samp']
    except:
        min_s = None
    # Get x and y parameters, if given
    try:
        cl_x_var = cluster_plt_dict['cl_x_var']
        cl_y_var = cluster_plt_dict['cl_y_var']
    except:
        cl_x_var = None
        cl_y_var = None
    # Get the boolean for whether to plot trendline slopes or not
    try:
        plot_slopes = cluster_plt_dict['plot_slopes']
    except:
        plot_slopes = False
    # Check whether or not the box and whisker plots were called for
    try:
        b_a_w_plt = cluster_plt_dict['b_a_w_plt']
    except:
        b_a_w_plt = True
    return min_cs, min_s, cl_x_var, cl_y_var, plot_slopes, b_a_w_plt

################################################################################

def HDBSCAN_(df, x_key, y_key, min_cs, min_samp=None, extra_cl_vars=None):
    """
    Runs the HDBSCAN algorithm on the set of data specified. Returns a pandas
    dataframe with columns for x_key, y_key, 'cluster', and 'clst_prob' and a
    rough measure of the DBCV score from `relative_validity_`

    df          A pandas data frame with x_key and y_key as equal length columns
    x_key       String of the name of the column to use on the x-axis
    y_key       String of the name of the column to use on the y-axis
    min_cs      An integer, the minimum number of points for a cluster
    min_samp    An integer, number of points in neighborhood for a core point
    extra_cl_vars   A list of extra variables to potentially calculate
    """
    # Set the parameters of the HDBSCAN algorithm
    #   Note: must set gen_min_span_tree=True or you can't get `relative_validity_`
    hdbscan_1 = hdbscan.HDBSCAN(gen_min_span_tree=True, min_cluster_size=min_cs, min_samples=min_samp, cluster_selection_method='leaf')
    # Run the HDBSCAN algorithm
    hdbscan_1.fit_predict(df[[x_key,y_key]])
    # Add the cluster labels and probabilities to the dataframe
    df['cluster']   = hdbscan_1.labels_
    df['clst_prob'] = hdbscan_1.probabilities_
    rel_val = hdbscan_1.relative_validity_
    # Determine whether there are any new variables to calculate
    new_cl_vars = list(set(extra_cl_vars) & set(clstr_vars))
    if len(new_cl_vars) > 0:
        df = calc_extra_cl_vars(df, new_cl_vars)
    return df, rel_val

################################################################################

def calc_extra_cl_vars(df, new_cl_vars):
    """
    Takes in an already-clustered pandas data frame and a list of variables and,
    if there are extra variables to calculate, it will add those to the data frame

    df                  A pandas data frame of the data to plot
    new_cl_vars         A list of clustering-related variables to calculate
    """
    # Find the number of clusters
    n_clusters = max(df['cluster'])
    # Check for variables to calculate
    for this_var in new_cl_vars:
        # Split the prefix from the original variable (assumes an underscore split)
        split_var = this_var.split('_', 1)
        prefix = split_var[0]
        var = split_var[1]
        print('prefix:',prefix,'- var:',var)
        # Make a new blank column in the data frame for this variable
        df[this_var] = None
        # Calculate the new values based on the prefix
        if prefix == 'pca':
            # Calculate the per profile cluster average version of the variable
            #   Reduces the number of points to just one per cluster per profile
            # Loop over each profile
            n_pfs = int(max(df['entry'].values))
            for pf in range(n_pfs+1):
                # Find the data from just this profile
                df_this_pf = df[df['entry']==pf]
                # Get a list of clusters in this profile
                clstr_ids = np.unique(np.array(df_this_pf['cluster'].values))
                # Remove the noise points
                clstr_ids = clstr_ids[clstr_ids != -1]
                # Loop over every cluster in this profile
                for i in clstr_ids:
                    # Find the data from this cluster
                    df_this_pf_this_cluster = df_this_pf[df_this_pf['cluster']==i]
                    # Find the mean of this var for this cluster for this profile
                    pf_clstr_mean = np.mean(df_this_pf_this_cluster[var].values)
                    # Put that value back into the original dataframe
                    #   Need to make a mask first for some reason
                    this_pf_this_cluster = (df['entry']==pf) & (df['cluster']==i)
                    df.loc[this_pf_this_cluster, this_var] = pf_clstr_mean
        if prefix == 'cmc':
            # Calculate the cluster mean-centered version of the variable
            #   Should not change the number of points to display
            # Loop over each cluster
            for i in range(n_clusters+1):
                # Find the data from this cluster
                df_this_cluster = df[df['cluster']==i].copy()
                # Find the mean of this var for this cluster
                clstr_mean = np.mean(df_this_cluster[var].values)
                # Calculate normalized values
                df_this_cluster[this_var] = df_this_cluster[var] - clstr_mean
                # Put those values back into the original dataframe
                df.loc[df['cluster']==i, this_var] = df_this_cluster[this_var]
        if prefix == 'ca':
            # Calculate the cluster average version of the variable
            #   Reduces the number of points to just one per cluster
            # Loop over each cluster
            for i in range(n_clusters+1):
                # Find the data from this cluster
                df_this_cluster = df[df['cluster']==i].copy()
                # Find the mean of this var for this cluster
                clstr_mean = np.mean(df_this_cluster[var].values)
                # Put those values back into the original dataframe
                df.loc[df['cluster']==i, this_var] = clstr_mean
            #
        #
    #
    return df

################################################################################

def plot_clusters(ax, df, x_key, y_key, cl_x_var, cl_y_var, clr_map, min_cs, min_samp=None, box_and_whisker=True):
    """
    Plots the clusters found by HDBSCAN on the x-y plane

    ax              The axis on which to plot
    df              A pandas data frame output from HDBSCAN_
    x_key           String of the name of the column to use on the x-axis
    y_key           String of the name of the column to use on the y-axis
    clr_map         String of the name of the colormap to use (ex: 'clusters')
    min_cs          An integer, the minimum number of points for a cluster
    min_samp        An integer, number of points in neighborhood for a core point
    box_and_whisker True/False whether to include the box and whisker plot
    """
    # Decide whether to plot the centroid or not
    if x_key in pf_vars or y_key in pf_vars:
        plot_centroid = False
    else:
        plot_centroid = True
    # Run the HDBSCAN algorithm on the provided dataframe
    df, rel_val = HDBSCAN_(df, cl_x_var, cl_y_var, min_cs, min_samp=min_samp, extra_cl_vars=[x_key,y_key])
    # Clusters are labeled starting from 0, so total number of clusters is
    #   the largest label plus 1
    n_clusters  = df['cluster'].max()+1
    # Noise points are labeled as -1
    # Plot noise points first
    df_noise = df[df.cluster==-1]
    ax.scatter(df_noise[x_key], df_noise[y_key], color=std_clr, s=mrk_size, marker=std_marker, alpha=noise_alpha, zorder=1)
    n_noise_pts = len(df_noise)
    # Which colormap?
    if clr_map == 'cluster':
        # Loop through each cluster
        pts_per_cluster = []
        for i in range(n_clusters):
            # Decide on the color and symbol, don't go off the end of the arrays
            my_clr = mpl_clrs[i%len(mpl_clrs)]
            my_mkr = mpl_mrks[i%len(mpl_mrks)]
            # Get relevant data
            x_data = df[df.cluster == i][x_key]
            x_mean = np.mean(x_data)
            y_data = df[df.cluster == i][y_key]
            y_mean = np.mean(y_data)
            alphas = df[df.cluster == i]['clst_prob']
            # Plot the points for this cluster with the specified color, marker, and alpha value
            ax.scatter(x_data, y_data, color=my_clr, s=mrk_size, marker=my_mkr, alpha=alphas, zorder=5)
            # Plot the centroid(?) of this cluster
            if plot_centroid:
                ax.scatter(x_mean, y_mean, color='r', s=cent_mrk_size, marker=my_mkr, zorder=10)
            # ax.scatter(x_mean, y_mean, color='r', s=cent_mrk_size, marker=r"${}$".format(str(i)), zorder=10)
            # Record the number of points in this cluster
            pts_per_cluster.append(len(x_data))
        # Add legend to report the total number of points and notes on the data
        n_pts_patch   = mpl.patches.Patch(color='none', label=str(len(df[x_key]))+' points')
        min_pts_patch = mpl.patches.Patch(color='none', label='min(pts/cluster): '+str(min_cs))
        n_clstr_patch = mpl.lines.Line2D([],[],color='r', label=r'$n_{clusters}$: '+str(n_clusters), marker='*', linewidth=0)
        n_noise_patch = mpl.patches.Patch(color=std_clr, label=r'$n_{noise pts}$: '+str(n_noise_pts), alpha=noise_alpha, edgecolor=None)
        rel_val_patch = mpl.patches.Patch(color='none', label='DBCV: %.4f'%(rel_val))
        ax.legend(handles=[n_pts_patch, min_pts_patch, n_clstr_patch, n_noise_patch, rel_val_patch])
        # Add inset axis for box-and-whisker plot
        if box_and_whisker:
            inset_ax = inset_axes(ax, width="30%", height="10%", loc=4)
            inset_ax.boxplot(pts_per_cluster, vert=0, sym='X')
            #   Adjust the look of the inset axis
            inset_ax.xaxis.set_ticks_position('top')
            inset_ax.set_xticks([int(min(pts_per_cluster)),int(np.median(pts_per_cluster)),int(max(pts_per_cluster))])
            inset_ax.spines['left'].set_visible(False)
            inset_ax.get_yaxis().set_visible(False)
            inset_ax.spines['right'].set_visible(False)
            inset_ax.spines['bottom'].set_visible(False)
            inset_ax.set_xlabel('Points per cluster')
            inset_ax.xaxis.set_label_position('top')
        #
    #


################################################################################

def plot_n_clusters_per_n_prof(ax, df, x_key, y_key, n_pf_step, min_css, min_samps=[None]):
    """
    Plots the number of clusters found by HDBSCAN vs. the number of profiles
    included in the data set

    ax          The axis on which to plot
    df          A pandas data frame output from HDBSCAN_
    x_key       String of the name of the column to use on the x-axis
    y_key       String of the name of the column to use on the y-axis
    n_pf_step   An integer, the step between number of profiles to include
                    A larger step means fewer overall runs of HDBSCAN algorithm
    min_css     A list of integers, the minimum number of points for a cluster
    min_samp    An integer, number of points in neighborhood for a core point
    """
    # Get the total number of profiles in the given dataframe
    max_entries = int(max(df['entry']))
    for i in range(len(min_css)):
        for j in range(len(min_samps)):
            n_clusters_per_n_profs = []
            n_profs = []
            for k in range(2,max_entries,n_pf_step):
                temp_df = df[df['entry'] < k]
                # Run the HDBSCAN algorithm
                new_df, rel_val = HDBSCAN_(temp_df, x_key, y_key, min_css[i], min_samps[j])
                # Clusters are labeled starting from 0, so total number of clusters is
                #   the largest label plus 1
                n_clusters  = new_df['cluster'].max()+1
                # print('Number of clusters for ',i,'profiles:',n_clusters)
                n_clusters_per_n_profs.append(n_clusters)
                n_profs.append(k)
                #
            ax.plot(n_profs, n_clusters_per_n_profs, color=mpl_clrs[i%len(mpl_clrs)], linestyle=l_styles[j], label='min(pts/cluster): '+str(min_css[i]))
    ax.legend()

################################################################################

def plot_clstr_param_sweep(ax, df, x_key, y_key, x_param, y_param, xlabel, ylabel, x_tuple, z_param=None, z_list=[None]):
    """
    Plots the number of clusters found by HDBSCAN vs. the number of profiles
    included in the data set

    ax              The axis on which to plot
    df              A pandas data frame on which to run HDBSCAN_
    x_key           String of the name of the column to use on the x-axis when clustering
    y_key           String of the name of the column to use on the y-axis when clustering
    x_param         String of the name of clustering attribute on the x-axis in the output
    y_param         String of the name of clustering attribute on the y-axis in the output
    x_tuple         A tuple for the x_param with (start, stop, step) to define the x-axis
    z_param         String of the name of clustering attribute to plot one line for each
    z_list          A list of values of the z_param to plot one line for each
    """
    # If limiting the number of profiles, find the total number of profiles in the given dataframe
    if x_param == 'n_pfs' or z_param == 'n_pfs':
        max_entries = int(max(df['entry']))
    # Build the array for the x_param axis
    x_param_array = np.arange(x_tuple[0], x_tuple[1], x_tuple[2])
    print('x_param:',x_param)
    print('y_param:',y_param)
    print('xp_array:',x_param_array)
    # exit(0)
    j=0
    for i in range(len(z_list)):
        y_param_array = []
        twin_y_param_array = []
        for x in x_param_array:
            # Set input params
            min_cs = None
            min_samps = None
            if x_param == 'min_cs':
                # min cluster size must be an integer
                min_cs = int(x)
                xlabel = 'Minimum cluster size'
            elif x_param == 'min_samps':
                # min samples must be an integer
                min_samps = int(x)
                xlabel = 'Minimum samples'
            if z_param == 'min_cs':
                # min cluster size must be an integer
                min_cs = int(z_list[i])
                zlabel = 'Minimum cluster size: '+str(min_cs)
            elif z_param == 'min_samps':
                # min samps must be an integer, or None
                if not isinstance(z_list[i], type(None)):
                    min_samps = int(z_list[i])
                else:
                    min_samps = z_list[i]
                zlabel = 'Minimum samples: '+str(min_samps)
            else:
                zlabel = None
            # Run the HDBSCAN algorithm
            new_df, rel_val = HDBSCAN_(df, x_key, y_key, min_cs, min_samps)
            # Set output params
            #   Check whether to do dual vertical axes
            if not isinstance(y_param, list):
                twin_sweep = False
                y_p = y_param
            elif len(y_param) == 2:
                twin_sweep = True
                y_p = y_param[0]
                # Create the twin axis
                ax1 = ax.twinx()
                if y_param[1] == 'n_clusters':
                    # Clusters are labeled starting from 0, so total number of clusters is
                    #   the largest label plus 1
                    twin_y_param_array.append(new_df['cluster'].max()+1)
                    twin_ylabel = 'Number of clusters'
                elif y_param[1] == 'DBCV':
                    # relative_validity_ is a rough measure of DBCV
                    twin_y_param_array.append(rel_val)
                    twin_ylabel = 'DBCV (relative_validity_)'
                #
            else:
                print('Too many arguments in y_param:',y_param)
                exit(0)
            if y_p == 'n_clusters':
                # Clusters are labeled starting from 0, so total number of clusters is
                #   the largest label plus 1
                y_param_array.append(new_df['cluster'].max()+1)
                ylabel = 'Number of clusters'
            elif y_p == 'DBCV':
                # relative_validity_ is a rough measure of DBCV
                y_param_array.append(rel_val)
                ylabel = 'DBCV (relative_validity_)'
            #
        ax.plot(x_param_array, y_param_array, color=mpl_clrs[i%len(mpl_clrs)], linestyle=l_styles[j], label=zlabel)
        if twin_sweep:
            ax1.plot(x_param_array, twin_y_param_array, color=mpl_clrs[i%len(mpl_clrs)], linestyle=l_styles[1])
            ax1.set_ylabel(twin_ylabel)
            # ax1.tick_params(axis='y', colors='b')
    ax.legend()
    return xlabel, ylabel

################################################################################

def plot_clstr_outputs(ax, df, min_cs, rel_val, x_param, y_param, xlabel=None, ylabel=None, z_param=None, z_list=[None], plot_slopes=False):
    """
    Plots some outputs of the HDBSCAN algorithm

    ax              The axis on which to plot
    df              A pandas data frame output from HDBSCAN_
    min_cs          Minimum points per cluster used in HDBSCAN_
    rel_val         The `relative_validity_` value from the output from HDBSCAN_
    x_param         String of the name of clustering attribute on the x-axis in the output
    y_param         String of the name of clustering attribute on the y-axis in the output
    z_param         String of the name of clustering attribute to plot one line for each
    z_list          A list of values of the z_param to plot one line for each
    plot_slopes     Boolean True/False whether to plot the trend lines of each cluster
    """
    print('From plot_clstr_outputs,')
    print('\tTotal points:',len(df))
    print('\trel_val:',rel_val)
    print('\tdf vars:',df.columns)
    # Create blank arrays to fill
    x_param_array = []
    y_param_array = []
    y_param_spans = []
    # Get the array of unique cluster labels, minus the noise
    clstr_array = np.unique(np.array(df[df['cluster'] != -1]['cluster']))
    # print('clstr_array:',clstr_array)
    if y_param != 'n_clusters':
        for i in range(len(clstr_array)):
            x_param_array.append([])
            y_param_array.append([])
            y_param_spans.append([])
        #
    #
    # Reformat dates so the ticks on the axis make sense
    if x_param == 'dt_start':
        df[x_param] = mpl.dates.date2num(df[x_param])
        use_dist = False
    # Calculate distances between profiles
    elif x_param == 'distance':
        # Set xlabel
        xlabel = 'Along-path distance (km)'
        # Reset x_param to `entry` so that it sorts profiles correctly
        x_param = 'entry'
        # Set the distance switch to True
        use_dist = True
        along_path_dist = 0
    else:
        use_dist = False
    # If the x_param is one listed here, loop over each profile
    if x_param in ['prof_no', 'entry', 'dt_start']:
        # Find the number of values of x_param and y_param
        xps = np.unique(np.array(df[x_param].values))
        n_xps = len(xps)
        ycs = np.unique(np.array(df['cluster'].values))
        # delete the noise point index [-1]
        ycs = ycs[ycs != -1]
        n_ycs = len(ycs)
        # Create blank arrays to fill with n_ycs rows, n_xps columns
        #   Need to use NaN instead of None so the error bars will work
        x_param_array = np.full((n_ycs,n_xps), float('NaN'))
        y_param_array = np.full((n_ycs,n_xps), float('NaN'))
        y_param_spans = np.full((n_ycs,n_xps), float('NaN'))
        # print('shape of y_param_array:',y_param_array.shape)
        if use_dist:
            df_first_pf = df[df[x_param] == min(xps)]
            past_lat_lon = (df_first_pf['lat'].values[0], df_first_pf['lon'].values[0])
        for ix in range(len(xps)):
            # Get just the dataframe for this profile
            df_this_pf = df[df[x_param] == xps[ix]]
            if use_dist:
                new_lat_lon = (df_this_pf['lat'].values[0], df_this_pf['lon'].values[0])
                along_path_dist += geodesic(past_lat_lon, new_lat_lon).km
                past_lat_lon = new_lat_lon
                pf = along_path_dist
            # Get the y_param for this profile
            if y_param == 'n_clusters':
                # Find the number of clusters identified in this profile
                n_clust_this_pf = len(np.unique(np.array(df_this_pf['cluster'])))-1
                # Record values
                x_param_array[0][ix] = pf
                y_param_array[0][ix] = n_clust_this_pf
                ylabel = 'Number of clusters'
            else:
                # Loop over each cluster
                for iy in range(len(ycs)): #np.unique(np.array(df_this_pf['cluster'])):
                    clstr = ycs[iy]
                    # Get just the dataframe for this cluster in this profile
                    df_this_pf_this_cluster = df_this_pf[df_this_pf['cluster']==clstr]
                    this_pf_this_clstr_values = df_this_pf_this_cluster[y_param].values
                    if len(this_pf_this_clstr_values) > 0:
                        # Find the average pressure for this cluster in this profile
                        clstr_avg_y_param = np.mean(this_pf_this_clstr_values)
                        # Find the span of pressures for this cluster in this profile
                        clstr_y_param_span = 0.5*(max(this_pf_this_clstr_values)-min(this_pf_this_clstr_values))
                        # Record values
                        x_param_array[iy][ix] = pf
                        y_param_array[iy][ix] = clstr_avg_y_param
                        y_param_spans[iy][ix] = clstr_y_param_span
                    #
                # end loop over clusters
            #
        # end loop over profiles
        if len(y_param_array) == 1:
            this_plt = ax.scatter(x_param_array, y_param_array, color=std_clr, s=layer_mrk_size, marker=std_marker)
        else:
            # Make empty list for normalized variations from the mean
            vars_from_mean = []
            # Loop over each cluster
            for i in range(n_ycs):
                # Decide on the color and symbol, don't go off the end of the arrays
                my_clr = mpl_clrs[i%len(mpl_clrs)]
                my_mkr = mpl_mrks[i%len(mpl_mrks)]
                # Plot this cluster
                this_plt = ax.scatter(x_param_array[i], y_param_array[i], color=my_clr, s=layer_mrk_size, marker=my_mkr, alpha=0.5, label=str(i))
                # this_plt = ax.scatter(x_param_array[i], y_param_array[i], color=my_clr, s=cent_mrk_size, marker=r"${}$".format(str(i)), alpha=0.5, label=str(i))
                ax.errorbar(x_param_array[i], y_param_array[i], y_param_spans[i], color=my_clr, capsize=l_cap_size, linestyle='none', alpha=0.5)
                # Format the ticks on the x-axis if using datetime
                if x_param == 'dt_start':
                    loc = mpl.dates.AutoDateLocator()
                    ax.xaxis.set_major_locator(loc)
                    ax.xaxis.set_major_formatter(mpl.dates.ConciseDateFormatter(loc))
                # Calculate the average variation from the mean for this cluster
                # vfm = np.mean(abs(y_param_array[i] - np.mean(y_param_array[i])))
                # Normalize that variation by the standard deviation and record it
                # vars_from_mean.append(vfm/np.std(y_param_array[i]))
            # Add the average normalized variation from the mean to the legend
            # nvfm_patch = mpl.patches.Patch(color='none', label='ANVFM:%.3E'%(np.mean(vars_from_mean)))
            # ax.legend(handles=[nvfm_patch])
            # ax.legend()
            ax.invert_yaxis()
            #
        #
        return xlabel, ylabel
    # If x_param is one listed here, loop over each cluster
    elif x_param in ['iT','CT','SP','SA','aiT','aCT','BSP','BSA']:
        # Clusters are labeled starting from 0, so total number of clusters is
        #   the largest label plus 1
        n_clusters  = df['cluster'].max()+1
        # Plot noise points first
        df_noise = df[df.cluster==-1]
        ax.scatter(df_noise[x_param], df_noise[y_param], color=std_clr, s=mrk_size, marker=std_marker, alpha=noise_alpha, zorder=1)
        n_noise_pts = len(df_noise)
        for i in range(len(clstr_array)):
            # Decide on the color and symbol, don't go off the end of the arrays
            my_clr = mpl_clrs[i%len(mpl_clrs)]
            my_mkr = mpl_mrks[i%len(mpl_mrks)]
            # Get relevant data
            x_data = df[df.cluster == i][x_param]
            x_mean = np.mean(x_data)
            y_data = df[df.cluster == i][y_param]
            y_mean = np.mean(y_data)
            alphas = df[df.cluster == i]['clst_prob']
            # Plot the points for this cluster with the specified color, marker, and alpha value
            # ax.scatter(x_data, y_data, color=my_clr, s=mrk_size, marker=my_mkr, alpha=alphas, zorder=5)
            ax.scatter(x_data, y_data, color=my_clr, s=mrk_size, marker=my_mkr, alpha=noise_alpha, zorder=5)
            # Plot the centroid(?) of this cluster
            ax.scatter(x_mean, y_mean, color='r', s=cent_mrk_size, marker=my_mkr, zorder=10)
            # ax.scatter(x_mean, y_mean, color='r', s=cent_mrk_size, marker=r"${}$".format(str(i)), zorder=10)
            # Plot the trend lines of each cluster if specified
            if plot_slopes:
                # Find the slope of the least-squares of the points for this cluster
                m, c = np.linalg.lstsq(np.array([x_data, np.ones(len(x_data))]).T, y_data, rcond=None)[0]
                # Plot the least-squares fit line for this cluster through the centroid
                ax.axline((x_mean, y_mean), slope=m, color=my_clr, zorder=3)
                # Add annotation to say what the slope is
                ax.annotate('%.2f'%(1/m), xy=(x_mean,y_mean), xycoords='data', color=my_clr)
        # Add legend to report the total number of points and notes on the data
        n_pts_patch   = mpl.patches.Patch(color='none', label=str(len(df[x_param]))+' points')
        min_pts_patch = mpl.patches.Patch(color='none', label='min(pts/cluster): '+str(min_cs))
        n_clstr_patch = mpl.lines.Line2D([],[],color='r', label=r'$n_{clusters}$: '+str(n_clusters), marker='*', linewidth=0)
        n_noise_patch = mpl.patches.Patch(color=std_clr, label=r'$n_{noise pts}$: '+str(n_noise_pts), alpha=noise_alpha, edgecolor=None)
        rel_val_patch = mpl.patches.Patch(color='none', label='DBCV: %.4f'%(rel_val))
        if y_param == 'la_CT':
            ax.legend(handles=[n_pts_patch, min_pts_patch, n_clstr_patch, n_noise_patch, rel_val_patch])
        #
        return xlabel, ylabel
    # If x_param is one listed here, loop over each cluster
    elif x_param == 'TS_slope':
        x_key = 'CT'
        y_key = 'SP'
        xlabel = r'Lateral density ratio $R_L$'
        for i in range(max(clstr_array)):
            # Decide on the color and symbol, don't go off the end of the arrays
            my_clr = mpl_clrs[i%len(mpl_clrs)]
            my_mkr = mpl_mrks[i%len(mpl_mrks)]
            # Get relevant data
            x_data = df[df.cluster == i][x_key]
            y_data = df[df.cluster == i][y_key]
            y_param_data = df[df.cluster == i][y_param]
            y_param_mean = np.mean(y_param_data)
            if y_param == 'press':
                y_param_mean = -1*y_param_mean
            # Get mean values of alpha and beta for this cluster
            alpha_data = df[df.cluster == i]['alpha']
            beta_data  = df[df.cluster == i]['beta']
            alpha = np.mean(alpha_data)
            beta  = np.mean(beta_data)
            # Find the slope of the least-squares of the points for this cluster
            m, c = np.linalg.lstsq(np.array([x_data, np.ones(len(x_data))]).T, y_data, rcond=None)[0]
            # Calculate the lateral density ratio
            R_L = (beta/alpha)*m
            # Plot the ST slope vs the y_param_mean
            ax.scatter(R_L, y_param_mean, color=my_clr, s=pf_mrk_size, marker=my_mkr, zorder=10)
        #
        # Plot a vertical line across zero slope
        ax.axvline(0, alpha=noise_alpha, zorder=1)
        return xlabel, ylabel
    # Make histogram by subtracting the mean of the variable for each cluster
    elif x_param == 'hist':
        # Add column in dataset for normalized values
        mc_y_param = 'mean centered '+y_param
        df[mc_y_param] = None
        # Loop across each cluster
        for i in range(max(clstr_array)):
            clstr = clstr_array[i]
            # Get just the dataframe for that cluster
            df_this_cluster = df[df['cluster']==clstr]
            # Find the average for the parameter for this cluster
            clstr_mean = np.mean(df_this_cluster[y_param].values)
            # Calculate normalized values
            df_this_cluster[mc_y_param] = df_this_cluster[y_param] - clstr_mean
            # Put those values back into the original dataframe
            df.loc[df['cluster']==clstr, mc_y_param] = df_this_cluster[mc_y_param]
            # clstr_mean = np.mean(df[df['cluster']==clstr][mc_y_param].values)
            # print('clstr_mean:',clstr_mean)
        # Get histogram parameters
        x_var, res_bins, median, mean, std_dev = get_hist_params(df, mc_y_param)
        # Plot the histogram
        ax.hist(x_var, bins=res_bins, color=std_clr, orientation='horizontal')
        # Add legend to report overall statistics
        n_pts_patch   = mpl.patches.Patch(color='none', label=str(len(x_var))+' points')
        median_patch  = mpl.patches.Patch(color='none', label='Median:  '+'%.4f'%median)
        mean_patch    = mpl.patches.Patch(color='none', label='Mean:    ' + '%.4f'%mean)
        std_dev_patch = mpl.patches.Patch(color='none', label='Std dev: '+'%.4f'%std_dev)
        notes_string = ''.join(df.notes.unique())
        # Only add the notes_string if it contains something
        if len(notes_string) > 1:
            notes_patch  = mpl.patches.Patch(color='none', label=notes_string)
            ax.legend(handles=[n_pts_patch, median_patch, mean_patch, std_dev_patch, notes_patch])
        else:
            ax.legend(handles=[n_pts_patch, median_patch, mean_patch, std_dev_patch])
        return 'Number of points', ylabel+' (mean centered by cluster)'
    else:
        print('Given x_param:',x_param,'is not valid')
        exit(0)
    j=0
    for i in range(len(z_list)):
        y_param_array = []
        twin_y_param_array = []
        for x in x_param_array:
            # Set input params
            min_cs = None
            min_samps = None
            if x_param == 'min_cs':
                # min cluster size must be an integer
                min_cs = int(x)
                xlabel = 'Minimum cluster size'
            elif x_param == 'min_samps':
                # min samples must be an integer
                min_samps = int(x)
                xlabel = 'Minimum samples'
            if z_param == 'min_cs':
                # min cluster size must be an integer
                min_cs = int(z_list[i])
                zlabel = 'Minimum cluster size: '+str(min_cs)
            elif z_param == 'min_samps':
                # min samps must be an integer, or None
                if not isinstance(z_list[i], type(None)):
                    min_samps = int(z_list[i])
                else:
                    min_samps = z_list[i]
                zlabel = 'Minimum samples: '+str(min_samps)
            else:
                zlabel = None
            # Run the HDBSCAN algorithm
            new_df, rel_val = HDBSCAN_(df, x_key, y_key, min_cs, min_samps)
            # Set output params
            #   Check whether to do dual vertical axes
            if not isinstance(y_param, list):
                twin_sweep = False
                y_p = y_param
            elif len(y_param) == 2:
                twin_sweep = True
                y_p = y_param[0]
                # Create the twin axis
                ax1 = ax.twinx()
                if y_param[1] == 'n_clusters':
                    # Clusters are labeled starting from 0, so total number of clusters is
                    #   the largest label plus 1
                    twin_y_param_array.append(new_df['cluster'].max()+1)
                    twin_ylabel = 'Number of clusters'
                elif y_param[1] == 'DBCV':
                    # relative_validity_ is a rough measure of DBCV
                    twin_y_param_array.append(rel_val)
                    twin_ylabel = 'DBCV (relative_validity_)'
                #
            else:
                print('Too many arguments in y_param:',y_param)
                exit(0)
            if y_p == 'n_clusters':
                # Clusters are labeled starting from 0, so total number of clusters is
                #   the largest label plus 1
                y_param_array.append(new_df['cluster'].max()+1)
                ylabel = 'Number of clusters'
            elif y_p == 'DBCV':
                # relative_validity_ is a rough measure of DBCV
                y_param_array.append(rel_val)
                ylabel = 'DBCV (relative_validity_)'
            #
        ax.plot(x_param_array, y_param_array, color=mpl_clrs[i%len(mpl_clrs)], linestyle=l_styles[j], label=zlabel)
        if twin_sweep:
            ax1.plot(x_param_array, twin_y_param_array, color=mpl_clrs[i%len(mpl_clrs)], linestyle=l_styles[1])
            ax1.set_ylabel(twin_ylabel)
            # ax1.tick_params(axis='y', colors='b')
    ax.legend()
    return xlabel, ylabel

################################################################################
