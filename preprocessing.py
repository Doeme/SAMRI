import nipype.interfaces.utility as util		# utility
import nipype.pipeline.engine as pe				# pypeline engine
from nipype.interfaces.fsl import GLM, MELODIC, FAST, BET, MeanImage, FLIRT, ApplyMask, ImageMaths, FSLCommand
from nipype.interfaces.nipy import SpaceTimeRealigner
from nipype.interfaces.afni import Bandpass
from nipype.interfaces.afni.base import AFNICommand
from nipype.interfaces.dcmstack import DcmStack
import nipype.interfaces.io as nio
from os import path
import nipype.interfaces.ants as ants
from extra_interfaces import DcmToNii, MEICA, VoxelResize, Bru2, FindScan, GetBrukerTiming
from extra_functions import get_data_selection
from nodes import ants_standard_registration_warp
from itertools import product
import pandas as pd

#set all outputs to compressed NIfTI
AFNICommand.set_default_output_type('NIFTI_GZ')
FSLCommand.set_default_output_type('NIFTI_GZ')

#relative paths
thisscriptspath = path.dirname(path.realpath(__file__))
scan_classification_file_path = path.join(thisscriptspath,"scan_type_classification.csv")

def get_scan(measurements_base, data_selection, condition, subject, scan_type):
	from os import path #for some reason the import outside the function fails
	scan_paths = []
	filtered_data = data_selection[(data_selection["condition"] == condition)&(data_selection["subject"] == subject)&(data_selection["scan_type"] == scan_type)]
	measurement_path = filtered_data["measurement"].tolist()[0]
	scan_subdir = filtered_data["scan"].tolist()[0]
	scan_path = path.join(measurements_base,measurement_path,scan_subdir)
	return scan_path

def dcm_preproc(workflow_base=".", force_convert=False, source_pattern="", IDs=""):
	# make IDs strings
	if "int" or "float" in str([type(ID) for ID in IDs]):
		IDs = [str(ID) for ID in IDs]

	#initiate the infosource node
	infosource = pe.Node(interface=util.IdentityInterface(fields=['subject_id']), name="subject_info_source")
	#define the list of subjects your pipeline should be executed on
	infosource.iterables = ('subject_id', IDs)

	#initiate the DataGrabber node with the infield: 'subject_id'
	#and the outfield: 'func' and 'struct'
	datasource = pe.Node(interface=nio.DataGrabber(infields=['subject_id'], outfields=['func', 'struct']), name='data_source')
	datasource.inputs.template = source_pattern
	#First way: define the arguments for the template '%s/%s.nii' for each field individual
	datasource.inputs.template_args['func'] = [['subject_id', 'EPI']]
	datasource.inputs.template_args['struct'] = [['subject_id','anatomical']]
	datasource.inputs.sort_filelist = True

	stacker = pe.Node(interface=DcmToNii(), name="stack_convert_functional")
	stacker.inputs.group_by = "EchoTime"

	struct_stacker = pe.Node(interface=DcmStack(), name="stack_convert_structural")

	voxelresize = pe.Node(interface=VoxelResize(), name="voxel_resize")
	voxelresize.inputs.resize_factor = 10

	meica = pe.Node(interface=MEICA(), name="multi_echo_ICA")
	meica.inputs.TR = 1.5
	meica.inputs.tpattern = "altminus"
	meica.inputs.cpus = 3

	workflow = pe.Workflow(name='Preprocessing')
	workflow.base_dir = workflow_base

	workflow.connect([
		(infosource, datasource, [('subject_id', 'subject_id')]),
		(datasource, stacker, [('func', 'dcm_dir')]),
		(stacker, voxelresize, [('nii_files', 'nii_files')]),
		(datasource, struct_stacker, [('struct', 'dicom_files')]),
		(stacker, meica, [('echo_times', 'echo_times')]),
		(voxelresize, meica, [('resized_files', 'echo_files')]),
		])

	workflow.write_graph(graph2use="orig")
	workflow.run(plugin="MultiProc")

def bru_preproc_lite(measurements_base, functional_scan_types=[], structural_scan_types=[], tr=1, conditions=[], subjects=[], exclude_subjects=[], include_measurements=[], exclude_measurements=[], actual_size=False, realign=False):

	#select all functional/sturctural scan types unless specified
	if not functional_scan_types or not structural_scan_types:
		 scan_classification = pd.read_csv(scan_classification_file_path)
		 if not functional_scan_types:
			 functional_scan_types = list(scan_classification[(scan_classification["categories"] == "functional")]["scan_type"])
		 if not structural_scan_types:
			 structural_scan_types = list(scan_classification[(scan_classification["categories"] == "structural")]["scan_type"])

	# define measurement directories to be processed, and populate the list either with the given include_measurements, or with an intelligent selection
	scan_types = functional_scan_types[:]
	scan_types.extend(structural_scan_types)
	data_selection=get_data_selection(measurements_base, conditions, scan_types=scan_types, subjects=subjects, exclude_subjects=exclude_subjects, include_measurements=include_measurements, exclude_measurements=exclude_measurements)
	if not subjects:
		subjects = set(list(data_selection["subject"]))
	if not conditions:
		conditions = set(list(data_selection["condition"]))

	infosource = pe.Node(interface=util.IdentityInterface(fields=['condition','subject']), name="infosource")
	infosource.iterables = [('condition',conditions), ('subject',subjects)]

	get_functional_scan = pe.Node(name='get_functional_scan', interface=util.Function(function=get_scan,input_names=["measurements_base","data_selection","condition","subject","scan_type"], output_names=['scan_path']))
	get_functional_scan.inputs.data_selection = data_selection
	get_functional_scan.inputs.measurements_base = measurements_base
	get_functional_scan.iterables = ("scan_type", functional_scan_types)

	functional_bru2nii = pe.Node(interface=Bru2(), name="functional_bru2nii")
	functional_bru2nii.inputs.actual_size=actual_size

	if structural_scan_types:
		get_structural_scan = pe.Node(name='get_structural_scan', interface=util.Function(function=get_scan,input_names=["measurements_base","data_selection","condition","subject","scan_type"], output_names=['scan_path']))
		get_structural_scan.inputs.data_selection = data_selection
		get_structural_scan.inputs.measurements_base = measurements_base
		get_structural_scan.iterables = ("scan_type", structural_scan_types)

		structural_bru2nii = pe.Node(interface=Bru2(), name="structural_bru2nii")
		structural_bru2nii.inputs.force_conversion=True
		structural_bru2nii.inputs.actual_size=actual_size

	realigner = pe.Node(interface=SpaceTimeRealigner(), name="realigner")
	realigner.inputs.slice_times = "asc_alt_2"
	realigner.inputs.tr = tr
	realigner.inputs.slice_info = 3 #3 for coronal slices (2 for horizontal, 1 for sagittal)

	workflow = pe.Workflow(name="PreprocessingLite")

	workflow_connections = [
		(infosource, get_functional_scan, [('condition', 'condition'),('subject', 'subject')]),
		(get_functional_scan, functional_bru2nii, [('scan_path', 'input_dir')]),
		]
	if realign:
		workflow_connections.extend([
			(functional_bru2nii, realigner, [('nii_file', 'in_file')]),
			])
	if structural_scan_types:
		workflow_connections.extend([
			(infosource, get_structural_scan, [('condition', 'condition'),('subject', 'subject')]),
			(get_structural_scan, structural_bru2nii, [('scan_path','input_dir')]),
			])

	workflow.connect(workflow_connections)
	# workflow.run(plugin="MultiProc")
	return workflow

def bru2_preproc2(measurements_base, functional_scan_type, structural_scan_type=None, tr=1, conditions=[], include_subjects=[], exclude_subjects=[], include_measurements=[], exclude_measurements=[], actual_size=False, workflow_denominator="Preprocessing", template="/home/chymera/NIdata/templates/ds_QBI_atlas100RD.nii", standalone_execute=False):
	measurements_base = path.expanduser(measurements_base)
	data_selection=get_data_selection(measurements_base, conditions, include_subjects=include_subjects, exclude_subjects=exclude_subjects, exclude_measurements=exclude_measurements)

	infosource = pe.Node(interface=util.IdentityInterface(fields=["condition","subject"]), name="infosource")
	infosource.iterables = [('condition', set(list(data_selection["condition"]))), ('subject', set(list(data_selection["subject"])))]

	def get_measurement(condition_id, subject_id, measurements_base, data_selection):
		measurement_path = data_selection[(data_selection["condition"] == condition_id)&(data_selection["subject"] == subject_id)]["measurement"]
		measurement_path = measurement_path.tolist()[0]
		measurement_path = measurements_base + "/" + measurement_path
		return measurement_path

	getmeasurement = pe.Node(name='getmeasurement', interface=util.Function(function=get_measurement, input_names=["condition_id","subject_id","measurements_base","data_selection"], output_names=['measurement_path']))
	getmeasurement.inputs.data_selection = data_selection
	getmeasurement.inputs.measurements_base = measurements_base

	functional_scan_finder = pe.Node(interface=FindScan(), name="functional_scan_finder")
	functional_scan_finder.inputs.query = functional_scan_type
	functional_scan_finder.inputs.query_file = "visu_pars"

	timing_metadata = pe.Node(interface=GetBrukerTiming(), name="timing_metadata")

	if structural_scan_type:
		structural_scan_finder = pe.Node(interface=FindScan(), name="structural_scan_finder")
		structural_scan_finder.inputs.query = structural_scan_type
		structural_scan_finder.inputs.query_file = "visu_pars"
		structural_bru2nii = pe.Node(interface=Bru2(), name="structural_bru2nii")
		structural_bru2nii.inputs.force_conversion=True
		structural_bru2nii.inputs.actual_size=actual_size

		structural_FAST = pe.Node(interface=FAST(), name="structural_FAST")
		structural_FAST.inputs.segments = False
		structural_FAST.inputs.output_biascorrected = True
		structural_FAST.inputs.bias_iters = 8

		structural_cutoff = pe.Node(interface=ImageMaths(), name="structural_cutoff")
		structural_cutoff.inputs.op_string = "-thrP 45"
		structural_registration, structural_warp = ants_standard_registration_warp(template, "structural_registration", "structural_warp")

	functional_bru2nii = pe.Node(interface=Bru2(), name="functional_bru2nii")
	functional_bru2nii.inputs.actual_size=actual_size

	realigner = pe.Node(interface=SpaceTimeRealigner(), name="realigner")
	realigner.inputs.slice_times = "asc_alt_2"
	realigner.inputs.tr = tr
	realigner.inputs.slice_info = 3 #3 for coronal slices (2 for horizontal, 1 for sagittal)

	temporal_mean = pe.Node(interface=MeanImage(), name="temporal_mean")
	functional_masker = pe.Node(interface=ApplyMask(), name="functional_masker")

	structural_BET = pe.Node(interface=BET(), name="structural_BET")
	structural_BET.inputs.mask = True
	structural_BET.inputs.frac = 0.5

	functional_registration, functional_warp = ants_standard_registration_warp(template, "functional_registration", "functional_warp")

	functional_FAST = pe.Node(interface=FAST(), name="functional_FAST")
	functional_FAST.inputs.segments = False
	functional_FAST.inputs.output_biascorrected = True
	functional_FAST.inputs.bias_iters = 8

	functional_cutoff = pe.Node(interface=ImageMaths(), name="functional_cutoff")
	functional_cutoff.inputs.op_string = "-thrP 45"

	functional_BET = pe.Node(interface=BET(), name="functional_BET")
	functional_BET.inputs.mask = True
	functional_BET.inputs.frac = 0.5

	functional_bandpass = pe.Node(interface=Bandpass(), name="functional_bandpass")
	functional_bandpass.inputs.highpass = 0.001
	functional_bandpass.inputs.lowpass = 9999

	structural_bandpass = pe.Node(interface=Bandpass(), name="structural_bandpass")
	structural_bandpass.inputs.highpass = 0.001
	structural_bandpass.inputs.lowpass = 9999

	melodic = pe.Node(interface=MELODIC(), name="MELODIC")
	melodic.inputs.report = True
	melodic.inputs.dim = 8

	workflow = pe.Workflow(name=workflow_denominator)

	workflow_connections = [
		(infosource, getmeasurement, [('condition', 'condition_id'),('subject', 'subject_id')]),
		(getmeasurement, functional_scan_finder, [('measurement_path', 'scans_directory')]),
		(functional_scan_finder, functional_bru2nii, [('positive_scan', 'input_dir')]),
		(functional_scan_finder, timing_metadata, [('positive_scan', 'scan_directory')]),
		(functional_bru2nii, realigner, [('nii_file', 'in_file')]),
		(realigner, temporal_mean, [('out_file', 'in_file')]),
		(temporal_mean, functional_FAST, [('out_file', 'in_files')]),
		(functional_FAST, functional_cutoff, [('restored_image', 'in_file')]),
		(functional_cutoff, functional_BET, [('out_file', 'in_file')]),
		(functional_BET, functional_registration, [('out_file', 'moving_image')]),
		(functional_registration, functional_warp, [('composite_transform', 'transforms')]),
		(realigner, functional_warp, [('out_file', 'input_image')]),
		(functional_warp, functional_bandpass, [('output_image', 'in_file')]),
		]

	if structural_scan_type:
		workflow_connections.extend([
			(getmeasurement, structural_scan_finder, [('measurement_path', 'scans_directory')]),
			(structural_scan_finder, structural_bru2nii, [('positive_scan', 'input_dir')]),
			(structural_bru2nii, structural_FAST, [('nii_file', 'in_files')]),
			(structural_FAST, structural_cutoff, [('restored_image', 'in_file')]),
			(structural_cutoff, structural_BET, [('out_file', 'in_file')]),
			(structural_BET, structural_registration, [('out_file', 'moving_image')]),
			(structural_registration, structural_warp, [('composite_transform', 'transforms')]),
			(realigner, structural_warp, [('out_file', 'input_image')]),
			(structural_warp, structural_bandpass, [('output_image', 'in_file')]),
			])

	workflow.connect(workflow_connections)

	if standalone_execute:
		workflow.base_dir = measurements_base
		workflow.run(plugin="MultiProc",  plugin_args={'n_procs' : 4})
	else:
		return workflow

def bru2_preproc(measurements_base, functional_scan_type, structural_scan_type=None, tr=1, conditions=[], include_subjects=[], exclude_subjects=[], include_measurements=[], exclude_measurements=[], actual_size=False, workflow_denominator="PreprocessingGLM", template="ds_QBI_atlas100RD.nii"):
	workflow_base = path.expanduser(workflow_base)
	data_selection=get_data_selection(measurements_base, conditions, include_subjects=include_subjects, exclude_subjects=exclude_subjects, exclude_measurements=exclude_measurements)

	infosource = pe.Node(interface=util.IdentityInterface(fields=['measurement_id']), name="infosource")
	infosource.iterables = ('measurement', IDs)

	data_source = pe.Node(interface=nio.DataGrabber(infields=['measurement_id'], outfields=['measurement_path']), name='data_source')
	data_source.inputs.template = workflow_base+"/%s"
	data_source.inputs.template_args['measurement_path'] = [['measurement_id']]

	data_source.inputs.sort_filelist = True

	functional_scan_finder = pe.Node(interface=FindScan(), name="functional_scan_finder")
	functional_scan_finder.inputs.query = functional_scan_type
	functional_scan_finder.inputs.query_file = "visu_pars"

	timing_metadata = pe.Node(interface=GetBrukerTiming(), name="timing_metadata")

	if structural_scan_type:
		structural_scan_finder = pe.Node(interface=FindScan(), name="structural_scan_finder")
		structural_scan_finder.inputs.query = structural_scan_type
		structural_scan_finder.inputs.query_file = "visu_pars"
		structural_bru2nii = pe.Node(interface=Bru2(), name="structural_bru2nii")
		structural_bru2nii.inputs.force_conversion=True
		structural_bru2nii.inputs.actual_size=actual_size

		structural_FAST = pe.Node(interface=FAST(), name="structural_FAST")
		structural_FAST.inputs.segments = False
		structural_FAST.inputs.output_biascorrected = True
		structural_FAST.inputs.bias_iters = 8

		structural_cutoff = pe.Node(interface=ImageMaths(), name="structural_cutoff")
		structural_cutoff.inputs.op_string = "-thrP 45"

	functional_bru2nii = pe.Node(interface=Bru2(), name="functional_bru2nii")
	functional_bru2nii.inputs.actual_size=actual_size

	realigner = pe.Node(interface=SpaceTimeRealigner(), name="realigner")
	realigner.inputs.slice_times = "asc_alt_2"
	realigner.inputs.tr = tr
	realigner.inputs.slice_info = 3 #3 for coronal slices (2 for horizontal, 1 for sagittal)

	temporal_mean = pe.Node(interface=MeanImage(), name="temporal_mean")
	functional_masker = pe.Node(interface=ApplyMask(), name="functional_masker")

	structural_BET = pe.Node(interface=BET(), name="structural_BET")
	structural_BET.inputs.mask = True
	structural_BET.inputs.frac = 0.5

	structural_registration, structural_warp = ants_standard_registration_warp(template, "structural_registration", "structural_warp")
	functional_registration, functional_warp = ants_standard_registration_warp(template, "functional_registration", "functional_warp")

	functional_FAST = pe.Node(interface=FAST(), name="functional_FAST")
	functional_FAST.inputs.segments = False
	functional_FAST.inputs.output_biascorrected = True
	functional_FAST.inputs.bias_iters = 8

	functional_cutoff = pe.Node(interface=ImageMaths(), name="functional_cutoff")
	functional_cutoff.inputs.op_string = "-thrP 45"

	functional_BET = pe.Node(interface=BET(), name="functional_BET")
	functional_BET.inputs.mask = True
	functional_BET.inputs.frac = 0.5

	functional_bandpass = pe.Node(interface=Bandpass(), name="functional_bandpass")
	functional_bandpass.inputs.highpass = 0.001
	functional_bandpass.inputs.lowpass = 9999

	structural_bandpass = pe.Node(interface=Bandpass(), name="structural_bandpass")
	structural_bandpass.inputs.highpass = 0.001
	structural_bandpass.inputs.lowpass = 9999

	melodic = pe.Node(interface=MELODIC(), name="MELODIC")
	melodic.inputs.report = True
	melodic.inputs.dim = 8

	workflow = pe.Workflow(name=workflow_denominator)

	workflow_connections = [
		(infosource, data_source, [('measurement_id', 'measurement_id')]),
		(data_source, functional_scan_finder, [('measurement_path', 'scans_directory')]),
		(functional_scan_finder, functional_bru2nii, [('positive_scan', 'input_dir')]),
		(functional_scan_finder, timing_metadata, [('positive_scan', 'scan_directory')]),
		(functional_bru2nii, realigner, [('nii_file', 'in_file')]),
		(realigner, temporal_mean, [('out_file', 'in_file')]),
		(temporal_mean, functional_FAST, [('out_file', 'in_files')]),
		(functional_FAST, functional_cutoff, [('restored_image', 'in_file')]),
		(functional_cutoff, functional_BET, [('out_file', 'in_file')]),
		(functional_BET, functional_registration, [('out_file', 'moving_image')]),
		(functional_registration, functional_warp, [('composite_transform', 'transforms')]),
		(realigner, functional_warp, [('out_file', 'input_image')]),
		(functional_warp, functional_bandpass, [('output_image', 'in_file')]),
		]

	if structural_scan_type:
		workflow_connections.extend([
			(data_source, structural_scan_finder, [('measurement_path', 'scans_directory')]),
			(structural_scan_finder, structural_bru2nii, [('positive_scan', 'input_dir')]),
			(structural_bru2nii, structural_FAST, [('nii_file', 'in_files')]),
			(structural_FAST, structural_cutoff, [('restored_image', 'in_file')]),
			(structural_cutoff, structural_BET, [('out_file', 'in_file')]),
			(structural_BET, structural_registration, [('out_file', 'moving_image')]),
			(structural_registration, structural_warp, [('composite_transform', 'transforms')]),
			(realigner, structural_warp, [('out_file', 'input_image')]),
			(structural_warp, structural_bandpass, [('output_image', 'in_file')]),
			])

	workflow.connect(workflow_connections)
	return workflow

if __name__ == "__main__":
	bru_preproc_lite(measurements_base="/mnt/data/NIdata/ofM.erc/", functional_scan_types=["EPI_CBV_alej","EPI_CBV_jin6","EPI_CBV_jin10","EPI_CBV_jin20","EPI_CBV_jin40","EPI_CBV_jin60"], structural_scan_type="T2_TurboRARE", conditions=["ERC_ofM"], include_subjects=["5502","5503"])
	# bru2_preproc2("~/NIdata/ofM.dr/", "7_EPI_CBV", structural_scan_type="T2_TurboRARE", conditions=["ofM","ofM_aF"], exclude_measurements=["20151027_121613_4013_1_1"], standalone_execute=True)
	# testme("~/NIdata/ofM.erc/", ["EPI_CBV_alej","EPI_CBV_jin6","EPI_CBV_jin10","EPI_CBV_jin20","EPI_CBV_jin40","EPI_CBV_jin60","T2_TurboRARE"], conditions=["ERC_ofM"], include_subjects=["5503","5502"])
