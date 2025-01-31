"""
A file containing the classes and code required to read a file stored in the common
intermediate format introduced in PR 319 (https://github.com/ceph/cbt/pull/319) and produce a hockey-stick curve graph
"""

import os
from abc import ABC, abstractmethod
from logging import Logger, getLogger
from pathlib import Path
from types import ModuleType
from typing import Optional, Union

from post_processing.common import (
    COMMON_FORMAT_DATA_TYPE,
    DATA_FILE_EXTENSION_WITH_DOT,
    PLOT_DATA_TYPE,
    PLOT_FILE_EXTENSION,
    get_blocksize_percentage_operation_from_file_name,
)

log: Logger = getLogger(f"{os.path.basename(__file__)}")


class CommonFormatPlotter(ABC):
    """
    The base class for plotting results curves
    """

    @abstractmethod
    def draw_and_save(self) -> None:
        """
        Produce the plot file(s) for each of the intermediate data files in the
        given directory and save them to disk
        """

    @abstractmethod
    def _generate_output_file_name(self, files: list[Path]) -> str:
        """
        Generate the name for the file the plot will be saved to.
        """

    def _add_title(self, plotter: ModuleType, source_files: list[Path]) -> None:
        """
        Given the source file full path, generate the title for the
        data plot and add it to the plot
        """

        title: str = ""

        if len(source_files) == 1:
            title = self._construct_title_from_file_name(source_files[0].parts[-1])
        else:
            title = self._construct_title_from_list_of_file_names(source_files)

        plotter.title(title)

    def _construct_title_from_list_of_file_names(self, file_paths: list[Path]) -> str:
        """
        Given a list of file paths construct a plot title.

        If there is a common element then the title will be
        '<common_element> comparison'
        e.g if all files had a blocksize = 16K the title would be
        '16k blocksize comparison'
        """
        titles: list[tuple[str, str, str]] = []
        blocksizes: list[str] = []
        read_percents: list[str] = []
        operations: list[str] = []

        for file in file_paths:
            (blocksize, read_percent, operation) = get_blocksize_percentage_operation_from_file_name(file.stem)
            titles.append((blocksize, read_percent, operation))

            if blocksize not in blocksizes:
                blocksizes.append(blocksize)
            if read_percent not in read_percents:
                read_percents.append(read_percent)
            if operation not in operations:
                operations.append(operation)

        if len(blocksizes) == 1:
            return f"{blocksizes[0]} blocksize comparison"

        if len(operations) == 1 and len(read_percents) == 1:
            return f"{read_percents[0]} {operations[0]} comparison"

        if len(operations) == 1:
            return f"{operations[0]} comparison"

        title: str = " ".join(titles.pop(0))
        for details in titles:
            title += "\nVs "
            title += " ".join(details)

        return title

    def _construct_title_from_file_name(self, file_name: str) -> str:
        """
        given a single file name construct a plot title from the blocksize,
        read percent and operation contained in the title
        """
        (blocksize, read_percent, operation) = get_blocksize_percentage_operation_from_file_name(
            file_name[: -len(DATA_FILE_EXTENSION_WITH_DOT)]
        )

        return f"{blocksize} {read_percent} {operation}"

    def _set_axis(self, plotter: ModuleType, maximum_values: Optional[tuple[int, int]] = None) -> None:
        """
        Set the range for the plot axes.

        maximum_values is a

        This will start from 0, with a maximum
        """
        maximum_x: Optional[int] = None
        maximum_y: Optional[int] = None

        if maximum_values is not None:
            maximum_x = maximum_values[0]
            maximum_y = maximum_values[1]

        plotter.xlim(0, maximum_x)
        plotter.ylim(0, maximum_y)

    def _sort_plot_data(self, unsorted_data: COMMON_FORMAT_DATA_TYPE) -> PLOT_DATA_TYPE:
        """
        Sort the data read from the file by queue depth
        """
        keys: list[str] = [key for key in unsorted_data.keys() if isinstance(unsorted_data[key], dict)]
        plot_data: PLOT_DATA_TYPE = {}
        sorted_plot_data: PLOT_DATA_TYPE = {}
        for key, data in unsorted_data.items():
            if isinstance(data, dict):
                plot_data[key] = data

        sorted_keys: list[str] = sorted(keys, key=int)
        for key in sorted_keys:
            sorted_plot_data[key] = plot_data[key]

        return sorted_plot_data

    def _add_single_file_data_with_errorbars(self, plotter: ModuleType, file_data: COMMON_FORMAT_DATA_TYPE) -> None:
        """
        Add the data from a single file to a plot. Include error bars. Each point
        in the plot is the latency vs IOPs or bandwidth for a given queue depth.

        The plot will have red error bars with a blue plot line
        """

        sorted_plot_data: PLOT_DATA_TYPE = self._sort_plot_data(file_data)

        x_data: list[Union[int, float]] = []
        y_data: list[Union[int, float]] = []
        error_bars: list[float] = []

        for _, data in sorted_plot_data.items():
            # for blocksize less than 64K we want to use the bandwidth to plot the graphs,
            # otherwise we should use iops.
            blocksize: int = int(int(data["blocksize"]) / 1024)
            if blocksize >= 64:
                # convert bytes to Mb, not Mib, so use 1000s rather than 1024
                x_data.append(float(data["bandwidth_bytes"]) / (1000 * 1000))
                plotter.xlabel("Bandwidth (MB/s)")
            else:
                x_data.append(float(data["iops"]))
                plotter.xlabel("IOps")
                # The stored values are in ns, we want to convert to ms
            y_data.append(float(data["latency"]) / (1000 * 1000))
            plotter.ylabel("Latency (ms)")
            error_bars.append(float(data["std_deviation"]) / (1000 * 1000))

        plotter.errorbar(x_data, y_data, error_bars, capsize=3, ecolor="red")

    def _add_single_file_data(self, plotter: ModuleType, file_data: COMMON_FORMAT_DATA_TYPE, label: str) -> None:
        """
        Add the data from a single file to a plot.

        This will be a line of colour with data points marked by a small cross,
        and no error bars.
        """
        sorted_plot_data: PLOT_DATA_TYPE = self._sort_plot_data(file_data)

        x_data: list[Union[int, float]] = []
        y_data: list[Union[int, float]] = []

        blocksize: int = 0

        for _, data in sorted_plot_data.items():
            # for blocksize less than 64K we want to use the bandwidth to plot the graphs,
            # otherwise we should use iops.
            blocksize = int(int(data["blocksize"]) / 1024)
            if blocksize >= 64:
                # convert bytes to Mb, not Mib, so use 1000s rather than 1024
                x_data.append(float(data["bandwidth_bytes"]) / (1000 * 1000))
                plotter.xlabel("Bandwidth (MB/s)")
            else:
                x_data.append(float(data["iops"]))
                plotter.xlabel("IOps")
                # The stored values are in ns, we want to convert to ms
            y_data.append(float(data["latency"]) / (1000 * 1000))
            plotter.ylabel("Latency (ms)")

        # The "+-" here indicates a solid line with crosses at the data points
        plotter.plot(x_data, y_data, "+-", label=label)

    def _save_plot(self, plotter: ModuleType, file_path: str) -> None:
        """
        save the plot to disk as a png file
        """
        plotter.savefig(file_path, format=f"{PLOT_FILE_EXTENSION}")

    def _clear_plot(self, plotter: ModuleType) -> None:
        """
        Clear the plot data
        """
        plotter.clf()
