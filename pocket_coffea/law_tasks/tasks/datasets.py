"""law tasks for a HEP analysis with pocket_coffea"""

import law
import luigi
import luigi.util
from pocket_coffea.law_tasks.configuration.general import (
    datasetconfig,
)
from pocket_coffea.law_tasks.utils import (
    create_datasets_paths,
    modify_dataset_output_path,
    read_datasets_definition,
)
from pocket_coffea.utils.dataset import build_datasets

# this is a nice idea but does not currently work because the datasets definition file
# needs to exist in the output of the CreateDatasets task
# @luigi.util.inherits(datasetconfig)
# class DatasetDefinitionExists(law.ExternalTask):
#     """Check existence of dataset definition file
#     External task, the datasets definition needs to be written by hand
#     """

#     def output(self):
#         return law.LocalFileTarget(self.dataset_definition)


# @luigi.util.requires(DatasetDefinitionExists)
@luigi.util.inherits(datasetconfig)
class CreateDatasets(law.Task):
    """Create dataset json files"""

    def output(self):
        """json files for datasets"""
        return [
            law.LocalFileTarget(dataset)
            for dataset in create_datasets_paths(
                datasets=read_datasets_definition(self.dataset_definition),
                output_dir=self.dataset_dir,
                split_by_year=self.split_by_year,
            )
        ]

    def run(self):
        # modify the output path of the dataset definition to reflect the correct
        # output directory
        modified_dataset_definition = modify_dataset_output_path(
            self.dataset_definition, self.dataset_dir
        )

        # build the dataset json file
        build_datasets(
            cfg=modified_dataset_definition,
            keys=self.keys,
            download=self.download,
            overwrite=self.overwrite,
            check=self.check,
            split_by_year=self.split_by_year,
            local_prefix=self.local_prefix,
            allowlist_sites=self.allowlist_sites,
            blocklist_sites=self.blocklist_sites,
            regex_sites=self.regex_sites,
            parallelize=self.parallelize,
        )
