import logging
import os
import sys
from dataclasses import dataclass

from coffea.processor.accumulator import accumulate
from coffea.processor.executor import ExecutorBase

from .executors_base import ExecutorFactoryABC

logger = logging.getLogger("luigi-interface")


class DaskExecutorFactory(ExecutorFactoryABC):
    """dask with htcondor vor VISPA cluster at RWTH."""

    def __init__(self, run_options, outputdir, **kwargs):
        self.outputdir = outputdir
        super().__init__(run_options=run_options, **kwargs)

    def get_worker_env(self):
        worker_env = [
            f"export X509_USER_PROXY={self.x509_path}",
        ]

        # add custon setup commands from user
        worker_env += self.run_options.get("custom-setup-commands", [])

        # python environment
        if self.run_options.get("conda-env", False):
            worker_env.append(f"export PATH={os.environ['CONDA_PREFIX']}/bin:$PATH")

            conda_root_prefix = os.environ.get("CONDA_ROOT_PREFIX", None)
            mamba_root_prefix = os.environ.get("MAMBA_ROOT_PREFIX", None)
            conda_default_env = os.environ.get("CONDA_DEFAULT_ENV", None)
            if conda_root_prefix is not None:
                worker_env.append(f"{conda_root_prefix} activate {conda_default_env}")
            elif mamba_root_prefix is not None:
                worker_env.append(f"{mamba_root_prefix} activate {conda_default_env}")
            else:
                raise RuntimeError(
                    """Neither CONDA_ROOT_PREFIX nor MAMBA_ROOT_PREFIX is set.
                    Cannot set up conda environment."""
                )

        elif self.run_options.get("local-virtualenv", False):
            worker_env.append(f"source {sys.prefix}/bin/activate")

        return worker_env

    def setup(self):
        from dask.distributed import Client
        from dask_jobqueue import HTCondorCluster
        from distributed.security import Security

        try:
            dashboard_address = os.environ["DASK_DASHBOARD_ADDRESS"]
        except KeyError:
            raise KeyError(
                """environment variable DASK_DASHBOARD_ADDRESS is not set.
                Please set it to the address of the Dask dashboard."""
            )

        # setup of voms proxy
        self.setup_proxyfile()

        # https://git.rwth-aachen.de/3pia/cms_analyses/common/-/blob/master/tasks/coffea.py?ref_type=heads#L235
        self.cluster = HTCondorCluster(
            cores=1,
            processes=1,
            memory=self.run_options.get("mem-per-worker", "2000MiB"),
            disk="2GB",
            local_directory="/tmp",
            protocol="tls://",
            security=Security(),
            scheduler_options={
                "dashboard_address": dashboard_address,
            },
            job_script_prologue=self.get_worker_env(),
            worker_extra_args=["--lifetime", "90m", "--lifetime-stagger", "15m"],
            job_extra_directives={"Request_CPUs": 0, "Request_GPUs": 0, "Getenv": True},
        )

        self.client = Client(self.cluster, security=Security())
        logger.info(f"dask dashboard at: {self.client.dashboard_link}")

        # TODO: scale efficiently
        self.cluster.adapt(
            minimum_jobs=1, maximum_jobs=max(self.run_options.get("scaleout", 1), 100)
        )

        logger.info("Waiting for workers to be available...")
        self.client.wait_for_workers(1)
        logger.info("Dask workers are available. Starting processing... YEAH!")

    def get(self):
        from coffea.processor import DaskExecutor

        return DaskExecutor(
            client=self.client, treereduction=20, retries=0, compression=1
        )

    def close(self):
        self.client.close()
        self.cluster.close()


@dataclass
class IterativeExecutorWithoutProgressBar(ExecutorBase):
    """Execute in one thread iteratively

    Parameters
    ----------
        items : list
            List of input arguments
        function : callable
            A function to be called on each input, which returns an accumulator instance
        accumulator : Accumulatable
            An accumulator to collect the output of the function
        status : bool
            If true (default), enable progress bar
        unit : str
            Label of progress bar unit
        desc : str
            Label of progress bar description
        compression : int, optional
            Ignored for iterative executor
    """

    workers: int = 1

    def __call__(
        self,
        items,
        function,
        accumulator,
    ):
        if len(items) == 0:
            return accumulator
        return (
            accumulate(
                map(function, (c for c in items)),
                accumulator,
            ),
            0,
        )


class IterativeExecutorFactory(ExecutorFactoryABC):
    """Iterative Executor without progress bar.
    The progress bar can be annoying if you use IPython embeded shells,
    so it is disabled here for better usability.
    """

    def get(self):
        return IterativeExecutorWithoutProgressBar(**self.customized_args())


def get_executor_factory(executor_name, **kwargs):
    if executor_name == "dask":
        return DaskExecutorFactory(**kwargs)
    elif executor_name == "iterative":
        return IterativeExecutorFactory(**kwargs)
    else:
        raise ValueError(f"Executor {executor_name} is not supported.")
