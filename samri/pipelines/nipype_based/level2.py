import inspect
import re
import nipype.interfaces.io as nio
import nipype.interfaces.utility as util
import nipype.pipeline.engine as pe
import nipype.interfaces.fsl as fsl
from itertools import product
from nipype.algorithms.modelgen import SpecifyModel
from os import path, listdir, remove, getcwd

from extra_interfaces import GenL2Model
from preprocessing import bru_preproc
from utils import datasource_exclude
try:
	from ..extra_functions import get_level2_inputs, get_subjectinfo, write_function_call
except ValueError:
	import os
	import sys
	sys.path.append(os.path.expanduser('~/src/SAMRI/samri/pipelines'))
	from extra_functions import get_level2_inputs, get_subjectinfo, write_function_call

def getlen(a):
	return len(a)
def add_suffix(name, suffix):
	return str(name)+str(suffix)

def l2_common_effect(l1_dir, tr=1, nprocs=6, l2_dir="", workflow_name="generic", groupby="session", excludes={}):
	l1_dir = path.expanduser(l1_dir)
	if not l2_dir:
		l2_dir = path.abspath(path.join(l1_dir,"..","..","l2"))

	datafind = nio.DataFinder()
	datafind.inputs.root_paths = l1_dir
	datafind.inputs.match_regex = '.+/sub-(?P<sub>.+)/ses-(?P<ses>.+)/.*?_trial-(?P<scan>.+)_cope\.nii.gz'
	datafind_res = datafind.run()
	subjects = set(datafind_res.outputs.sub)
	sessions = set(datafind_res.outputs.ses)
	scans = set(datafind_res.outputs.scan)

	datasource = pe.Node(interface=nio.DataGrabber(infields=["group",], outfields=["copes", "varcbs"]), name="datasource")
	datasource.inputs.base_directory = l1_dir
	datasource.inputs.sort_filelist = True
	datasource.inputs.template = "*"
	datasource.inputs.template_args = dict(
		copes=[['group','group']],
		varcbs=[['group','group']]
		)

	infosource = pe.Node(interface=util.IdentityInterface(fields=['iterable']), name="infosource")

	copemerge = pe.Node(interface=fsl.Merge(dimension='t'),name="copemerge")
	varcopemerge = pe.Node(interface=fsl.Merge(dimension='t'),name="varcopemerge")

	level2model = pe.Node(interface=fsl.L2Model(),name='level2model')

	flameo = pe.Node(interface=fsl.FLAMEO(), name="flameo")
	flameo.inputs.mask_file="/home/chymera/NIdata/templates/ds_QBI_chr_bin.nii.gz"
	flameo.inputs.run_mode="ols"

	datasink = pe.Node(nio.DataSink(), name='datasink')
	datasink.inputs.base_directory = path.join(l2_dir,workflow_name)
	datasink.inputs.substitutions = [('_iterable_', ''),]

	if groupby == "subject":
		infosource.iterables = [('iterable', subjects)]
		datasource.inputs.field_template = dict(
			copes="sub-%s/ses-*/sub-%s_ses-*_trial-*_cope.nii.gz",
			varcbs="sub-%s/ses-*/sub-%s_ses-*_trial-*_varcb.nii.gz",
			)
	elif groupby == "session":
		infosource.iterables = [('iterable', sessions)]
		datasource.inputs.field_template = dict(
			copes="sub-*/ses-%s/sub-*_ses-%s_trial-*_cope.nii.gz",
			varcbs="sub-*/ses-%s/sub-*_ses-%s_trial-*_varcb.nii.gz",
			)
	elif groupby == "scan":
		infosource.iterables = [('iterable', scans)]
		datasource.inputs.template_args = dict(
			copes=[['group']],
			varcbs=[['group']]
			)
		datasource.inputs.field_template = dict(
			copes="sub-*/ses-*/sub-*_ses-*_trial-%s_cope.nii.gz ",
			varcbs="sub-*/ses-*/sub-*_ses-*_trial-%s_varcb.nii.gz ",
			)

	workflow_connections = [
		(infosource, datasource, [('iterable', 'group')]),
		(infosource, copemerge, [(('iterable',add_suffix,"_cope.nii.gz"), 'merged_file')]),
		(infosource, varcopemerge, [(('iterable',add_suffix,"_varcb.nii.gz"), 'merged_file')]),
		(datasource, copemerge, [(('copes',datasource_exclude,excludes), 'in_files')]),
		(datasource, varcopemerge, [(('varcbs',datasource_exclude,excludes), 'in_files')]),
		(datasource, level2model, [(('copes',datasource_exclude,excludes,"len"), 'num_copes')]),
		(copemerge,flameo,[('merged_file','cope_file')]),
		(varcopemerge,flameo,[('merged_file','var_cope_file')]),
		(level2model,flameo, [('design_mat','design_file')]),
		(level2model,flameo, [('design_grp','cov_split_file')]),
		(level2model,flameo, [('design_con','t_con_file')]),
		(flameo, datasink, [('copes', '@copes')]),
		(flameo, datasink, [('fstats', '@fstats')]),
		(flameo, datasink, [('tstats', '@tstats')]),
		(flameo, datasink, [('zstats', '@zstats')]),
		]

	workdir_name = workflow_name+"_work"
	workflow = pe.Workflow(name=workdir_name)
	workflow.connect(workflow_connections)
	workflow.base_dir = l2_dir
	workflow.write_graph(dotfilename=path.join(workflow.base_dir,workdir_name,"graph.dot"), graph2use="hierarchical", format="png")

	workflow.run(plugin="MultiProc",  plugin_args={'n_procs' : nprocs})

def level2_common_effect(level1_directory, categories=[], participants=[], scan_types=[], denominator="level2"):
	level1_directory = path.expanduser(level1_directory)
	#edit the following lines to choose different outputs (e.g. from functional coregistration)
	copemergeroot = level1_directory+"/results/func_cope/"
	varcbmergeroot = level1_directory+"/results/func_varcb/"

	copemerge = pe.Node(interface=Merge(dimension='t'),name="copemerge")
	varcopemerge = pe.Node(interface=Merge(dimension='t'),name="varcopemerge")

	level2model = pe.Node(interface=L2Model(),name='level2model')

	flameo = pe.MapNode(interface=FLAMEO(), name="flameo", iterfield=['cope_file','var_cope_file'])
	flameo.inputs.mask_file="/home/chymera/NIdata/templates/ds_QBI_chr_bin.nii.gz"
	flameo.inputs.run_mode="ols"

	workflow_connections = [
		(copemerge,flameo,[('merged_file','cope_file')]),
		(varcopemerge,flameo,[('merged_file','var_cope_file')]),
		(level2model,flameo, [('design_mat','design_file')]),
		(level2model,flameo, [('design_grp','cov_split_file')]),
		(level2model,flameo, [('design_con','t_con_file')]),
		]

	multi_scan_type = False
	multi_category = False
	try:
		if isinstance(scan_types[0],list):
			multi_scan_type = True
	except IndexError:
		pass
	try:
		if isinstance(categories[0],list):
			multi_category = True
	except IndexError:
		pass

	if multi_category or multi_scan_type:
		get_copes = pe.Node(name='get_copes', interface=util.Function(function=get_level2_inputs,input_names=["input_root","categories","participants","scan_types"], output_names=['scan_paths']))
		get_copes.inputs.input_root=copemergeroot
		get_copes.inputs.participants=participants
		get_varcbs = pe.Node(name='get_varcbs', interface=util.Function(function=get_level2_inputs,input_names=["input_root","categories","participants","scan_types"], output_names=['scan_paths']))
		get_varcbs.inputs.input_root=varcbmergeroot
		get_varcbs.inputs.participants=participants

		if not multi_category:
			infosource = pe.Node(interface=util.IdentityInterface(fields=['scan_type_multi']), name="infosource")
			infosource.iterables = [('scan_type_multi',scan_types)]
			get_copes.inputs.categories=categories
			get_varcbs.inputs.categories=categories
			workflow_connections.extend([
				(infosource, get_copes, [('scan_type_multi', 'scan_types')]),
				(infosource, get_varcbs, [('scan_type_multi', 'scan_types')]),
				])

		if not multi_scan_type:
			infosource = pe.Node(interface=util.IdentityInterface(fields=['category_multi']), name="infosource")
			infosource.iterables = [('category_multi',categories)]
			get_copes.inputs.scan_types=scan_types
			get_varcbs.inputs.scan_types=scan_types
			workflow_connections.extend([
				(infosource, get_copes, [('category_multi', 'categories')]),
				(infosource, get_varcbs, [('category_multi', 'categories')]),
				])

		workflow_connections.extend([
			(get_copes, copemerge, [('scan_paths', 'in_files')]),
			(get_varcbs, varcopemerge, [('scan_paths', 'in_files')]),
			(get_copes, level2model, [(('scan_paths',getlen), 'num_copes')]),
			])
	else:
		copes = get_level2_inputs(copemergeroot, categories=categories, participants=participants, scan_types=scan_types)
		varcbs = get_level2_inputs(varcbmergeroot, categories=categories, participants=participants, scan_types=scan_types)

		copemerge.inputs.in_files=copes
		varcopemerge.inputs.in_files=varcbs

		level2model.inputs.num_copes=len(copes)

	second_level = pe.Workflow(name=denominator)
	second_level.connect(workflow_connections)

	second_level.base_dir = level1_directory+"/.."
	second_level.write_graph(dotfilename=path.join(second_level.base_dir,denominator,"graph.dot"),graph2use="flat")
	frame = inspect.currentframe()
	write_function_call(frame,path.join(second_level.base_dir,denominator,"function_call.txt"))
	second_level.run(plugin="MultiProc",  plugin_args={'n_procs' : 6})

def level2(level1_directory, categories=["ofM","ofM_aF"], participants=["4008","4007","4011","4012"], denominator="level2"):
	level1_directory = path.expanduser(level1_directory)
	copemergeroot = level1_directory+"/results/cope/"
	varcbmergeroot = level1_directory+"/results/varcb/"

	subirs_list = [category+"."+participant for category, participant in product(categories,participants)]

	copes = [copemergeroot+sub_dir+"/cope.nii.gz" for sub_dir in subirs_list]

	copemerge = pe.Node(interface=Merge(dimension='t'),name="copemerge")
	copemerge.inputs.in_files=copes

	varcopemerge = pe.Node(interface=Merge(dimension='t'),name="varcopemerge")
	varcopemerge.inputs.in_files=[varcbmergeroot+sub_dir+"/varcb.nii.gz" for sub_dir in subirs_list]

	level2model = pe.Node(interface=GenL2Model(),name='level2model')
	level2model.inputs.num_copes=len(copes)
	level2model.inputs.conditions=categories
	level2model.inputs.subjects=participants

	flameo = pe.MapNode(interface=FLAMEO(), name="flameo", iterfield=['cope_file','var_cope_file'])
	flameo.inputs.mask_file="/home/chymera/NIdata/templates/ds_QBI_chr_bin.nii.gz"
	flameo.inputs.run_mode="ols"

	second_level = pe.Workflow(name=denominator)

	second_level.connect([
		(copemerge,flameo,[('merged_file','cope_file')]),
		(varcopemerge,flameo,[('merged_file','var_cope_file')]),
		(level2model,flameo, [('design_mat','design_file')]),
		(level2model,flameo, [('design_grp','cov_split_file')]),
		(level2model,flameo, [('design_con','t_con_file')]),
		])

	second_level.write_graph(graph2use="flat")
	second_level.base_dir = level1_directory+"/.."
	second_level.run(plugin="MultiProc",  plugin_args={'n_procs' : 6})

if __name__ == "__main__":
	# level1("~/NIdata/ofM.dr/", {"7_EPI_CBV":"6_20_jb"}, structural_scan_types=-1, conditions=["ofM","ofM_aF","ofM_cF1","ofM_cF2","ofM_pF"], exclude_measurements=["20151027_121613_4013_1_1"], pipeline_denominator="level1_dgamma_blurxy56n", blur_xy=5.6)
	# level1("~/NIdata/ofM.erc/", {"EPI_CBV_jin6":"jin6","EPI_CBV_jin10":"jin10","EPI_CBV_jin20":"jin20","EPI_CBV_jin40":"jin40","EPI_CBV_jin60":"jin60","EPI_CBV_alej":"alej",}, structural_scan_types=-1, actual_size=False, pipeline_denominator="level1_dgamma")
	# level2_common_effect("~/NIdata/ofM.erc/GLM/level1_dgamma", categories=[], scan_types=[["EPI_CBV_jin6"],["EPI_CBV_jin10"],["EPI_CBV_jin20"],["EPI_CBV_jin40"],["EPI_CBV_jin60"],["EPI_CBV_alej"]], participants=["5502","5503"], denominator="level2_dgamma")
	# for i in range(4,8):
	# 	level1("~/NIdata/ofM.erc/", {"EPI_CBV_jin6":"jin6","EPI_CBV_jin10":"jin10","EPI_CBV_jin20":"jin20","EPI_CBV_jin40":"jin40","EPI_CBV_jin60":"jin60","EPI_CBV_alej":"alej",}, structural_scan_types=-1, actual_size=False, pipeline_denominator="level1_dgamma_blurxy"+str(i), blur_xy=i)

	l2_common_effect("~/NIdata/ofM.dr/l1/generic", workflow_name="sessionwise", groupby="session", excludes={"subjects":["4001","4008"]})
	l2_common_effect("~/NIdata/ofM.dr/l1/generic", workflow_name="subjectwise", groupby="subject")
