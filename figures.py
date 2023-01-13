"""
Author: Mikhail Schee
Created: 2022-08-18

This script is set up to make figures of Arctic Ocean profile data that has been
formatted into netcdfs by the `make_netcdf` function.

"""

# For custom analysis functions
import analysis_helper_functions as ahf

# Common filters
staircase_range = [185,300]

### Filters for reproducing plots from Timmermans et al. 2008
# Timmermans 2008 Figure 4 depth range
T2008_fig4_y_lims = {'y_lims':[260,220]}
# Timmermans 2008 Figure 4 shows profile 185
T2008_fig4_pfs = [183, 185, 187]
# Filters used in Timmermans 2008 T-S and aT-BS plots
T2008_p_range = [180,300]
T2008_S_range = [34.4,34.6]
T2008_fig5a_ax_lims = {'x_lims':[34.05,34.75], 'y_lims':[-1.3,0.5]}
T2008_fig6a_ax_lims = {'x_lims':[0.027,0.027045], 'y_lims':[-13e-6,3e-6]}
# The actual limits are above, but need to adjust the x lims for some reason
T2008_fig6a_ax_lims = {'x_lims':[0.026835,0.026880], 'y_lims':[-13e-6,3e-6]}

################################################################################
# Make dictionaries for what data to load in and analyze
################################################################################

# All profiles from certain ITPs
ITP2_all = {'ITP_2':'all'}

# Just specific profiles
ITP2_pfs = {'ITP_2':T2008_fig4_pfs}

################################################################################
# Create data filtering objects
print('- Creating data filtering objects')
################################################################################

dfs0 = ahf.Data_Filters()

################################################################################
# Create data sets by combining filters and the data to load in
print('- Creating data sets')
################################################################################

ds_ITP2_all = ahf.Data_Set(ITP2_all, dfs0)
ds_ITP2_pfs = ahf.Data_Set(ITP2_pfs, dfs0)

################################################################################
# Create profile filtering objects
print('- Creating profile filtering objects')
################################################################################

pfs_f0 = ahf.Profile_Filters()
pfs_f1 = ahf.Profile_Filters(p_range=staircase_range, m_avg_win=50)

################################################################################
# Create plotting parameter objects

print('- Creating plotting parameter objects')
################################################################################

### Test plots
pp_xy_default = ahf.Plot_Parameters()
pp_test0 = ahf.Plot_Parameters(x_vars=['SP'], y_vars=['iT'], clr_map='cluster', legend=False, extra_args={'b_a_w_plt':False, 'cl_x_var':'SP', 'cl_y_var':'la_iT', 'min_cs':90})
# pp_test = ahf.Plot_Parameters(x_vars=['iT', 'la_iT'], y_vars=['press'], plot_type='profiles', clr_map='clr_all_same')
# pp_test = ahf.Plot_Parameters(x_vars=['SP'], y_vars=['la_iT'], clr_map='cluster', extra_args={'cl_x_var':'SP', 'cl_y_var':'la_iT', 'min_cs':200})

### Figures for paper
## Parameter sweeps
pp_ps_min_cs = ahf.Plot_Parameters(x_vars=['min_cs'], y_vars=['n_clusters','DBCV'], clr_map='clr_all_same', extra_args={'cl_x_var':'SP', 'cl_y_var':'la_iT', 'min_cs':90, 'cl_ps_tuple':[20,210,10], 'z_var':'maw_size', 'z_list':[50,70,140]})
pp_ps_l_maw  = ahf.Plot_Parameters(x_vars=['maw_size'], y_vars=['n_clusters','DBCV'], clr_map='clr_all_same', extra_args={'cl_x_var':'SP', 'cl_y_var':'la_iT', 'min_cs':90, 'cl_ps_tuple':[10,210,10], 'z_var':'min_cs', 'z_list':[90,120,240]})
pp_ps_n_pfs  = ahf.Plot_Parameters(x_vars=['n_pfs'], y_vars=['n_clusters','DBCV'], clr_map='clr_all_same', extra_args={'cl_x_var':'SP', 'cl_y_var':'la_iT', 'min_cs':90, 'cl_ps_tuple':[10,410,10], 'z_var':'min_cs', 'z_list':[90,120,240]})

## Reproducing figures from Timmermans et al. 2008
## The actual clustering done for reproducing figures from Timmermans et al. 2008
pp_T2008_clstr = ahf.Plot_Parameters(x_vars=['SP'], y_vars=['la_CT'], clr_map='cluster', extra_args={'b_a_w_plt':True, 'cl_x_var':'SP', 'cl_y_var':'la_CT', 'min_cs':90})
## Reproducing Timmermans et al. 2008 Figure 4, with cluster coloring and 2 extra profiles
pp_T2008_fig4  = ahf.Plot_Parameters(x_vars=['SP'], y_vars=['press'], plot_type='profiles', clr_map='cluster', extra_args={'pfs_to_plot':T2008_fig4_pfs, 'cl_x_var':'SP', 'cl_y_var':'la_CT', 'min_cs':90}, ax_lims=T2008_fig4_y_lims)
## Reproducing Timmermans et al. 2008 Figure 5a, but with cluster coloring
pp_T2008_fig5a = ahf.Plot_Parameters(x_vars=['SP'], y_vars=['CT'], clr_map='cluster', extra_args={'b_a_w_plt':False, 'cl_x_var':'SP', 'cl_y_var':'la_CT', 'min_cs':90}, ax_lims=T2008_fig5a_ax_lims, legend=False)
## Reproducing Timmermans et al. 2008 Figure 6a, but with cluster coloring
pp_T2008_fig6a = ahf.Plot_Parameters(x_vars=['BSP'], y_vars=['aCT'], clr_map='cluster', extra_args={'b_a_w_plt':False, 'plot_slopes':True, 'cl_x_var':'SP', 'cl_y_var':'la_CT', 'min_cs':90}, ax_lims=T2008_fig6a_ax_lims, legend=False)

## Tracking clusters across profiles, reproducing Lu et al. 2022 Figure 3
pp_Lu2022_fig3a = ahf.Plot_Parameters(x_vars=['dt_start'], y_vars=['pca_press'], clr_map='cluster', extra_args={'b_a_w_plt':False, 'cl_x_var':'SP', 'cl_y_var':'la_CT', 'min_cs':90}, legend=False)
pp_Lu2022_fig3b = ahf.Plot_Parameters(x_vars=['dt_start'], y_vars=['pca_CT'], clr_map='cluster', extra_args={'b_a_w_plt':False, 'cl_x_var':'SP', 'cl_y_var':'la_CT', 'min_cs':90}, legend=False)
pp_Lu2022_fig3c = ahf.Plot_Parameters(x_vars=['dt_start'], y_vars=['pca_SP'], clr_map='cluster', extra_args={'b_a_w_plt':False, 'cl_x_var':'SP', 'cl_y_var':'la_CT', 'min_cs':90}, legend=False)
pp_Lu2022_fig3d = ahf.Plot_Parameters(x_vars=['dt_start'], y_vars=['pca_sigma'], clr_map='cluster', extra_args={'b_a_w_plt':False, 'cl_x_var':'SP', 'cl_y_var':'la_CT', 'min_cs':90}, legend=False)

## Histograms of data that's been mean centered by cluster
pp_cmc_press = ahf.Plot_Parameters(x_vars=['hist'], y_vars=['cmc_press'], extra_args={'cl_x_var':'SP', 'cl_y_var':'la_CT', 'min_cs':90, 'plt_hist_lines':True})
pp_cmc_sigma = ahf.Plot_Parameters(x_vars=['hist'], y_vars=['cmc_sigma'], extra_args={'cl_x_var':'SP', 'cl_y_var':'la_CT', 'min_cs':90, 'plt_hist_lines':True})
pp_cmc_temp  = ahf.Plot_Parameters(x_vars=['hist'], y_vars=['cmc_CT'], extra_args={'cl_x_var':'SP', 'cl_y_var':'la_CT', 'min_cs':90, 'plt_hist_lines':True})
pp_cmc_salt  = ahf.Plot_Parameters(x_vars=['hist'], y_vars=['cmc_SP'], extra_args={'cl_x_var':'SP', 'cl_y_var':'la_CT', 'min_cs':90, 'plt_hist_lines':True})

################################################################################
# Create analysis group objects
print('- Creating analysis group objects')
################################################################################

## Test Analysis Groups
# my_group0 = ahf.Analysis_Group(ds_ITP2_all, pfs_f1, pp_test0)
# my_group1 = ahf.Analysis_Group(ds_ITP2_all, pfs_f1, pp_test)
# my_group0 = ahf.Analysis_Group(ds_ITP2_pfs, pfs_f0, pp_test)
# my_group1 = ahf.Analysis_Group(ds_ITP2_pfs, pfs_f1, pp_test)

### Figures for paper
## Parameter sweeps
# group_ps_min_cs = ahf.Analysis_Group(ds_ITP2_all, pfs_f1, pp_ps_min_cs)
# group_ps_l_maw  = ahf.Analysis_Group(ds_ITP2_all, pfs_f1, pp_ps_l_maw)
# group_ps_n_pfs  = ahf.Analysis_Group(ds_ITP2_all, pfs_f1, pp_ps_n_pfs)
## Reproducing figures from Timmermans et al. 2008
# group_T2008_clstr = ahf.Analysis_Group(ds_ITP2_all, pfs_f1, pp_T2008_clstr)
# group_T2008_fig4  = ahf.Analysis_Group(ds_ITP2_all, pfs_f1, pp_T2008_fig4)
# group_T2008_fig5a = ahf.Analysis_Group(ds_ITP2_all, pfs_f1, pp_T2008_fig5a)
# group_T2008_fig6a = ahf.Analysis_Group(ds_ITP2_all, pfs_f1, pp_T2008_fig6a)
## Tracking clusters across profiles, reproducing Lu et al. 2022 Figure 3
# group_Lu2022_fig3a = ahf.Analysis_Group(ds_ITP2_all, pfs_f1, pp_Lu2022_fig3a)
# group_Lu2022_fig3b = ahf.Analysis_Group(ds_ITP2_all, pfs_f1, pp_Lu2022_fig3b)
# group_Lu2022_fig3c = ahf.Analysis_Group(ds_ITP2_all, pfs_f1, pp_Lu2022_fig3c)
# group_Lu2022_fig3d = ahf.Analysis_Group(ds_ITP2_all, pfs_f1, pp_Lu2022_fig3d)
## Histograms of data that's been mean centered by cluster
group_cmc_press = ahf.Analysis_Group(ds_ITP2_all, pfs_f1, pp_cmc_press)
# group_cmc_sigma = ahf.Analysis_Group(ds_ITP2_all, pfs_f1, pp_cmc_sigma)
# group_cmc_temp  = ahf.Analysis_Group(ds_ITP2_all, pfs_f1, pp_cmc_temp)
# group_cmc_salt  = ahf.Analysis_Group(ds_ITP2_all, pfs_f1, pp_cmc_salt)

################################################################################
# Declare figures or summaries to output
print('- Creating outputs')
################################################################################

# ahf.make_figure([my_group0])
# ahf.make_figure([my_group0, my_group1])

### Figures for paper
## Parameter sweeps
# ahf.make_figure([group_ps_min_cs, group_ps_l_maw, group_ps_n_pfs])
## Reproducing figures from Timmermans et al. 2008
# ahf.make_figure([group_T2008_clstr, group_T2008_fig4, group_T2008_fig5a, group_T2008_fig6a])
## Tracking clusters across profiles, reproducing Lu et al. 2022 Figure 3
# ahf.make_figure([group_Lu2022_fig3a, group_Lu2022_fig3d, group_Lu2022_fig3b, group_Lu2022_fig3c])
## Histograms of data that's been mean centered by cluster
ahf.make_figure([group_cmc_press])#, group_cmc_sigma, group_cmc_temp, group_cmc_salt])
