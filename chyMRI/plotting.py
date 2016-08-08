import os
import nibabel
from nilearn import image, plotting
import pandas as pd
import numpy as np
from nilearn.input_data import NiftiLabelsMasker
import nipype.interfaces.io as nio

import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
plt.style.use('ggplot')

def plot_timecourses(parcellation="/home/chymera/NIdata/templates/roi/ds_QBI_vze_chr.nii.gz", condition=["ERC_ofM"], subject=["5502"], scan_type=["EPI_CBV_alej"]):
	datasource = nio.DataGrabber(infields=["condition","subject","scan_type"], outfields=["nii_data", "delay_file", "stimulation_file"], sort_filelist = True)
	datasource.inputs.base_directory = "/home/chymera/NIdata/ofM.erc/level1"
	datasource.inputs.template = '*'
	datasource.inputs.field_template = dict(
		nii_data='bruker_preprocessing/_condition_%s_subject_%s/_scan_type_%s/functional_bandpass/*.nii.gz',
		delay_file='bruker_preprocessing/_condition_%s_subject_%s/_scan_type_%s/timing_metadata/_report/report.rst',
		stimulation_file='first_level/_condition_%s_subject_%s/_scan_type_%s/specify_model/_report/report.rst'
		)
	datasource.inputs.template_args = dict(
		nii_data=[
			['condition','subject','scan_type']
			],
		delay_file=[
			['condition','subject','scan_type']
			],
		stimulation_file=[
			['condition','subject','scan_type']
			]
		)
	datasource.inputs.condition = ['ERC_ofM']
	datasource.inputs.subject = ['5502']
	datasource.inputs.scan_type = ['EPI_CBV_alej']

	results = datasource.run()
	nii_data = results.outputs.stimulation_file
	print nii_data

	masker = NiftiLabelsMasker(labels_img=parcellation, standardize=True, memory='nilearn_cache', verbose=5)

	time_series = masker.fit_transform("/home/chymera/NIdata/ofM.erc/level1/bruker_preprocessing/_condition_ERC_ofM_subject_5502/_scan_type_EPI_CBV_alej/functional_bandpass/corr_7_trans_filt.nii.gz").T

	region_assignments = pd.read_csv("/home/chymera/NIdata/templates/roi/QBI_vze_chr.csv", index_col=["ID"])

	for i in [10,11]:
		plt.plot(time_series[i], label=region_assignments.get_value(i, "acronym"))
	plt.legend()

def plot_stat_map(stat_map="/home/chymera/NIdata/ofM.dr/level2_3s/_category_multi_ofM_cF2/flameo/mapflow/_flameo0/stats/tstat1.nii.gz" ,template="/home/chymera/NIdata/templates/medres_QBI_chr.nii.gz", cbv=True, cut_coords=None, black_bg=False, annotate=True, title=None, threshold=2.5, scale=1, draw_cross=True):
	"""Wrapper for the nilearn.plotting.plot_stat_map, provides better control over element scaling and uses a prettier default style

	Keyword Arguments:
	scale -- allows intelligent scaling of annotation, crosshairs, and title
	"""

	colors_plus = plt.cm.autumn(np.linspace(0., 1, 128))
	colors_minus = plt.cm.winter(np.linspace(0, 1, 128))

	if cbv:
		colors = np.vstack((colors_plus, colors_minus[::-1]))
	else:
		colors = np.vstack((colors_minus, colors_plus[::-1]))
	mymap = mcolors.LinearSegmentedColormap.from_list('my_colormap', colors)

	fig = plt.figure(figsize=(14,5), facecolor='#eeeeee')

	display = plotting.plot_stat_map(stat_map, bg_img=template,threshold=threshold, figure=fig, black_bg=black_bg, vmax=40, cmap=mymap, cut_coords=cut_coords, annotate=False, title=None, draw_cross=False, interpolation="hermite")
	if draw_cross:
		display.draw_cross(linewidth=scale*1.6, alpha=0.4)
	if annotate:
		display.annotate(size=2+scale*18)
	if title:
		display.title(title, size=2+scale*26)

	return display

def plot_myanat(anat="/home/chymera/NIdata/templates/hires_QBI_chr.nii.gz"):
	plotting.plot_anat(anat, cut_coords=[0, 0, 0],title='Anatomy image')

def plot_nii(file_path, slices):
	plotting.plot_anat(file_path, cut_coords=slices, display_mode="y", annotate=False, draw_cross=False)

# def plot_timecourse(file_path, roi_path=None, roi_number=None):

def plot_fsl_design(file_path):
	df = pd.read_csv(file_path, skiprows=5, sep="\t", header=None, names=[1,2,3,4,5,6], index_col=False)
	print(df)
	df.plot()

def plot_stim_design(file_path,stim):
	if isinstance(stim,str):
		from nipype.interfaces.base import Bunch
		match_string='* output : '
		with open(stim) as subject_info_report:
			for line in subject_info_report:
				if line[:11] == match_string:
					_, bunch_string = line.split(match_string)
					bunch=eval(bunch_string[1:-2])
					break
		durations=bunch.durations
		onsets=bunch.onsets
	elif isinstance(stim,dict):
		durations = stim["durations"]
		onsets = stim["onsets"]

	df = pd.read_csv(file_path, skiprows=5, sep="\t", header=None, names=[1,2,3,4,5,6], index_col=False)
	fig, ax = plt.subplots(figsize=(6,4) , facecolor='#eeeeee', tight_layout=True)
	for d, o in zip(durations, onsets):
		d = int(d[0])
		o = int(o[0])
		ax.axvspan(o,o+d, facecolor="cyan", alpha=0.15)
		plt.hold(True)
	ax = df.plot(ax=ax)
	#remove bottom and top small tick lines
	plt.tick_params(axis='x', which='both', bottom='off', top='off', left='off', right='off')
	plt.tick_params(axis='y', which='both', bottom='off', top='off', left='off', right='off')

if __name__ == '__main__':
	# plot_nii("/home/chymera/FSL_GLM_work/GLM/_measurement_id_20151103_213035_4001_1_1/functional_cutoff/6_restore_maths.nii.gz", (-50,20))
	# plot_fsl_design("/home/chymera/NIdata/ofM.dr/level1/first_level/_condition_ofM_subject_4001/modelgen/run0.mat")
	# stim = {"durations":[[20.0], [20.0], [20.0], [20.0], [20.0], [20.0]], "onsets":[[172.44299999999998], [352.443], [532.443], [712.443], [892.443], [1072.443]]}
	# plot_stim_design("/home/chymera/level1/first_level/_condition_ERC_ofM_subject_5503/_scan_type_T2_TurboRARE/_scan_type_EPI_CBV_alej/modelgen/run0.mat",stim)
	# plot_stim_design(
		# "/home/chymera/run0_dg.mat",
		# "/home/chymera/report_dg.rst"
		# )
	# plot_stat_map(stat_map="/home/chymera/cluster/othresh.nii.gz")
	# plot_stat_map(stat_map="/home/chymera/NIdata/ofM.dr/GLM/level2_dgamma/_category_multi_ofM/flameo/mapflow/_flameo0/stats/tstat1.nii.gz", cbv=True, cut_coords=(-50,8,45))
	plot_stat_map(stat_map="/home/chymera/NIdata/ofM.erc/GLM/level2_ext_gamma/_scan_type_multi_EPI_CBV_alej/flameo/mapflow/_flameo0/stats/tstat1.nii.gz", cbv=True)
	# plot_stat_map(template="/home/chymera/NIdata/templates/QBI_chr.nii.gz",cut_coords=(-50,8,45))
	# plot_myanat()
	# plot_timecourses()
	plt.show()
