import nipype.pipeline.engine as pe
import nipype.interfaces.utility as util
from nipype.interfaces.fsl import GLM, MELODIC, FAST, BET
import nipype.interfaces.io as nio
from os import path
from preprocessing import bru2_preproc

def fsl_glm(workflow_base, functional_scan_type, structural_scan_type, workflow_denominator="FSL_GLM", omit_ID=[]):
	workflow_base = path.expanduser(workflow_base)
	bru2_preproc_workflow = bru2_preproc(workflow_base, functional_scan_type, structural_scan_type=structural_scan_type, omit_ID=omit_ID)

	spatial_filtering = pe.Node(interface=FAST(), name="FAST")
	spatial_filtering.inputs.output_biascorrected = True
	spatial_filtering.inputs.bias_iters = 6

	skullstripping = pe.Node(interface=BET(), name="BET")

	melodic = pe.Node(interface=MELODIC(), name="MELODIC")
	melodic.inputs.report = True
	melodic.inputs.dim = 8

	datasink = pe.Node(nio.DataSink(), name='sinker')
	datasink.inputs.base_directory = workflow_base+"/"+workflow_denominator+"_results"

	#SET UP ANALYSIS WORKFLOW:
	analysis_workflow = pe.Workflow(name="GLM")

	analysis_workflow.connect([
		(spatial_filtering, skullstripping, [('restored_image', 'in_file')]),
		(skullstripping, melodic, [('out_file', 'in_files')]),
		(melodic, datasink, [('report_dir', 'MELODIC_reports')])
		])

	#SET UP COMBINED WORKFLOW:
	pipeline = pe.Workflow(name=workflow_denominator+"_work")
	pipeline.base_dir = workflow_base

	pipeline.connect([(bru2_preproc_workflow, analysis_workflow, [('bru2_functional.nii_file','FAST.in_files')])
		])

	pipeline.write_graph(graph2use="orig")
	pipeline.run(plugin="MultiProc")

if __name__ == "__main__":
	fsl_glm(workflow_base="~/NIdata/ofM.dr/", functional_scan_type="7_EPI_CBV", structural_scan_type="4_T2_TurboRARE", omit_ID=["20151026_135856_4006_1_1"])
