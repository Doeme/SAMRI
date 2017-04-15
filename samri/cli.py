__author__ = "Horea Christian"

import argh
from pipelines.nipype_based.diagnostics import diagnose

def main():
	argh.dispatch_commands([diagnose])

if __name__ == '__main__':
	main()
