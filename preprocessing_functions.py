from nipype.interfaces.dcmstack import DcmStack
stacker = DcmStack()
from dcmstack.extract import default_extractor
from dicom import read_file
from os import listdir, path, makedirs
from shutil import move

def convert_dcm_dir(dicom_dir, multi_epi=False):

	nii_dir = dicom_dir.replace("dicom", "nii")
	if not path.exists(nii_dir):
		makedirs(nii_dir)

	if multi_epi:
		dicom_files = listdir(dicom_dir)
		echo_times=[]
		for dicom_file in dicom_files:
			meta = default_extractor(read_file(dicom_dir+dicom_file, stop_before_pixels=True, force=True))
			echo_times += [meta["EchoTime"]]

		for echo_time in list(set(echo_times)):
			echo_indices = [i for i, j in enumerate(echo_times) if j == echo_time]
			stacker.inputs.dicom_files = [dicom_dir+dicom_files[index] for index in echo_indices]
			stacker.inputs.embed_meta = True
			file_name = "EPI"+str(echo_time)[:2]
			stacker.inputs.out_format = file_name
			result = stacker.run()
			destination_file_name = nii_dir+"/"+file_name
			move(result.outputs.out_file, destination_file_name)
			print(destination_file_name)

	else:
		stacker.inputs.dicom_files = dicom_dir
		file_name = "EPI"
		stacker.inputs.out_format = file_name
		result = stacker.run()
		destination_file_name = nii_dir+"/"+file_name
		move(result.outputs.out_file, destination_file_name)
		print(destination_file_name)

if __name__ == "__main__":
	convert_dcm_dir("/home/chymera/data2/dc.rs/export_ME/dicom/4459/1/EPI/", multi_epi=True)
