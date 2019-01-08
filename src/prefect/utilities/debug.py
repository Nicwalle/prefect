# Licensed under LICENSE.md; also available at https://www.prefect.io/licenses/alpha-eula

import cloudpickle
import os
import subprocess
import tempfile

from contextlib import contextmanager
import textwrap
from typing import Any, Iterator

import prefect
from prefect.engine import state


def is_serializable(obj: Any, raise_on_error: bool = False) -> bool:
    """
    Checks whether a given object can be deployed to Prefect Cloud.  This requires
    that the object can be serialized in the current process and deserialized in a fresh process.

    Args:
        - obj (Any): the object to check
        - raise_on_error(bool, optional): if `True`, raises the `CalledProcessError` for inspection;
            the `output` attribute of this exception can contain useful information about why the object is not deployable

    Returns:
        - bool: `True` if deployable, `False` otherwise

    Raises:
        - subprocess.CalledProcessError: if `raise_on_error=True` and the object is not deployable
    """

    template = textwrap.dedent(
        """
        import cloudpickle

        with open('{}', 'rb') as z76123:
            res = cloudpickle.load(z76123)
        """
    )
    bd, binary_file = tempfile.mkstemp()
    sd, script_file = tempfile.mkstemp()
    os.close(bd)
    os.close(sd)
    try:
        with open(binary_file, "wb") as bf:
            cloudpickle.dump(obj, bf)
        with open(script_file, "w") as sf:
            sf.write(template.format(binary_file))
        try:
            subprocess.check_output(
                "python {}".format(script_file), shell=True, stderr=subprocess.STDOUT
            )
        except subprocess.CalledProcessError as exc:
            if raise_on_error:
                raise exc
            return False
    except Exception as exc:
        if raise_on_error:
            raise exc
        return False
    finally:
        os.unlink(binary_file)
        os.unlink(script_file)
    return True


@contextmanager
def raise_on_exception() -> Iterator:
    """
    Context manager for raising exceptions when they occur instead of trapping them.
    Intended to be used only for local debugging and testing.

    Example:
        ```python
        from prefect import Flow, task
        from prefect.utilities.debug import raise_on_exception

        @task
        def div(x):
            return 1 / x

        with Flow() as f:
            res = div(0)

        with raise_on_exception():
            f.run() # raises ZeroDivisionError
        ```
    """
    with prefect.context(raise_on_exception=True):
        yield


def make_return_failed_handler(failed_tasks_set: set):
    """
    This state handler can be used to automatically return any tasks that failed or retried
    from the FlowRunner.

    NOTE: this will only work with the LocalExecutor, as it depends on sharing a global set

    It can be used like this:

    ```
    flow = prefect.Flow(...)
    return_tasks = set()
    state = flow.run(
        return_tasks=return_tasks,
        task_runner_state_handlers=[make_return_failed_handler(return_tasks)])
    ```
    """

    def handler(
        task_runner: "prefect.engine.task_runner.TaskRunner",
        old_state: state.State,
        new_state: state.State,
    ) -> state.State:
        if isinstance(new_state, (state.Failed, state.Retrying)):
            failed_tasks_set.add(task_runner.task)
        return new_state

    return handler